import io
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from database.models import connection, init_db
from routes.reports import reports_bp


class ReportUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = self.temp_dir.name + "/healthcare.sqlite3"
        init_db(self.database)
        with connection(self.database) as db:
            db.execute("INSERT INTO users(id,email,password_hash) VALUES(1,'patient@example.test','test-hash')")
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test-only", DATABASE_PATH=self.database)
        app.register_blueprint(reports_bp)

        @app.get("/")
        def index():
            return "sign in"

        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_file_with_mismatched_signature(self):
        response = self.client.post("/upload", data={
            "file": (io.BytesIO(b"not a pdf"), "blood-test.pdf"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertIn("file contents do not match", session["_flashes"][0][1])
        with connection(self.database) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 0)

    @patch("ai.file_explanation.extract_report_text", return_value="Hemoglobin 10 g/dL (12 - 16)")
    def test_saves_supported_pdf_to_the_signed_in_patient(self, _extract):
        response = self.client.post("/upload", data={
            "file": (io.BytesIO(b"%PDF-1.4 report data"), "blood-test.pdf"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        with connection(self.database) as db:
            report = db.execute("SELECT user_id,title,content,mime_type FROM reports").fetchone()
        self.assertEqual(tuple(report), (1, "blood-test.pdf", "Hemoglobin 10 g/dL (12 - 16)", "application/pdf"))


if __name__ == "__main__":
    unittest.main()
