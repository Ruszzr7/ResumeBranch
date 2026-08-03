import unittest
from io import BytesIO

from pypdf import PdfWriter

from backend.source_documents import detect_source_page_count


class SourceDocumentTests(unittest.TestCase):
    def test_image_source_is_one_page(self):
        self.assertEqual(detect_source_page_count(b"image", "image/png"), 1)

    def test_pdf_source_uses_real_page_count(self):
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.add_blank_page(width=595, height=842)
        output = BytesIO()
        writer.write(output)
        self.assertEqual(
            detect_source_page_count(output.getvalue(), "application/pdf"),
            2,
        )

    def test_empty_pdf_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "为空"):
            detect_source_page_count(b"", "application/pdf")


if __name__ == "__main__":
    unittest.main()
