import unittest

from backend.pdf_generator import render_resume_to_html
from backend.layout_config import (
    LAYOUT_TEMPLATES,
    apply_density,
    apply_layout_template,
    apply_layout_change_groups,
    build_layout_changes,
    default_layout_config,
    normalize_layout_config,
    resolve_content_block_flow,
    resolve_layout_tokens,
    reset_layout_section,
)


class LayoutConfigTests(unittest.TestCase):
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

    def test_defaults_are_complete_and_independent(self):
        first = default_layout_config()
        second = default_layout_config()
        first["education"]["preset"] = "compact"
        self.assertEqual(second["education"]["preset"], "classic")

    def test_unknown_values_and_numbers_are_normalized(self):
        config = normalize_layout_config({
            "global": {"density": "wild", "fontSize": 99, "lineHeight": 0},
            "education": {"preset": "floating", "schoolTagStyle": "neon"},
        })
        self.assertEqual(config["global"]["density"], "compact")
        self.assertEqual(config["global"]["fontSize"], 11.5)
        self.assertEqual(config["global"]["lineHeight"], 1.1)
        self.assertEqual(config["education"]["preset"], "classic")
        self.assertEqual(config["education"]["schoolTagStyle"], "filled")

    def test_typography_is_recorded_and_unknown_fonts_cannot_split_renderers(self):
        config = normalize_layout_config({
            "version": 2,
            "typography": {
                "preset": "unknown",
                "latinFont": "Random Latin",
                "eastAsiaFont": "Random CJK",
            },
        })
        self.assertEqual(config["version"], 5)
        self.assertEqual(config["typography"]["preset"], "microsoft-office")
        self.assertEqual(config["typography"]["latinFont"], "Arial")
        self.assertEqual(config["typography"]["eastAsiaFont"], "Microsoft YaHei")

    def test_v3_default_visual_scale_migrates_to_v4_semantic_body_size(self):
        config = normalize_layout_config({
            "version": 3,
            "global": {"fontSize": 10.5, "lineHeight": 1.32, "moduleMargin": 0.45},
        })
        self.assertEqual(config["version"], 5)
        self.assertEqual(config["global"]["fontSize"], 9)
        self.assertEqual(config["global"]["lineHeight"], 1.28)
        self.assertEqual(config["global"]["moduleMargin"], 0.55)
        self.assertEqual(config["typography"]["fontSizes"], {
            "name": 14, "sectionTitle": 11, "entryTitle": 10,
            "meta": 9, "body": 9, "label": 9,
        })

    def test_v4_layout_migrates_to_explicit_semantic_font_sizes_without_visual_change(self):
        config = normalize_layout_config({
            "version": 4,
            "global": {"fontSize": 9.5},
        })
        self.assertEqual(config["version"], 5)
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
        self.assertEqual(config["global"]["lineHeight"], 1.28)
        self.assertEqual(config["global"]["moduleMargin"], 0.55)
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

    def test_curated_template_reuses_presets_and_preserves_content_visibility(self):
        config = default_layout_config()
        config["global"]["hiddenSections"] = ["self_evaluation"]
        config["basics"]["hiddenFields"] = ["gender"]
        result = apply_layout_template(config, "modern-clean")
        self.assertEqual(result["basics"]["preset"], "left-aligned")
        self.assertEqual(result["education"]["preset"], "three-column")
        self.assertEqual(result["education"]["schoolTagStyle"], "text")
        self.assertEqual(result["global"]["hiddenSections"], ["self_evaluation"])
        self.assertEqual(result["basics"]["hiddenFields"], ["gender"])

    def test_all_curated_templates_resolve_to_supported_module_presets(self):
        expected = {
            "classic-professional": ("centered", "classic", "classic"),
            "modern-clean": ("left-aligned", "three-column", "classic"),
            "compact-tech": ("left-aligned", "compact", "compact"),
        }
        self.assertEqual(set(LAYOUT_TEMPLATES), set(expected))
        for template_id, presets in expected.items():
            result = apply_layout_template(default_layout_config(), template_id)
            self.assertEqual(
                (result["basics"]["preset"], result["education"]["preset"], result["work_experience"]["preset"]),
                presets,
            )

    def test_layout_changes_are_atomic_per_module(self):
        before = default_layout_config()
        after = default_layout_config()
        after["education"].update({"preset": "three-column", "schoolTagStyle": "text"})
        after["self_evaluation"]["preset"] = "bullets"
        changes = build_layout_changes(before, after)
        self.assertEqual({change["id"] for change in changes}, {"layout-education", "layout-self_evaluation"})
        education_change = next(change for change in changes if change["id"] == "layout-education")
        labels = {detail["field_label"] for detail in education_change["details"]}
        self.assertEqual(labels, {"教育信息布局", "学校标签样式", "成绩信息位置"})
        selected = apply_layout_change_groups(before, after, ["layout-education"])
        self.assertEqual(selected["education"]["preset"], "three-column")
        self.assertEqual(selected["self_evaluation"]["preset"], "paragraphs")

    def test_reset_one_module_preserves_other_overrides(self):
        config = default_layout_config()
        config["education"]["preset"] = "compact"
        config["others"]["preset"] = "tags"
        reset = reset_layout_section(config, "education")
        self.assertEqual(reset["education"]["preset"], "classic")
        self.assertEqual(reset["others"]["preset"], "tags")


if __name__ == "__main__":
    unittest.main()
