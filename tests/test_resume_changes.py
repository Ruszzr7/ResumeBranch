from copy import deepcopy
import unittest

from backend.layout_config import default_layout_config
from backend.resume_changes import (
    apply_resume_changes,
    build_resume_changes,
    build_resume_state_version,
    resume_digest,
    resume_state_version_matches,
    validate_resume_change_set,
)
from backend.resume_schema import validate_resume_data


class ResumeChangeTests(unittest.TestCase):
    def setUp(self):
        self.before = {
            "basics": {"name": "张三", "target_position": "开发"},
            "education": [{"school": "A大学", "gpa": "3.5", "details": ["一等奖学金"]}],
            "work_experience": [],
            "project_experience": [],
            "others": {"skills": ["Python"]},
            "self_evaluation": [],
        }
        self.after = {
            **self.before,
            "basics": {"name": "张伟", "target_position": "后端开发"},
            "education": [{"school": "A大学", "gpa": "3.8", "details": ["一等奖学金"]}],
            "others": {"skills": ["Python", "Go"]},
        }

    def test_builds_readable_granular_changes(self):
        changes = build_resume_changes(self.before, self.after)
        self.assertEqual(len(changes), 4)
        self.assertIn("基础信息 · 姓名", [item["label"] for item in changes])
        self.assertIn("教育经历 1 · GPA", [item["label"] for item in changes])
        self.assertEqual(len({item["id"] for item in changes}), 4)

    def test_applies_only_selected_changes(self):
        changes = build_resume_changes(self.before, self.after)
        selected = [item["id"] for item in changes if item["path"] in [["basics", "name"], ["education", 0, "gpa"]]]
        result = apply_resume_changes(self.before, changes, selected)
        self.assertEqual(result["basics"]["name"], "张伟")
        self.assertEqual(result["basics"]["target_position"], "开发")
        self.assertEqual(result["education"][0]["gpa"], "3.8")
        self.assertEqual(result["others"]["skills"], ["Python"])

    def test_digest_is_stable_for_key_order(self):
        self.assertEqual(resume_digest({"a": 1, "b": 2}), resume_digest({"b": 2, "a": 1}))

    def test_state_version_hashes_content_and_layout_independently(self):
        content = validate_resume_data({"basics": {"name": "张三"}})
        layout = default_layout_config()
        base = build_resume_state_version(content, layout)

        changed_content = deepcopy(content)
        changed_content["basics"]["name"] = "李四"
        self.assertFalse(resume_state_version_matches(
            base, changed_content, layout, check_content=True, check_layout=False,
        ))
        self.assertTrue(resume_state_version_matches(
            base, changed_content, layout, check_content=False, check_layout=True,
        ))
        self.assertFalse(resume_state_version_matches(
            base, changed_content, layout, check_content=True, check_layout=True,
        ))

        changed_layout = deepcopy(layout)
        changed_layout["global"]["moduleMargin"] = 0.8
        self.assertTrue(resume_state_version_matches(
            base, content, changed_layout, check_content=True, check_layout=False,
        ))
        self.assertFalse(resume_state_version_matches(
            base, content, changed_layout, check_content=False, check_layout=True,
        ))
        self.assertFalse(resume_state_version_matches(
            base, content, changed_layout, check_content=True, check_layout=True,
        ))

    def test_missing_and_empty_fields_are_not_presented_as_changes(self):
        changes = build_resume_changes({"basics": {}}, {"basics": {"age": "", "location": None}})
        self.assertEqual(changes, [])

    def test_internal_field_names_never_leak_to_user_labels(self):
        changes = build_resume_changes(
            {"basics": {"birth_date": ""}, "custom_sections": []},
            {
                "basics": {"birth_date": "2000.01"},
                "custom_sections": [{"title": "社团经历", "items": ["负责人"]}],
            },
        )
        labels = [item["label"] for item in changes]
        self.assertTrue(any("出生年月" in label for label in labels))
        self.assertFalse(any("birth_date" in label or "custom_sections" in label for label in labels))

    def test_content_block_items_keep_numbered_and_bullet_boundaries_in_preview(self):
        before = {
            "project_experience": [{
                "content_blocks": [
                    {"type": "numbered_list", "items": ["旧职责一", "旧职责二"]},
                    {"type": "bullet_list", "items": ["旧补充一", "旧补充二"]},
                ],
            }],
        }
        after = {
            "project_experience": [{
                "content_blocks": [
                    {"type": "numbered_list", "items": ["新职责一", "新职责二"]},
                    {"type": "bullet_list", "items": ["新补充一", "新补充二"]},
                ],
            }],
        }

        changes = build_resume_changes(before, after)

        self.assertEqual(changes[0]["before_display"], "1. 旧职责一\n2. 旧职责二")
        self.assertEqual(changes[0]["after_display"], "1. 新职责一\n2. 新职责二")
        self.assertEqual(changes[1]["before_display"], "• 旧补充一\n• 旧补充二")
        self.assertEqual(changes[1]["after_display"], "• 新补充一\n• 新补充二")
        self.assertTrue(validate_resume_change_set(before, after, changes))

    def test_change_set_is_bound_to_the_candidate_before_selective_apply(self):
        changes = build_resume_changes(self.before, self.after)
        self.assertTrue(validate_resume_change_set(self.before, self.after, changes))
        tampered = [dict(change) for change in changes]
        tampered[0]["after"] = "恶意替换"
        self.assertFalse(validate_resume_change_set(self.before, self.after, tampered))

    def test_change_set_rejects_unknown_paths(self):
        changes = build_resume_changes(self.before, self.after)
        changes.append({
            "id": "change-extra", "path": ["basics", "photo"],
            "operation": "replace", "before": "", "after": "data:image/png;base64,unexpected",
        })
        self.assertFalse(validate_resume_change_set(self.before, self.after, changes))


if __name__ == "__main__":
    unittest.main()
