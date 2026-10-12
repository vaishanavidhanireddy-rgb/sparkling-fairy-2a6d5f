import unittest
import tempfile
from unittest.mock import patch

from flask import Flask

from routes.reports import reports_bp
from database.models import connection, init_db


class AssistantApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = self.temp_dir.name + "/test.sqlite3"
        init_db(self.database)
        with connection(self.database) as db:
            db.execute("INSERT INTO users(id,email,password_hash) VALUES(4,'patient@example.test','test-hash')")
            db.execute("INSERT INTO reports(user_id,title,content) VALUES(4,'Blood test','Hemoglobin 10 g/dL (12 - 16)\nGlucose 90 mg/dL (70 - 100)')")
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test-only", DATABASE_PATH=self.database, MISTRAL_API_KEY="server-secret")
        app.register_blueprint(reports_bp)

        @app.get("/")
        def index():
            return "sign in"

        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 4

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_assistant_rejects_invalid_json_and_empty_question(self):
        invalid = self.client.post("/api/assistant", data="not json", content_type="text/plain")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.get_json(), {"error": "Send a JSON object with a question."})

        empty = self.client.post("/api/assistant", json={"question": "  "})
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.get_json(), {"error": "Enter a question first."})

    @patch("routes.reports.explain_symptom", return_value="A plain-language explanation.")
    def test_assistant_calls_existing_ai_service_without_returning_secret(self, explain):
        response = self.client.post("/api/assistant", json={"question": "What does this term mean?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"answer": "A plain-language explanation."})
        explain.assert_called_once_with("What does this term mean?", "server-secret", model="ministral-14b-latest")
        self.assertNotIn("server-secret", response.get_data(as_text=True))

    @patch("routes.reports.explain_symptom", side_effect=RuntimeError("AI provider is unavailable."))
    def test_assistant_provider_errors_are_json(self, _explain):
        response = self.client.post("/api/assistant", json={"question": "Explain a report."})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "AI provider is unavailable."})

    @patch("routes.reports.answer_report_question", return_value="Context-aware answer.")
    def test_assistant_uses_only_the_signed_in_users_selected_report(self, answer):
        response = self.client.post("/api/assistant", json={"question": "Explain hemoglobin", "report_id": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"answer": "Context-aware answer."})
        answer.assert_called_once_with("Explain hemoglobin", "Blood test",
                                       "Hemoglobin 10 g/dL (12 - 16)\nGlucose 90 mg/dL (70 - 100)",
                                       "server-secret", model="ministral-14b-latest")
        missing = self.client.post("/api/assistant", json={"question": "Read this", "report_id": 999})
        self.assertEqual(missing.status_code, 404)

    def test_health_insights_uses_explicit_ranges_and_date_filters(self):
        response = self.client.get("/api/health-insights")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["abnormal_count"], 1)
        hemoglobin = next(row for row in payload["items"] if row["name"] == "Hemoglobin")
        self.assertTrue(hemoglobin["abnormal"])
        self.assertEqual(hemoglobin["reference_range"], "12 - 16")
        filtered = self.client.get("/api/health-insights?biomarker=Glucose&from=2999-01-01")
        self.assertEqual(filtered.get_json()["items"], [])
        invalid = self.client.get("/api/health-insights?from=not-a-date")
        self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
