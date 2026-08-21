import os
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from backend.pdf_generator import generate_pdf, render_resume_to_html
from backend.pdf_renderer import (
    PDF_BROWSER_ENV,
    PDF_NO_SANDBOX_ENV,
    find_pdf_browser,
    render_html_with_chromium,
)


def pdf_with_pages(count: int) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=595, height=842)
    writer.write(output)
    return output.getvalue()


class PdfRendererTests(unittest.TestCase):
    def test_configured_browser_path_takes_precedence(self):
        with TemporaryDirectory() as temp_dir:
            browser = Path(temp_dir) / "browser.exe"
            browser.touch()
            with patch.dict(os.environ, {PDF_BROWSER_ENV: str(browser)}):
                self.assertEqual(find_pdf_browser(), str(browser.resolve()))

    def test_chromium_command_uses_isolated_profile_and_suppresses_headers(self):
        with TemporaryDirectory() as temp_dir:
            browser = Path(temp_dir) / "browser.exe"
            browser.touch()

            def fake_run(command, **kwargs):
                output = next(value.split("=", 1)[1] for value in command if value.startswith("--print-to-pdf="))
                Path(output).write_bytes(pdf_with_pages(1))
                return type("Completed", (), {"returncode": 0, "stderr": b""})()

            with patch("backend.pdf_renderer.subprocess.run", side_effect=fake_run) as run:
                result = render_html_with_chromium("<html><body>test</body></html>", browser_path=str(browser))

            self.assertEqual(len(PdfReader(BytesIO(result)).pages), 1)
            command = run.call_args.args[0]
            self.assertIn("--headless=new", command)
            self.assertIn("--no-pdf-header-footer", command)
            self.assertTrue(any(value.startswith("--user-data-dir=") for value in command))

    def test_no_sandbox_is_opted_into_by_the_docker_profile(self):
        with TemporaryDirectory() as temp_dir:
            browser = Path(temp_dir) / "browser.exe"
            browser.touch()

            def fake_run(command, **kwargs):
                output = next(value.split("=", 1)[1] for value in command if value.startswith("--print-to-pdf="))
                Path(output).write_bytes(pdf_with_pages(1))
                return type("Completed", (), {"returncode": 0, "stderr": b""})()

            with (
                patch.dict(os.environ, {PDF_NO_SANDBOX_ENV: "true"}),
                patch("backend.pdf_renderer.subprocess.run", side_effect=fake_run) as run,
            ):
                render_html_with_chromium("<html><body>test</body></html>", browser_path=str(browser))

            self.assertIn("--no-sandbox", run.call_args.args[0])

    def test_missing_browser_fails_with_installation_guidance(self):
        with patch("backend.pdf_renderer.find_pdf_browser", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Chrome、Edge 或 Chromium"):
                render_html_with_chromium("<html><body>test</body></html>")

    def test_browser_failure_does_not_switch_rendering_engines(self):
        with TemporaryDirectory() as temp_dir:
            browser = Path(temp_dir) / "browser.exe"
            browser.touch()
            completed = type("Completed", (), {"returncode": 1, "stderr": b"failed"})()
            with patch("backend.pdf_renderer.subprocess.run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "Chromium PDF"):
                    render_html_with_chromium("<html><body>test</body></html>", browser_path=str(browser))

    def test_generate_pdf_prefers_browser_and_applies_two_page_limit(self):
        with patch("backend.pdf_generator.render_html_with_chromium", return_value=pdf_with_pages(2)):
            result = generate_pdf({"basics": {"name": "测试"}})
        self.assertEqual(len(PdfReader(BytesIO(result)).pages), 2)

        with patch("backend.pdf_generator.render_html_with_chromium", return_value=pdf_with_pages(3)):
            with self.assertRaisesRegex(ValueError, "两页"):
                generate_pdf({"basics": {"name": "测试"}})

    def test_punctuation_codepoints_are_preserved_in_pdf_html(self):
        punctuation_sample = "中文，句号。分号；冒号：括号（）/ ASCII,.;:!?() RL部署经验"
        html = render_resume_to_html({
            "basics": {"name": "标点测试"},
            "self_evaluation": [punctuation_sample],
        })
        self.assertIn(punctuation_sample, html)
        self.assertIn('font-family: "Arial", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;', html)


if __name__ == "__main__":
    unittest.main()
