import base64
import unittest

from backend.multimodal_files import build_file_message_part


class MultimodalFileTests(unittest.TestCase):
    def test_pdf_is_sent_as_original_application_pdf_data_url(self):
        original = b"%PDF-1.7\noriginal-vector-and-text-content"

        part = build_file_message_part(original, "application/pdf")

        self.assertEqual(part["type"], "image_url")
        url = part["image_url"]["url"]
        self.assertTrue(url.startswith("data:application/pdf;base64,"))
        encoded = url.split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded), original)
        self.assertNotIn("image/png", url)

    def test_initial_upload_keeps_supported_image_types(self):
        part = build_file_message_part(b"png", "image/png", normalize_image_type=True)
        self.assertTrue(part["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_initial_upload_normalizes_other_images_to_jpeg_like_original(self):
        part = build_file_message_part(b"gif", "image/gif", normalize_image_type=True)
        self.assertTrue(part["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_rejects_unsupported_files(self):
        with self.assertRaisesRegex(ValueError, "只支持图片或PDF文件"):
            build_file_message_part(b"text", "text/plain")


if __name__ == "__main__":
    unittest.main()
