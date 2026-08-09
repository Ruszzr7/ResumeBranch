import unittest
from io import BytesIO
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, ProjectTask, ResumeProject, attach_source_document, discard_pending_source_document, get_source_document
from backend.source_documents import (
    detect_source_page_count,
    persist_source_document,
    remove_source_document_file,
    source_document_path,
)


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


    def test_source_file_is_private_pending_then_attached_to_task(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        project = ResumeProject(id="project", user_id=1, title="resume")
        task = ProjectTask(id="task", project_id="project", user_id=1, title="base", session_id="task", is_base=True)
        db.add_all([project, task])
        db.commit()
        try:
            with TemporaryDirectory() as directory, patch.dict(os.environ, {"SOURCE_DOCUMENT_DIR": directory}):
                document = persist_source_document(db, 1, b"%PDF-source", "application/pdf", "../resume.pdf")
                self.assertEqual(document.status, "pending")
                self.assertEqual(document.original_filename, "resume.pdf")
                self.assertTrue(source_document_path(document.storage_key).is_file())
                self.assertIsNone(get_source_document(db, 2, document.id))
                attached = attach_source_document(db, 1, document.id, task_id="task")
                self.assertEqual(attached.status, "ready")
                db.refresh(task)
                self.assertEqual(task.source_document_id, document.id)
                remove_source_document_file(document.storage_key)
                self.assertFalse(os.path.exists(os.path.join(directory, document.storage_key)))
        finally:
            db.close()

    def test_cancelled_pending_source_removes_metadata(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            with TemporaryDirectory() as directory, patch.dict(os.environ, {"SOURCE_DOCUMENT_DIR": directory}):
                document = persist_source_document(db, 1, b"image", "image/png", "resume.png")
                storage_key = discard_pending_source_document(db, 1, document.id)
                self.assertEqual(storage_key, document.storage_key)
                remove_source_document_file(storage_key)
                self.assertFalse(os.path.exists(os.path.join(directory, storage_key)))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
