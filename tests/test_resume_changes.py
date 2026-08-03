import unittest

from backend.resume_changes import apply_resume_changes, build_resume_changes, resume_digest


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

    def test_missing_and_empty_fields_are_not_presented_as_changes(self):
        changes = build_resume_changes({"basics": {}}, {"basics": {"age": "", "location": None}})
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
