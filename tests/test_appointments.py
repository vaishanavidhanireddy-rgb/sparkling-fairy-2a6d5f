import csv
import io
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from flask import Flask

from database.appointment_imports import read_geography_csv
from database.models import connection, init_db
from routes.appointments import appointments_bp
from scripts.import_appointment_data import import_files


class AppointmentDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "test.sqlite3"
        init_db(self.database)
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test-only", DATABASE_PATH=str(self.database), HOSPITAL_ADMIN_EMAILS=set())
        app.register_blueprint(appointments_bp)

        @app.get("/")
        def index():
            return "sign in"

        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["email"] = "patient@example.test"

    def tearDown(self):
        self.client = None
        self.temp_dir.cleanup()

    def _write_csv(self, name, fieldnames, rows):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _import_test_fixture(self):
        geography = self._write_csv("lgd_test.csv", [
            "State Name in English", "District Name in English",
            "Local Body Name in English", "Local Body Code", "Pin Code",
        ], [{"State Name in English": "Test State", "District Name in English": "Test District",
             "Local Body Name in English": "Test City", "Local Body Code": "TEST-ULB-1",
             "Pin Code": "123456"}])
        hospitals = self._write_csv("ogd_test.csv", [
            "Sr_No", "Hospital_Name", "State", "District", "Town", "Location",
            "Address_Original_First_Line", "Telephone", "Hospital_Category",
            "Hospital_Care_Type", "Specialties", "Pincode", "Location_Coordinates",
        ], [{"Sr_No": "TEST-HOSP-1", "Hospital_Name": "Synthetic Test Clinic",
             "State": "Test State", "District": "Test District", "Town": "Test City",
             "Location": "Test Road", "Address_Original_First_Line": "Test Road",
             "Telephone": "0000000000", "Hospital_Category": "Test fixture",
             "Hospital_Care_Type": "Test only", "Specialties": "Test only",
             "Pincode": "123456", "Location_Coordinates": ""}])
        doctors = self._write_csv("nmc_test.csv", [
            "hospital_name", "state", "district", "city", "doctor_name", "specialty",
            "registration_number", "verification_status", "verification_url",
        ], [{"hospital_name": "Synthetic Test Clinic", "state": "Test State",
             "district": "Test District", "city": "Test City", "doctor_name": "Synthetic Test Doctor",
             "specialty": "Test only", "registration_number": "TEST-REG-1",
             "verification_status": "verified", "verification_url": "https://nmr.nmc.org.in/search-doctor"}])
        return geography, hospitals, doctors

    def test_sequential_api_cascade_returns_expected_json(self):
        geography, hospitals, doctors = self._import_test_fixture()
        import_files(self.database, geography, hospitals, doctors)

        states = self.client.get("/api/appointments/states").get_json()
        self.assertEqual(states, {"items": [{"name": "Test State"}]})
        districts = self.client.get("/api/appointments/districts?state=Test%20State").get_json()
        self.assertEqual(districts, {"items": [{"name": "Test District"}]})
        cities = self.client.get("/api/appointments/cities?state=Test%20State&district=Test%20District").get_json()
        self.assertEqual(cities, {"items": [{"name": "Test City"}]})
        hospitals_response = self.client.get(
            "/api/appointments/hospitals?state=Test%20State&district=Test%20District&city=Test%20City"
        ).get_json()
        self.assertEqual(len(hospitals_response["items"]), 1)
        hospital = hospitals_response["items"][0]
        self.assertEqual(hospital["hospital_name"], "Synthetic Test Clinic")
        doctors_response = self.client.get(f"/api/appointments/hospitals/{hospital['id']}/doctors").get_json()
        self.assertEqual(doctors_response["items"][0]["doctor_name"], "Synthetic Test Doctor")
        self.assertEqual(doctors_response["items"][0]["verification_status"], "verified")

    def test_geography_remains_available_without_hospitals(self):
        geography, _, _ = self._import_test_fixture()
        import_files(self.database, geography_path=geography)
        self.assertEqual(self.client.get("/api/appointments/states").get_json(), {"items": [{"name": "Test State"}]})
        response = self.client.get(
            "/api/appointments/hospitals?state=Test%20State&district=Test%20District&city=Test%20City"
        )
        self.assertEqual(response.get_json(), {"items": []})

    def test_lgd_state_and_district_files_populate_independently_of_city_hospitals(self):
        states = self._write_csv("states.csv", ["State Name in English", "State Code"], [
            {"State Name in English": "Test State", "State Code": "TS"},
        ])
        districts = self._write_csv("districts.csv", ["State Code", "District Name in English", "District Code"], [
            {"State Code": "TS", "District Name in English": "Test District", "District Code": "TD"},
        ])
        counts = import_files(self.database, states_path=states, districts_path=districts)
        self.assertEqual(counts["states"], 1)
        self.assertEqual(counts["districts"], 1)
        self.assertEqual(self.client.get("/api/appointments/states").get_json(), {"items": [{"name": "Test State"}]})
        self.assertEqual(self.client.get("/api/appointments/districts?state=Test%20State").get_json(),
                         {"items": [{"name": "Test District"}]})

    def test_hospital_without_town_uses_only_a_unique_lgd_pin_match(self):
        geography, _, doctors = self._import_test_fixture()
        hospitals = self._write_csv("hospital_without_town.csv", [
            "Sr_No", "Hospital_Name", "State", "District", "Town", "Pincode",
        ], [{"Sr_No": "TEST-HOSP-2", "Hospital_Name": "Synthetic Test Clinic",
             "State": "Test State", "District": "Test District", "Town": "0", "Pincode": "123456"}])
        import_files(self.database, geography, hospitals, doctors)
        response = self.client.get(
            "/api/appointments/hospitals?state=Test%20State&district=Test%20District&city=Test%20City"
        ).get_json()
        self.assertEqual(response["items"][0]["city"], "Test City")

    def test_admin_hospital_upload_uses_the_same_ogd_parser_and_city_match(self):
        geography, _, _ = self._import_test_fixture()
        import_files(self.database, geography_path=geography)
        self.client.application.config["HOSPITAL_ADMIN_EMAILS"] = {"patient@example.test"}
        source = self._write_csv("official-upload.csv", [
            "Sr_No", "Hospital_Name", "State", "District", "Town", "Pincode",
        ], [{"Sr_No": "TEST-UPLOAD-1", "Hospital_Name": "Synthetic Upload Clinic",
             "State": "Test State", "District": "Test District", "Town": "0", "Pincode": "123456"}])
        response = self.client.post("/appointments/directory/upload", data={
            "directory_file": (io.BytesIO(source.read_bytes()), "official.csv"),
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        hospitals = self.client.get(
            "/api/appointments/hospitals?state=Test%20State&district=Test%20District&city=Test%20City"
        ).get_json()["items"]
        self.assertEqual(hospitals[0]["hospital_name"], "Synthetic Upload Clinic")

    def test_schema_migration_preserves_existing_user_and_legacy_hospital_rows(self):
        db = sqlite3.connect(self.database)
        try:
            db.execute("INSERT INTO users(email,password_hash) VALUES('saved@example.test','hash')")
            db.execute("CREATE TABLE hospitals (id INTEGER PRIMARY KEY, name TEXT, state TEXT, area TEXT, status TEXT)")
            db.execute("INSERT INTO hospitals(name,state,area,status) VALUES('Legacy listing','Old State','Old Area','approved')")
            db.commit()
        finally:
            db.close()

        init_db(self.database)
        db = sqlite3.connect(self.database)
        try:
            self.assertEqual(db.execute("SELECT email FROM users").fetchone()[0], "saved@example.test")
            self.assertEqual(db.execute("SELECT name FROM hospitals").fetchone()[0], "Legacy listing")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM appointment_hospitals").fetchone()[0], 0)
        finally:
            db.close()

    def test_doctors_must_match_a_hospital_and_import_is_atomic(self):
        geography, hospitals, doctors = self._import_test_fixture()
        invalid = self._write_csv("invalid_doctor.csv", [
            "hospital_name", "state", "district", "city", "doctor_name",
        ], [{"hospital_name": "Unknown Clinic", "state": "Test State", "district": "Test District",
             "city": "Test City", "doctor_name": "Synthetic Test Doctor"}])
        with self.assertRaisesRegex(ValueError, "does not match an imported hospital"):
            import_files(self.database, geography, hospitals, invalid)
        with connection(self.database) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM appointment_locations WHERE active=1").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM appointment_hospitals").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM appointment_doctors").fetchone()[0], 0)

    def test_invalid_geography_headers_fail_before_writing(self):
        path = self._write_csv("bad.csv", ["foo", "bar"], [{"foo": "A", "bar": "B"}])
        with self.assertRaisesRegex(ValueError, "Geography CSV needs"):
            read_geography_csv(path)
        with connection(self.database) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM appointment_locations").fetchone()[0], 0)

    def test_api_requires_login(self):
        response = self.client.application.test_client().get("/api/appointments/states")
        self.assertEqual(response.status_code, 302)

    def test_doctor_directory_search_and_empty_response(self):
        empty = self.client.get("/api/appointments/doctors")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.get_json(), {"items": [], "specialties": []})

        geography, hospitals, doctors = self._import_test_fixture()
        import_files(self.database, geography, hospitals, doctors)
        result = self.client.get("/api/appointments/doctors?q=Synthetic&specialty=Test%20only")
        self.assertEqual(result.status_code, 200)
        payload = result.get_json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["doctor_name"], "Synthetic Test Doctor")
        self.assertEqual(payload["items"][0]["hospital_name"], "Synthetic Test Clinic")
        self.assertEqual(payload["specialties"], ["Test only"])

    def test_cascade_api_validation_returns_json_errors(self):
        response = self.client.get("/api/appointments/districts")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Choose a state first."})

    def test_booking_saves_request_for_the_selected_hospital_and_doctor(self):
        geography, hospitals, doctors = self._import_test_fixture()
        import_files(self.database, geography, hospitals, doctors)
        with connection(self.database) as db:
            db.execute("INSERT INTO users(id,email,password_hash) VALUES(1,'patient@example.test','test-hash')")
            hospital_id = db.execute("SELECT id FROM appointment_hospitals").fetchone()[0]
            doctor_id = db.execute("SELECT id FROM appointment_doctors").fetchone()[0]
        response = self.client.post("/appointments/book", data={
            "hospital_id": str(hospital_id), "doctor_id": str(doctor_id),
            "appointment_date": (date.today() + timedelta(days=2)).isoformat(), "time_slot": "morning",
        })
        self.assertEqual(response.status_code, 302)
        with connection(self.database) as db:
            saved = db.execute("SELECT hospital_id,doctor_id,booking_mode,status FROM appointment_requests").fetchone()
        self.assertEqual(tuple(saved), (hospital_id, doctor_id, "demo_request", "demo_pending"))


if __name__ == "__main__":
    unittest.main()
