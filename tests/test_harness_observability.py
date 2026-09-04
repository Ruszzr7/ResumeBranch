import unittest

from backend.harness.observability import HarnessMetrics


class HarnessObservabilityTests(unittest.TestCase):
    def test_counters_are_whitelisted_and_data_free(self):
        metrics = HarnessMetrics()
        metrics.increment("resume_coach_turns_total")
        metrics.increment("resume_coach_errors_total", 3)
        metrics.increment("resume_visual_render_fallbacks_total")
        metrics.increment("resume_visual_model_fallbacks_total")
        metrics.increment("resume_visual_render_failures_total")
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["resume_coach_turns_total"], 1)
        self.assertEqual(snapshot["resume_coach_errors_total"], 3)
        self.assertEqual(snapshot["resume_visual_render_fallbacks_total"], 1)
        self.assertEqual(snapshot["resume_visual_model_fallbacks_total"], 1)
        self.assertEqual(snapshot["resume_visual_render_failures_total"], 1)
        self.assertNotIn("email", " ".join(snapshot))
        with self.assertRaises(ValueError):
            metrics.increment("user_email")


if __name__ == "__main__":
    unittest.main()
