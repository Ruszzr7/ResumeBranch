import unittest

from pydantic import ValidationError

from backend.resume_schema import validate_resume_data


class ResumeSchemaTests(unittest.TestCase):
    def test_empty_resume_has_one_canonical_shape(self):
        result = validate_resume_data({})

        self.assertEqual(result["basics"]["name"], "")
        self.assertEqual(result["education"], [])
        self.assertEqual(result["work_experience"], [])
        self.assertEqual(result["others"]["skills"], [])
        self.assertEqual(validate_resume_data(result), result)

    def test_supported_optional_display_fields_are_preserved(self):
        result = validate_resume_data({
            "basics": {"name": "测试", "photo_aspect_ratio": 1.5},
            "others": {
                "field_labels": {"certificates": "资格证书"},
            },
            "custom_sections": [{
                "title": "校园经历",
                "items": ["学生会"],
                "list_style": "numbered",
            }],
        })

        self.assertEqual(result["basics"]["photo_aspect_ratio"], 1.5)
        self.assertEqual(result["others"]["field_labels"]["certificates"], "资格证书")
        self.assertNotIn("languages", result["others"]["field_labels"])
        self.assertEqual(result["custom_sections"][0]["list_style"], "numbered")

    def test_unknown_runtime_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_resume_data({"research": ["机器人控制"]})

        with self.assertRaises(ValidationError):
            validate_resume_data({"education": [{"school_name": "测试大学", "average_score": "90"}]})

    def test_invalid_supported_values_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_resume_data({
                "custom_sections": [{
                    "title": "校园经历",
                    "items": ["学生会"],
                    "list_style": "unknown",
                }],
            })

        with self.assertRaises(ValidationError):
            validate_resume_data({"basics": {"photo_aspect_ratio": 4.0}})


if __name__ == "__main__":
    unittest.main()
