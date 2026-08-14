import unittest

from backend.pdf_generator import render_resume_to_html
from backend.layout_config import (
    apply_density,
    apply_layout_change_groups,
    build_layout_changes,
    default_layout_config,
    format_compact_academic_metric,
    normalize_layout_config,
    component_position,
    resolve_module_layout,
    resolve_content_block_flow,
    resolve_education_column_widths,
    resolve_layout_tokens,
    resolve_photo_height_mm,
    reset_layout_section,
)


class LayoutConfigTests(unittest.TestCase):
    def test_column_titles_list_styles_and_education_merges_are_normalized(self):
        config = normalize_layout_config({
            "global": {
                "titleOverrides": {"skills": {"zh": "技术栈"}},
                "sectionPlacements": {
                    "research_interests": "education",
                    "publications": "education",
                    "skills": "education",
                    "honors": "unknown",
                },
            },
            "skills": {"listStyle": "numbered"},
            "publications": {"listStyle": "paragraph"},
        })
        self.assertEqual(config["global"]["titleOverrides"]["skills"]["zh"], "技术栈")
        self.assertEqual(config["global"]["sectionPlacements"], {
            "research_interests": "education", "publications": "education",
        })
        self.assertEqual(config["skills"]["listStyle"], "numbered")
        self.assertEqual(config["publications"]["listStyle"], "paragraph")

    def test_content_block_flow_distinguishes_inline_and_separate_labels(self):
        self.assertEqual(
            resolve_content_block_flow({"type": "paragraph", "label": "项目简介"})["labelPlacement"],
            "inline",
        )
        self.assertEqual(
            resolve_content_block_flow({"type": "numbered_list", "label": "项目职责"})["labelPlacement"],
            "separate",
        )
        self.assertEqual(
            resolve_content_block_flow({"type": "bullet_list", "label": ""})["labelPlacement"],
            "none",
        )
        self.assertFalse(resolve_content_block_flow({
            "type": "paragraph", "label": "项目简介", "label_bold": False,
        })["labelBold"])
        self.assertFalse(resolve_content_block_flow({
            "type": "paragraph", "semantic_role": "introduction", "label": "",
        })["visible"])
        self.assertTrue(resolve_content_block_flow({
            "type": "bullet_list", "semantic_role": "generic", "label": "",
        })["visible"])
        self.assertEqual(resolve_content_block_flow({
            "type": "numbered_list", "semantic_role": "responsibilities", "label": "主要贡献",
        })["contentIndentLevels"], 2)

    def test_defaults_are_complete_and_independent(self):
        first = default_layout_config()
        second = default_layout_config()
        first["education"]["preset"] = "classic"
        first["education"]["componentRows"][0]["cells"][0]["alignment"] = "right"
        self.assertEqual(second["education"]["preset"], "compact")
        self.assertEqual(second["education"]["componentRows"][0]["cells"][0]["alignment"], "left")
        self.assertEqual(second["education"]["componentRows"][0]["cells"][1]["alignment"], "left")
        self.assertEqual(second["skills"]["indentLevel"], 0)
        self.assertEqual(second["research_interests"]["indentLevel"], 0)
        self.assertEqual(second["honors"]["indentLevel"], 0)
        self.assertEqual(second["global"]["sectionPlacements"], {})
        self.assertEqual(
            [row["cells"][0]["components"] for row in second["others"]["componentRows"]],
            [["certificates"], ["languages"]],
        )
        self.assertEqual(second["global"]["sectionOrder"], [
            "education", "honors", "publications", "research_interests", "skills",
            "work_experience", "project_experience", "custom_sections", "others", "self_evaluation",
        ])

    def test_v7_default_order_migrates_but_user_order_is_preserved(self):
        old_default = [
            "education", "skills", "research_interests", "honors", "publications",
            "work_experience", "project_experience", "custom_sections", "others", "self_evaluation",
        ]
        migrated = normalize_layout_config({"version": 7, "global": {"sectionOrder": old_default}})
        self.assertEqual(migrated["global"]["sectionOrder"], default_layout_config()["global"]["sectionOrder"])

        custom = [
            "education", "publications", "honors", "research_interests", "skills",
            "work_experience", "project_experience", "custom_sections", "others", "self_evaluation",
        ]
        preserved = normalize_layout_config({"version": 7, "global": {"sectionOrder": custom}})
        self.assertEqual(preserved["global"]["sectionOrder"], custom)

    def test_unknown_values_and_numbers_are_normalized(self):
        config = normalize_layout_config({
            "global": {"density": "wild", "fontSize": 99, "lineHeight": 0},
            "education": {"preset": "floating", "schoolTagStyle": "neon"},
        })
        self.assertEqual(config["global"]["density"], "compact")
        self.assertEqual(config["global"]["fontSize"], 11.5)
        self.assertEqual(config["global"]["lineHeight"], 1.0)
        self.assertEqual(config["education"]["preset"], "compact")
        self.assertEqual(config["education"]["schoolTagStyle"], "text")

    def test_global_section_chrome_and_constrained_basic_photo_are_normalized(self):
        config = normalize_layout_config({
            "global": {"titleStyle": "underline"},
            "basics": {"photoWidthMm": 99, "titleAlignment": "center"},
            "education": {"titleStyle": "plain", "titleAlignment": "right"},
            "work_experience": {"preset": "classic"},
            "internship_experience": {"preset": "classic"},
        })
        self.assertEqual(config["global"]["titleStyle"], "underline")
        self.assertIsNone(config["basics"]["titleAlignment"])
        self.assertIsNone(config["education"]["titleStyle"])
        self.assertIsNone(config["education"]["titleAlignment"])
        self.assertEqual(config["work_experience"]["preset"], "compact")
        self.assertEqual(config["internship_experience"]["preset"], "compact")
        self.assertEqual(config["basics"]["photoWidthMm"], 30)
        tokens = resolve_layout_tokens(config)
        self.assertEqual(tokens["photoWidthMm"], 30)
        self.assertAlmostEqual(tokens["photoHeightMm"], 30 * 26 / 21)

    def test_photo_height_is_capped_to_the_header_frame_when_content_follows(self):
        config = default_layout_config()
        tokens = resolve_layout_tokens(config)
        data = {
            "basics": {
                "name": "张三",
                "photo": "data:image/png;base64,placeholder",
                "photo_aspect_ratio": 0.75,
            },
            "education": [{"school_name": "示例大学"}],
        }

        resolved = resolve_photo_height_mm(data, config, tokens)

        self.assertGreaterEqual(resolved, 10)
        self.assertLess(resolved, tokens["photoHeightMm"])
        self.assertEqual(resolve_photo_height_mm({"basics": {}}, config, tokens), tokens["photoHeightMm"])

    def test_typography_is_recorded_and_unknown_fonts_cannot_split_renderers(self):
        config = normalize_layout_config({
            "version": 2,
            "typography": {
                "preset": "unknown",
                "latinFont": "Random Latin",
                "eastAsiaFont": "Random CJK",
            },
        })
        self.assertEqual(config["version"], 8)
        self.assertEqual(config["typography"]["preset"], "microsoft-office")
        self.assertEqual(config["typography"]["latinFont"], "Arial")
        self.assertEqual(config["typography"]["eastAsiaFont"], "Microsoft YaHei")

    def test_v3_default_visual_scale_migrates_to_v4_semantic_body_size(self):
        config = normalize_layout_config({
            "version": 3,
            "global": {"fontSize": 10.5, "lineHeight": 1.32, "moduleMargin": 0.45},
        })
        self.assertEqual(config["version"], 8)
        self.assertEqual(config["global"]["fontSize"], 9)
        self.assertEqual(config["global"]["lineHeight"], 1.28)
        self.assertEqual(config["global"]["moduleMargin"], 0.55)

    def test_invalid_enums_unknown_fields_and_duplicate_sections_normalize_deterministically(self):
        config = normalize_layout_config({
            "version": 6,
            "global": {
                "density": "invalid", "titleStyle": "invalid",
                "sectionOrder": ["skills", "education", "skills", "invalid"],
                "hiddenSections": ["honors", "invalid"],
            },
            "project_experience": {"detailsStyle": "numbered"},
            "basics": {"hiddenFields": ["phone", "invalid"]},
        })
        self.assertEqual(config["global"]["density"], "compact")
        self.assertEqual(config["global"]["titleStyle"], "underline")
        self.assertEqual(config["global"]["sectionOrder"].count("skills"), 1)
        self.assertEqual(config["global"]["hiddenSections"], ["honors"])
        self.assertEqual(config["project_experience"]["detailsStyle"], "bullets")
        self.assertEqual(config["basics"]["hiddenFields"], ["phone"])
        self.assertEqual(config["typography"]["fontSizes"], {
            "name": 14, "sectionTitle": 11, "entryTitle": 10,
            "meta": 9, "body": 9, "label": 9,
        })

    def test_v4_layout_migrates_to_explicit_semantic_font_sizes_without_visual_change(self):
        config = normalize_layout_config({
            "version": 4,
            "global": {"fontSize": 9.5},
        })
        self.assertEqual(config["version"], 8)
        self.assertEqual(config["typography"]["fontSizes"], {
            "name": 14, "sectionTitle": 11.5, "entryTitle": 10.5,
            "meta": 9.5, "body": 9.5, "label": 9.5,
        })

    def test_semantic_font_sizes_are_half_point_bounded_and_unknown_roles_are_removed(self):
        config = normalize_layout_config({
            "version": 5,
            "global": {"fontSize": 10.25},
            "typography": {"fontSizes": {
                "name": 99,
                "sectionTitle": 11.26,
                "entryTitle": 8,
                "meta": 10.24,
                "body": 8,
                "label": 11.75,
                "unknown": 42,
            }},
        })
        self.assertEqual(config["global"]["fontSize"], 10.5)
        self.assertEqual(config["typography"]["fontSizes"], {
            "name": 20, "sectionTitle": 11.5, "entryTitle": 8.5,
            "meta": 10, "body": 10.5, "label": 12,
        })

    def test_v5_standard_default_line_height_migrates_to_compact_export_rhythm(self):
        config = normalize_layout_config({
            "version": 5,
            "global": {"density": "standard", "lineHeight": 1.35},
        })
        self.assertEqual(config["version"], 8)
        self.assertEqual(config["global"]["lineHeight"], 1.28)

        custom = normalize_layout_config({
            "version": 5,
            "global": {"density": "standard", "lineHeight": 1.4},
        })
        self.assertEqual(custom["global"]["lineHeight"], 1.4)

    def test_shared_tokens_convert_spacing_to_physical_units_once(self):
        tokens = resolve_layout_tokens(default_layout_config(), {
            "fontSize": 9,
            "lineHeight": 1.28,
            "moduleMargin": 0.55,
            "marginTop": 7,
        })
        self.assertEqual(tokens["fontFamilyCss"], '"Arial", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif')
        self.assertEqual(tokens["bodyFontSizePt"], 9)
        self.assertEqual(tokens["metaFontSizePt"], 9)
        self.assertEqual(tokens["entryTitleFontSizePt"], 10)
        self.assertEqual(tokens["sectionTitleFontSizePt"], 11)
        self.assertEqual(tokens["nameFontSizePt"], 14)
        self.assertEqual(tokens["labelFontSizePt"], 9)
        self.assertEqual(tokens["bodyFontWeight"], 400)
        self.assertEqual(tokens["metaFontWeight"], 400)
        self.assertEqual(tokens["entryTitleFontWeight"], 700)
        self.assertEqual(tokens["sectionTitleFontWeight"], 700)
        self.assertEqual(tokens["nameFontWeight"], 700)
        self.assertEqual(tokens["letterSpacingPt"], 0)
        self.assertEqual(tokens["labelFontWeight"], 700)
        self.assertAlmostEqual(tokens["listTextIndentPt"], 13.95)
        self.assertAlmostEqual(tokens["listMarkerGapPt"], 2.25)
        self.assertAlmostEqual(tokens["moduleSpacingPt"], 4.95)
        self.assertAlmostEqual(tokens["paragraphSpacingPt"], 0.81)
        self.assertEqual(tokens["marginTopMm"], 7)

    def test_compact_education_middle_expands_symmetrically_for_gpa_and_rank(self):
        tokens = resolve_layout_tokens(default_layout_config())
        short = resolve_education_column_widths(
            tokens,
            schools=["中山大学"],
            dates=["2024.09 - 2027.06"],
            degree_majors=["硕士 · 电子信息"],
            compact_metrics=["4.0/5.0 (前5%)"],
        )
        long = resolve_education_column_widths(
            tokens,
            schools=["中山大学"],
            dates=["2024.09 - 2027.06"],
            degree_majors=["硕士 · 电子信息工程与人工智能"],
            compact_metrics=["4.0/5.0 (前5%)"],
        )

        self.assertGreater(long["middleMm"], short["middleMm"])
        self.assertAlmostEqual(short["sideMm"] * 2 + short["middleMm"], 192.0, places=2)
        self.assertAlmostEqual(long["sideMm"] * 2 + long["middleMm"], 192.0, places=2)

    def test_compact_metric_preserves_user_ranking_wording(self):
        base = {"gpa": "3.8", "gpa_scale": "5.0"}
        self.assertEqual(
            format_compact_academic_metric({**base, "ranking": "10%"}),
            "3.8/5.0 (10%)",
        )
        self.assertEqual(
            format_compact_academic_metric({**base, "ranking": "前10%"}),
            "3.8/5.0 (前10%)",
        )

    def test_pdf_html_consumes_the_shared_font_and_spacing_tokens(self):
        html = render_resume_to_html(
            {"basics": {"name": "张三"}},
            {"fontSize": 9, "moduleMargin": 0.55},
            layout_config=default_layout_config(),
        )
        self.assertIn('font-family: "Arial", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;', html)
        self.assertIn("--module-margin: 4.95pt;", html)
        self.assertIn("--name-font-size: 14pt;", html)
        self.assertIn("--meta-font-weight: 400;", html)
        self.assertIn("--entry-title-font-weight: 700;", html)
        self.assertIn("margin-top: var(--module-margin);", html)
        self.assertIn(".section {\n        margin-bottom: 0;", html)
        self.assertIn("margin-bottom: var(--paragraph-spacing);", html)

    def test_three_column_forces_metrics_into_information_column(self):
        config = normalize_layout_config({
            "education": {"preset": "three-column", "metricsPlacement": "below"}
        })
        self.assertEqual(config["education"]["metricsPlacement"], "info-column")

    def test_split_work_adds_virtual_internship_section(self):
        config = normalize_layout_config({
            "global": {"splitWorkExperience": True, "sectionOrder": ["education", "work_experience"]}
        })
        self.assertEqual(
            config["global"]["sectionOrder"].index("internship_experience"),
            config["global"]["sectionOrder"].index("work_experience") + 1,
        )

    def test_density_applies_safe_numeric_bundle(self):
        config = apply_density({}, "compact")
        self.assertEqual(config["global"]["fontSize"], 9)
        self.assertEqual(config["global"]["lineHeight"], 1.25)
        self.assertEqual(config["global"]["moduleMargin"], 0.5)
        self.assertEqual(config["typography"]["fontSizes"]["body"], 9)
        self.assertEqual(config["typography"]["fontSizes"]["sectionTitle"], 11)

    def test_typography_changes_are_atomic_with_global_layout(self):
        before = default_layout_config()
        after = default_layout_config()
        after["typography"]["fontSizes"]["name"] = 16
        changes = build_layout_changes(before, after)
        self.assertEqual([change["id"] for change in changes], ["layout-global"])
        self.assertIn("分角色字号", {detail["field_label"] for detail in changes[0]["details"]})
        selected = apply_layout_change_groups(before, after, ["layout-global"])
        self.assertEqual(selected["typography"]["fontSizes"]["name"], 16)

    def test_layout_changes_are_atomic_per_module(self):
        before = default_layout_config()
        after = default_layout_config()
        after["education"].update({"preset": "three-column", "schoolTagStyle": "outline"})
        after["self_evaluation"]["preset"] = "bullets"
        changes = build_layout_changes(before, after)
        self.assertEqual({change["id"] for change in changes}, {"layout-education", "layout-self_evaluation"})
        education_change = next(change for change in changes if change["id"] == "layout-education")
        labels = {detail["field_label"] for detail in education_change["details"]}
        self.assertEqual(labels, {"教育信息布局", "学校标签样式", "成绩信息位置"})
        selected = apply_layout_change_groups(before, after, ["layout-education"])
        self.assertEqual(selected["education"]["preset"], "three-column")
        self.assertEqual(selected["self_evaluation"]["preset"], "compact")

    def test_reset_one_module_preserves_other_overrides(self):
        config = default_layout_config()
        config["education"]["preset"] = "classic"
        config["others"]["preset"] = "inline"
        reset = reset_layout_section(config, "education")
        self.assertEqual(reset["education"]["preset"], "compact")
        self.assertEqual(reset["others"]["preset"], "inline")

    def test_v6_layout_migrates_to_module_contract_without_second_line_height(self):
        config = normalize_layout_config({
            "version": 6,
            "global": {"lineHeight": 1.45},
            "education": {"preset": "classic"},
        })
        module = resolve_module_layout(config, "education")
        self.assertEqual(config["version"], 8)
        self.assertEqual(module["resolvedLineHeight"], 1.45)
        self.assertNotIn("lineHeight", config["education"])
        self.assertEqual(component_position(config, "education", "school"), (0, 0))

    def test_module_contract_cleans_unknown_components_and_constrains_long_text(self):
        config = normalize_layout_config({
            "version": 7,
            "work_experience": {
                "hiddenComponents": ["position", "unknown", "content"],
                "indentLevel": 99,
                "componentRows": [{"cells": [{
                    "components": ["organization", "content", "unknown"],
                    "flow": "inline", "width": "content", "alignment": "right",
                }]}],
            },
        })
        work = config["work_experience"]
        self.assertEqual(work["hiddenComponents"], ["position"])
        self.assertEqual(work["indentLevel"], 3)
        content_row = next(
            row for row in work["componentRows"]
            if any("content" in cell["components"] for cell in row["cells"])
        )
        self.assertEqual(content_row["cells"], [{
            "components": ["content"], "flow": "stacked", "width": "fill", "alignment": "justify",
        }])


if __name__ == "__main__":
    unittest.main()
