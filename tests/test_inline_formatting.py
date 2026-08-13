import unittest

from backend.inline_formatting import (
    InlineFormatError,
    format_inline_html,
    format_resume_text,
    parse_inline_bold,
    plain_inline_text,
    set_inline_bold,
)


def resume_with_repeated_text():
    return {
        "basics": {"name": "测试用户"},
        "education": [],
        "work_experience": [
            {
                "company_name": "甲公司",
                "job_title": "后端实习生",
                "job_type": "实习",
                "content_blocks": [{
                    "type": "bullet_list", "label": "", "text": "",
                    "items": ["项目性能提升35%"],
                }],
            },
            {
                "company_name": "乙公司",
                "job_title": "后端工程师",
                "job_type": "全职",
                "content_blocks": [{
                    "type": "bullet_list", "label": "", "text": "",
                    "items": ["项目性能提升35%"],
                }],
            },
        ],
        "project_experience": [{
            "project_name": "性能项目",
            "role": "开发",
            "content_blocks": [{
                "type": "bullet_list", "label": "", "text": "",
                "items": ["项目性能提升35%"],
            }],
        }],
        "others": {"skills": [], "certificates": [], "languages": []},
        "self_evaluation": [],
    }


class InlineFormattingTests(unittest.TestCase):
    def test_rendering_preserves_source_whitespace_and_natural_break_points(self):
        for value in (
            "中文与 ASCII token 保留普通空格",
            "括号（全角）与(parentheses)保持原样",
            "混排 A1/B2、C++ API，标点不被改写",
        ):
            self.assertEqual(plain_inline_text(value), value)
            self.assertEqual(format_inline_html(value), value)

    def test_parser_preserves_unmatched_markers_as_literal_text(self):
        value = "负责 **核心模块"
        self.assertEqual(plain_inline_text(value), value)
        self.assertEqual(
            [(segment.text, segment.bold) for segment in parse_inline_bold(value)],
            [(value, False)],
        )

    def test_html_renderer_escapes_user_html_and_allows_bold_only(self):
        rendered = format_inline_html('<img src=x onerror="boom"> **安全结果**')
        self.assertEqual(
            rendered,
            '&lt;img src=x onerror=&quot;boom&quot;&gt; <strong>安全结果</strong>',
        )
        self.assertNotIn("<img", rendered)

    def test_bold_and_unbold_can_split_existing_runs_without_changing_text(self):
        bolded = set_inline_bold("性能**提升**35%", "提升35", bold=True)
        self.assertEqual(bolded, "性能**提升35**%")
        self.assertEqual(plain_inline_text(bolded), "性能提升35%")

        unbolded = set_inline_bold("性能**提升35%**", "提升35", bold=False)
        self.assertEqual(unbolded, "性能提升35**%**")
        self.assertEqual(plain_inline_text(unbolded), "性能提升35%")

    def test_quoted_section_words_do_not_expand_scope(self):
        original = resume_with_repeated_text()
        candidate, reference = format_resume_text(
            original,
            "项目性能提升35%",
            bold=True,
            request_text="把实习经历中的“项目性能提升35%”加粗",
        )
        self.assertEqual(reference.section, "internship_experience")
        self.assertEqual(
            candidate["work_experience"][0]["content_blocks"][0]["items"][0],
            "**项目性能提升35%**",
        )
        self.assertEqual(
            candidate["work_experience"][1]["content_blocks"][0]["items"][0],
            "项目性能提升35%",
        )
        self.assertEqual(
            candidate["project_experience"][0]["content_blocks"][0]["items"][0],
            "项目性能提升35%",
        )

    def test_zero_or_multiple_matches_fail_closed_without_mutating_input(self):
        original = resume_with_repeated_text()
        with self.assertRaisesRegex(InlineFormatError, "找到 3 处"):
            format_resume_text(original, "项目性能提升35%", bold=True)
        with self.assertRaisesRegex(InlineFormatError, "没有找到"):
            format_resume_text(original, "不存在的原文", bold=True)
        self.assertEqual(
            original["work_experience"][0]["content_blocks"][0]["items"][0],
            "项目性能提升35%",
        )

    def test_reapplying_the_same_state_is_rejected_without_candidate(self):
        data = resume_with_repeated_text()
        data["work_experience"][0]["content_blocks"][0]["items"][0] = "**项目性能提升35%**"
        with self.assertRaisesRegex(InlineFormatError, "已经是粗体"):
            format_resume_text(
                data,
                "项目性能提升35%",
                bold=True,
                request_text="把实习经历中的“项目性能提升35%”加粗",
            )

    def test_semantically_bold_titles_reject_misleading_inline_changes(self):
        data = resume_with_repeated_text()
        with self.assertRaisesRegex(InlineFormatError, "版式整体加粗"):
            format_resume_text(
                data,
                "甲公司",
                bold=True,
                request_text="把实习经历中的“甲公司”加粗",
            )
        with self.assertRaisesRegex(InlineFormatError, "不能只取消其中一部分"):
            format_resume_text(
                data,
                "甲公司",
                bold=False,
                request_text="把实习经历中的“甲公司”取消加粗",
            )


if __name__ == "__main__":
    unittest.main()
