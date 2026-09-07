import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from backend import resume_translation


class FakeDb:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeModel:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, messages):
        entries = json.loads(messages[-1].content)
        self.calls.append(entries)
        return AIMessage(content=json.dumps({
            "translations": {
                entry["id"]: f"EN:{entry['text']}" for entry in entries
            }
        }, ensure_ascii=False))


def sample_resume():
    return {
        "basics": {
            "name": "李明",
            "phone": "13800000000",
            "email": "name@example.com",
            "birth_date": "2000.01",
            "target_position": "控制算法工程师",
        },
        "education": [{
            "school_name": "示例大学",
            "major": "控制工程",
            "degree": "硕士",
            "date_range": ["2024.09", "2027.06"],
        }],
        "others": {"skills": ["熟悉 Python 与机器人控制"]},
    }


def project_resume():
    source = sample_resume()
    source["project_experience"] = [{
        "project_name": "导航平台",
        "content_blocks": [
            {"type": "paragraph", "semantic_role": "tech_stack", "label": "技术栈", "label_bold": True, "text": "Python 与 FastAPI", "items": []},
            {"type": "paragraph", "semantic_role": "introduction", "label": "项目简介", "label_bold": True, "text": "导航服务", "items": []},
        ],
    }]
    return source


class ResumeTranslationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.memory = {}

    def get_memory(self, db, user_id, ids):
        return {key: self.memory[key] for key in ids if key in self.memory}

    def save_memory(self, db, user_id, **entry):
        self.memory[entry["memory_id"]] = entry["translated_text"]

    async def test_preserves_structure_and_skips_contact_dates(self):
        model = FakeModel()
        with patch.object(resume_translation, "get_translation_memory", self.get_memory), \
             patch.object(resume_translation, "save_translation_memory", self.save_memory):
            result = await resume_translation.translate_resume(
                FakeDb(), 7, sample_resume(), model=model,
            )

        translated = result["resume_data"]
        self.assertEqual(translated["basics"]["name"], "EN:李明")
        self.assertEqual(translated["basics"]["target_position"], "EN:控制算法工程师")
        self.assertEqual(translated["basics"]["phone"], "13800000000")
        self.assertEqual(translated["basics"]["email"], "name@example.com")
        self.assertEqual(translated["basics"]["birth_date"], "2000.01")
        self.assertEqual(translated["education"][0]["date_range"], ["2024.09", "2027.06"])
        self.assertGreater(result["new_translations"], 0)
        self.assertEqual(result["cache_hits"], 0)
        self.assertEqual(len(model.calls), 1)

    async def test_reuses_unchanged_field_translations(self):
        model = FakeModel()
        with patch.object(resume_translation, "get_translation_memory", self.get_memory), \
             patch.object(resume_translation, "save_translation_memory", self.save_memory):
            first = await resume_translation.translate_resume(FakeDb(), 7, sample_resume(), model=model)
            second = await resume_translation.translate_resume(FakeDb(), 7, sample_resume(), model=model)

        self.assertEqual(first["new_translations"], second["cache_hits"])
        self.assertEqual(second["new_translations"], 0)
        self.assertEqual(len(model.calls), 1)

    async def test_translation_preserves_project_tech_stack_role_and_order(self):
        model = FakeModel()
        with patch.object(resume_translation, "get_translation_memory", self.get_memory), \
             patch.object(resume_translation, "save_translation_memory", self.save_memory):
            result = await resume_translation.translate_resume(FakeDb(), 7, project_resume(), model=model)

        blocks = result["resume_data"]["project_experience"][0]["content_blocks"]
        self.assertEqual([block["semantic_role"] for block in blocks], ["tech_stack", "introduction"])
        self.assertEqual(blocks[0]["label"], "EN:技术栈")

    async def test_changed_field_is_retranslated_while_unchanged_fields_are_reused(self):
        model = FakeModel()
        with patch.object(resume_translation, "get_translation_memory", self.get_memory), \
             patch.object(resume_translation, "save_translation_memory", self.save_memory):
            first = await resume_translation.translate_resume(FakeDb(), 7, sample_resume(), model=model)
            changed = sample_resume()
            changed["basics"]["target_position"] = "机器人算法工程师"
            second = await resume_translation.translate_resume(FakeDb(), 7, changed, model=model)

        self.assertGreater(second["cache_hits"], 0)
        self.assertEqual(second["new_translations"], 1)
        self.assertEqual(second["resume_data"]["basics"]["target_position"], "EN:机器人算法工程师")
        self.assertEqual(second["resume_data"]["education"][0]["school_name"], first["resume_data"]["education"][0]["school_name"])
        self.assertEqual(len(model.calls), 2)

    async def test_endpoint_saves_translated_resume_without_chat_confirmation(self):
        from backend import main

        translated = {"basics": {"name": "Li Ming"}}
        service_result = {
            "resume_data": translated,
            "cache_hits": 2,
            "new_translations": 1,
            "total_translatable": 3,
        }
        task = SimpleNamespace(id="task-1")
        with patch.object(main, "_require_request_task", return_value=task), \
             patch.object(main, "get_user_resume", return_value=sample_resume()), \
             patch.object(main, "get_resume_translation_state", return_value=None), \
             patch.object(main, "save_resume_translation_state"), \
             patch.object(resume_translation, "translate_resume", AsyncMock(return_value=service_result)), \
             patch.object(main, "_acquire_short_mutation_lock", return_value=("owner", "request")), \
             patch.object(main, "_release_short_mutation_lock"), \
             patch.object(main, "commit_resume_mutation", return_value={
                 "resume_data": translated,
                 "state_version": {"sequence": 1},
             }) as commit_mutation:
            result = await main.translate_resume_endpoint(
                main.TranslateResumeRequest(),
                db=FakeDb(),
                current_user=SimpleNamespace(id=7),
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["cache_hits"], 2)
        self.assertEqual(commit_mutation.call_args.args[2], "task-1")
        self.assertEqual(commit_mutation.call_args.kwargs["source"], "translation")

    async def test_endpoint_reuses_durable_full_snapshot(self):
        from backend import main
        from backend.resume_changes import resume_digest

        source = sample_resume()
        translated = {"basics": {"name": "Li Ming"}}
        state = SimpleNamespace(
            source_digest=resume_digest(source),
            source_data=source,
            translated_data=translated,
        )
        translator = AsyncMock()
        with patch.object(main, "_require_request_task", return_value=SimpleNamespace(id="task-1")), \
             patch.object(main, "get_user_resume", return_value=source), \
             patch.object(main, "get_resume_translation_state", return_value=state), \
             patch.object(resume_translation, "translate_resume", translator), \
             patch.object(main, "save_resume_translation_state"), \
             patch.object(main, "_acquire_short_mutation_lock", return_value=("owner", "request")), \
             patch.object(main, "_release_short_mutation_lock"), \
             patch.object(main, "commit_resume_mutation", return_value={
                 "resume_data": translated,
                 "state_version": {"sequence": 1},
             }):
            result = await main.translate_resume_endpoint(
                main.TranslateResumeRequest(), FakeDb(), SimpleNamespace(id=7),
            )

        self.assertTrue(result["full_snapshot_reused"])
        self.assertEqual(result["resume_data"], translated)
        translator.assert_not_awaited()

    async def test_restore_endpoint_uses_durable_chinese_snapshot(self):
        from backend import main

        source = sample_resume()
        state = SimpleNamespace(source_data=source)
        with patch.object(main, "_require_request_task", return_value=SimpleNamespace(id="task-1")), \
             patch.object(main, "get_user_resume", return_value={"basics": {"name": "Li Ming"}}), \
             patch.object(main, "get_resume_translation_state", return_value=state), \
             patch.object(main, "save_resume_translation_state"), \
             patch.object(main, "_acquire_short_mutation_lock", return_value=("owner", "request")), \
             patch.object(main, "_release_short_mutation_lock"), \
             patch.object(main, "commit_resume_mutation", return_value={
                 "resume_data": source,
                 "state_version": {"sequence": 1},
             }) as commit_mutation:
            result = await main.restore_resume_translation_endpoint(
                FakeDb(), SimpleNamespace(id=7),
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["resume_data"]["basics"]["name"], "李明")
        self.assertEqual(commit_mutation.call_args.kwargs["source"], "translation_restore")


if __name__ == "__main__":
    unittest.main()
