import unittest

from backend.layout_config import (
    apply_density,
    apply_layout_change_groups,
    build_layout_changes,
    default_layout_config,
    normalize_layout_config,
    reset_layout_section,
)


class LayoutConfigTests(unittest.TestCase):
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
        self.assertEqual(config["global"]["density"], "standard")
        self.assertEqual(config["global"]["fontSize"], 14)
        self.assertEqual(config["global"]["lineHeight"], 1.1)
        self.assertEqual(config["education"]["preset"], "classic")
        self.assertEqual(config["education"]["schoolTagStyle"], "filled")

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
        self.assertEqual(config["global"]["fontSize"], 10)
        self.assertEqual(config["global"]["lineHeight"], 1.3)

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
