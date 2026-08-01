import unittest

from backend.resume_data import normalize_resume_data


class ResumeDataNormalizationTests(unittest.TestCase):
    def test_migrates_gpa_from_legacy_thesis(self):
        source = {
            "education": [
                {
                    "school_name": "示例大学",
                    "theses": [
                        {"title": "GPA", "details": ["3.72/4.0"]},
                        {"title": "真实论文", "details": ["研究内容"]},
                    ],
                }
            ]
        }

        result = normalize_resume_data(source)
        education = result["education"][0]

        self.assertEqual(education["gpa"], "3.72")
        self.assertEqual(education["gpa_scale"], "4.0")
        self.assertEqual(education["theses"], [{"title": "真实论文", "details": ["研究内容"]}])
        self.assertNotIn("gpa", source["education"][0])

    def test_preserves_real_thesis_mentioning_gpa(self):
        source = {
            "education": [
                {
                    "theses": [
                        {"title": "基于 GPA 数据的学生表现研究", "details": []},
                    ]
                }
            ]
        }

        result = normalize_resume_data(source)

        self.assertEqual(result["education"][0]["gpa"], "")
        self.assertEqual(len(result["education"][0]["theses"]), 1)

    def test_normalizes_alias_and_combined_scale(self):
        source = {"education": [{"GPA": "3.8/4.0", "专业排名": "前 10%"}]}

        result = normalize_resume_data(source)["education"][0]

        self.assertEqual(result["gpa"], "3.8")
        self.assertEqual(result["gpa_scale"], "4.0")
        self.assertEqual(result["ranking"], "前 10%")
        self.assertNotIn("GPA", result)

    def test_migrates_chinese_gpa_with_full_score_phrase(self):
        source = {
            "education": [
                {"theses": [{"title": "平均绩点", "details": ["3.7（满分4.0）"]}]}
            ]
        }

        result = normalize_resume_data(source)["education"][0]

        self.assertEqual(result["gpa"], "3.7")
        self.assertEqual(result["gpa_scale"], "4.0")
        self.assertEqual(result["theses"], [])


if __name__ == "__main__":
    unittest.main()
