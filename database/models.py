"""SQLite and PostgreSQL persistence layer for the healthcare app."""
import os
import json
import re
import sqlite3
from contextlib import contextmanager
from html import unescape
from pathlib import Path


POSTGRES_SCHEMA_MIGRATIONS = (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS state TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS area TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS country TEXT NOT NULL DEFAULT 'India'",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS explanation TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS file_data BYTEA",
    "ALTER TABLE reports ADD COLUMN IF NOT EXISTS mime_type TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE wellness_logs ADD COLUMN IF NOT EXISTS focus TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS care_type TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS specialties TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS pincode TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS coordinates TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'admin_uploaded'",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS source_record_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS source_url TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_hospitals ADD COLUMN IF NOT EXISTS imported_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_locations ADD COLUMN IF NOT EXISTS pincodes TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_requests ADD COLUMN IF NOT EXISTS doctor_id INTEGER REFERENCES appointment_doctors(id) ON DELETE SET NULL",
    "ALTER TABLE appointment_requests ADD COLUMN IF NOT EXISTS appointment_date TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE appointment_requests ADD COLUMN IF NOT EXISTS time_slot TEXT NOT NULL DEFAULT 'any'",
    "ALTER TABLE appointment_requests ADD COLUMN IF NOT EXISTS booking_key TEXT",
    "ALTER TABLE appointment_requests ADD COLUMN IF NOT EXISTS booking_mode TEXT NOT NULL DEFAULT 'demo_request'",
    "UPDATE appointment_requests SET booking_mode='legacy_request' WHERE booking_key IS NULL AND appointment_date='' AND booking_mode='demo_request'",
    "CREATE UNIQUE INDEX IF NOT EXISTS appointment_request_dedupe ON appointment_requests(booking_key) WHERE booking_key IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS users_firebase_uid ON users(firebase_uid)",
)


def _is_postgres(path):
    return bool(os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))) or (
        isinstance(path, str) and path.startswith(("postgres://", "postgresql://"))
    )


def _postgres_sql(statement, returning_id=False):
    if re.match(r"\s*SELECT\b", statement, flags=re.IGNORECASE):
        statement = re.sub(
            r"([\w.]+)\s*=\s*\?\s+COLLATE\s+NOCASE",
            r"LOWER(\1) = LOWER(?)",
            statement,
            flags=re.IGNORECASE,
        )
        statement = re.sub(
            r"([\w.]+)\s+COLLATE\s+NOCASE",
            r"LOWER(\1)",
            statement,
            flags=re.IGNORECASE,
        )
    statement = re.sub(r"\bCOLLATE\s+NOCASE\b", "", statement, flags=re.IGNORECASE)
    statement = re.sub(r"\bLIKE\b", "ILIKE", statement, flags=re.IGNORECASE)
    statement = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        statement,
        flags=re.IGNORECASE,
    )
    statement = re.sub(r"\bBLOB\b", "BYTEA", statement, flags=re.IGNORECASE)
    statement = re.sub(
        r"\bDEFAULT\s+CURRENT_TIMESTAMP\b",
        "DEFAULT CURRENT_TIMESTAMP::TEXT",
        statement,
        flags=re.IGNORECASE,
    )
    statement = statement.replace("?", "%s").strip().rstrip(";")
    if returning_id and re.match(r"INSERT\s+INTO\b", statement, flags=re.IGNORECASE) and not re.search(
        r"\bRETURNING\b", statement, flags=re.IGNORECASE
    ):
        statement += " RETURNING id"
    return statement


class _PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def lastrowid(self):
        row = self._cursor.fetchone()
        return row["id"] if row else None

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=()):
        cursor = self._connection.cursor()
        cursor.execute(_postgres_sql(statement, returning_id=True), parameters)
        return _PostgresCursor(cursor)

    def executemany(self, statement, parameters):
        cursor = self._connection.cursor()
        cursor.executemany(_postgres_sql(statement), parameters)
        return _PostgresCursor(cursor)

    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def _postgres_connection(database_url):
    try:
        import psycopg2
    except ImportError as error:
        raise RuntimeError("Install psycopg2-binary to use DATABASE_URL with PostgreSQL.") from error
    from psycopg2.extras import DictCursor

    return _PostgresConnection(psycopg2.connect(database_url, cursor_factory=DictCursor))


def _appointment_directory_needs_seed(db):
    """Return True when the bundled directory has not yet been loaded for this database."""
    for table in ("appointment_states", "appointment_districts", "appointment_locations", "appointment_hospitals"):
        try:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            return True
        if count == 0:
            return True
    return False


def _seed_attached_appointment_directory(db):
    """Load the bundled hospital finder directory into the appointment tables."""
    data_path = Path(__file__).with_name("appointment_directory.json")
    if not data_path.is_file():
        return
    data = json.loads(data_path.read_text(encoding="utf-8-sig"))
    source_url = "bundled:find-hospital-final.html"

    states = {row["id"]: unescape(row["name"]).strip() for row in data["states"]}
    districts = {row["id"]: (states[row["stateId"]], unescape(row["name"]).strip())
                 for row in data["districts"]}
    cities = {row["id"]: (districts[row["districtId"]][0], districts[row["districtId"]][1],
                           unescape(row["name"]).strip()) for row in data["cities"]}

    db.executemany(
        "INSERT INTO appointment_states(state,source_code,source_url,active) VALUES(?,?,?,1) ON CONFLICT DO NOTHING",
        [(name, f"attached-{state_id}", source_url) for state_id, name in states.items()],
    )
    db.executemany(
        "INSERT INTO appointment_districts(state,district,source_code,source_url,active) VALUES(?,?,?,?,1) ON CONFLICT DO NOTHING",
        [(state, district, f"attached-{district_id}", source_url)
         for district_id, (state, district) in districts.items()],
    )
    db.executemany(
        "INSERT INTO appointment_locations(state,district,city,source_code,source_url,active) VALUES(?,?,?,?,?,1) ON CONFLICT DO NOTHING",
        [(state, district, city, f"attached-{city_id}", source_url)
         for city_id, (state, district, city) in cities.items()],
    )

    hospital_rows = []
    for row in data["hospitals"]:
        state, district, city = cities[row["cityId"]]
        name = unescape(row["name"]).strip()
        address = unescape(row.get("address", "")).strip()
        hospital_rows.append((
            name, state, district, city, address, address,
            unescape(row.get("phone", "")).strip(), "", "", "", "", "",
            "attached_directory", str(row["id"]), source_url,
        ))
    db.executemany(
        """INSERT INTO appointment_hospitals
           (hospital_name,state,district,city,area,address,phone,category,care_type,specialties,pincode,
            coordinates,source_type,source_record_id,source_url)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(hospital_name,state,district,city,area) DO NOTHING""",
        hospital_rows,
    )


def init_db(path):
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url and not database_url.startswith(("postgres://", "postgresql://")):
        raise ValueError("DATABASE_URL must be a PostgreSQL connection URL.")
    if _is_postgres(path):
        database_url = database_url or path
        db = _postgres_connection(database_url)
        try:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    explanation TEXT NOT NULL DEFAULT '',
                    file_data BLOB,
                    mime_type TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    reminder_time TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS wellness_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    log_date TEXT NOT NULL,
                    water_glasses INTEGER NOT NULL DEFAULT 0,
                    sleep_hours REAL NOT NULL DEFAULT 0,
                    exercise_minutes INTEGER NOT NULL DEFAULT 0,
                    steps INTEGER NOT NULL DEFAULT 0,
                    focus TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, log_date)
                );
                CREATE TABLE IF NOT EXISTS appointment_hospitals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hospital_name TEXT COLLATE NOCASE NOT NULL,
                    state TEXT COLLATE NOCASE NOT NULL,
                    district TEXT COLLATE NOCASE NOT NULL,
                    city TEXT COLLATE NOCASE NOT NULL,
                    area TEXT COLLATE NOCASE NOT NULL,
                    address TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    care_type TEXT NOT NULL DEFAULT '',
                    specialties TEXT NOT NULL DEFAULT '',
                    pincode TEXT NOT NULL DEFAULT '',
                    coordinates TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'admin_uploaded',
                    source_record_id TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(hospital_name, state, district, city, area)
                );
                CREATE INDEX IF NOT EXISTS appointment_hospitals_location
                    ON appointment_hospitals(state, district, city, area);
                CREATE TABLE IF NOT EXISTS appointment_locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state TEXT COLLATE NOCASE NOT NULL,
                    district TEXT COLLATE NOCASE NOT NULL,
                    city TEXT COLLATE NOCASE NOT NULL,
                    source_code TEXT NOT NULL DEFAULT '',
                    pincodes TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(state, district, city)
                );
                CREATE INDEX IF NOT EXISTS appointment_locations_parent
                    ON appointment_locations(state, district, city);
                CREATE TABLE IF NOT EXISTS appointment_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state TEXT COLLATE NOCASE NOT NULL UNIQUE,
                    source_code TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS appointment_districts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state TEXT COLLATE NOCASE NOT NULL,
                    district TEXT COLLATE NOCASE NOT NULL,
                    source_code TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(state, district)
                );
                CREATE INDEX IF NOT EXISTS appointment_districts_parent
                    ON appointment_districts(state, district);
                CREATE TABLE IF NOT EXISTS appointment_doctors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hospital_id INTEGER NOT NULL REFERENCES appointment_hospitals(id) ON DELETE CASCADE,
                    doctor_name TEXT COLLATE NOCASE NOT NULL,
                    specialty TEXT NOT NULL DEFAULT '',
                    registration_number TEXT NOT NULL DEFAULT '',
                    verification_url TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL DEFAULT 'unverified',
                    source_type TEXT NOT NULL DEFAULT 'admin_uploaded',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(hospital_id, doctor_name, registration_number)
                );
                CREATE INDEX IF NOT EXISTS doctors_by_hospital
                    ON appointment_doctors(hospital_id, doctor_name);
                CREATE TABLE IF NOT EXISTS appointment_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    hospital_id INTEGER NOT NULL REFERENCES appointment_hospitals(id) ON DELETE CASCADE,
                    doctor_id INTEGER REFERENCES appointment_doctors(id) ON DELETE SET NULL,
                    appointment_date TEXT NOT NULL DEFAULT '',
                    time_slot TEXT NOT NULL DEFAULT 'any',
                    booking_key TEXT,
                    booking_mode TEXT NOT NULL DEFAULT 'demo_request',
                    appointment_at TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS appointments_by_user
                    ON appointment_requests(user_id, appointment_at);
            """)
            for statement in POSTGRES_SCHEMA_MIGRATIONS:
                db.execute(statement)
            if _appointment_directory_needs_seed(db):
                _seed_attached_appointment_directory(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return

    db = sqlite3.connect(path)
    try:
        with db:
            db.execute("PRAGMA foreign_keys = ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    explanation TEXT NOT NULL DEFAULT '',
                    file_data BLOB,
                    mime_type TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    instructions TEXT NOT NULL DEFAULT '',
                    reminder_time TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS wellness_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    log_date TEXT NOT NULL,
                    water_glasses INTEGER NOT NULL DEFAULT 0,
                    sleep_hours REAL NOT NULL DEFAULT 0,
                    exercise_minutes INTEGER NOT NULL DEFAULT 0,
                    steps INTEGER NOT NULL DEFAULT 0,
                    focus TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, log_date)
                );
                CREATE TABLE IF NOT EXISTS appointment_hospitals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hospital_name TEXT COLLATE NOCASE NOT NULL,
                    state TEXT COLLATE NOCASE NOT NULL,
                    district TEXT COLLATE NOCASE NOT NULL,
                    city TEXT COLLATE NOCASE NOT NULL,
                    area TEXT COLLATE NOCASE NOT NULL,
                    address TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    care_type TEXT NOT NULL DEFAULT '',
                    specialties TEXT NOT NULL DEFAULT '',
                    pincode TEXT NOT NULL DEFAULT '',
                    coordinates TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'admin_uploaded',
                    source_record_id TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(hospital_name, state, district, city, area)
                );
                CREATE INDEX IF NOT EXISTS appointment_hospitals_location
                    ON appointment_hospitals(state, district, city, area);
                CREATE TABLE IF NOT EXISTS appointment_locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state TEXT COLLATE NOCASE NOT NULL,
                    district TEXT COLLATE NOCASE NOT NULL,
                    city TEXT COLLATE NOCASE NOT NULL,
                    source_code TEXT NOT NULL DEFAULT '',
                    pincodes TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(state, district, city)
                );
                CREATE INDEX IF NOT EXISTS appointment_locations_parent
                    ON appointment_locations(state, district, city);
            CREATE TABLE IF NOT EXISTS appointment_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT COLLATE NOCASE NOT NULL UNIQUE,
                source_code TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS appointment_districts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT COLLATE NOCASE NOT NULL,
                district TEXT COLLATE NOCASE NOT NULL,
                source_code TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(state, district)
            );
            CREATE INDEX IF NOT EXISTS appointment_districts_parent
                ON appointment_districts(state, district);
                CREATE TABLE IF NOT EXISTS appointment_doctors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hospital_id INTEGER NOT NULL REFERENCES appointment_hospitals(id) ON DELETE CASCADE,
                    doctor_name TEXT COLLATE NOCASE NOT NULL,
                    specialty TEXT NOT NULL DEFAULT '',
                    registration_number TEXT NOT NULL DEFAULT '',
                    verification_url TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL DEFAULT 'unverified',
                    source_type TEXT NOT NULL DEFAULT 'admin_uploaded',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(hospital_id, doctor_name, registration_number)
                );
                CREATE INDEX IF NOT EXISTS doctors_by_hospital
                    ON appointment_doctors(hospital_id, doctor_name);
                CREATE TABLE IF NOT EXISTS appointment_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    hospital_id INTEGER NOT NULL REFERENCES appointment_hospitals(id) ON DELETE CASCADE,
                    doctor_id INTEGER REFERENCES appointment_doctors(id) ON DELETE SET NULL,
                    appointment_date TEXT NOT NULL DEFAULT '',
                    time_slot TEXT NOT NULL DEFAULT 'any',
                    booking_key TEXT,
                    booking_mode TEXT NOT NULL DEFAULT 'demo_request',
                    appointment_at TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS appointments_by_user
                    ON appointment_requests(user_id, appointment_at);
            """)
            # Additive migration for databases created before contact numbers existed.
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "phone" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN phone TEXT")
            if "firebase_uid" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN firebase_uid TEXT")
            if "state" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN state TEXT")
            if "area" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN area TEXT")
            if "country" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN country TEXT NOT NULL DEFAULT 'India'")
            report_columns = {row[1] for row in db.execute("PRAGMA table_info(reports)")}
            if "explanation" not in report_columns:
                db.execute("ALTER TABLE reports ADD COLUMN explanation TEXT NOT NULL DEFAULT ''")
            if "file_data" not in report_columns:
                db.execute("ALTER TABLE reports ADD COLUMN file_data BLOB")
            if "mime_type" not in report_columns:
                db.execute("ALTER TABLE reports ADD COLUMN mime_type TEXT NOT NULL DEFAULT ''")
            wellness_columns = {row[1] for row in db.execute("PRAGMA table_info(wellness_logs)")}
            if "focus" not in wellness_columns:
                db.execute("ALTER TABLE wellness_logs ADD COLUMN focus TEXT NOT NULL DEFAULT ''")
            hospital_columns = {row[1] for row in db.execute("PRAGMA table_info(appointment_hospitals)")}
            hospital_additions = {
                "category": "TEXT NOT NULL DEFAULT ''",
                "care_type": "TEXT NOT NULL DEFAULT ''",
                "specialties": "TEXT NOT NULL DEFAULT ''",
                "pincode": "TEXT NOT NULL DEFAULT ''",
                "coordinates": "TEXT NOT NULL DEFAULT ''",
                "source_type": "TEXT NOT NULL DEFAULT 'admin_uploaded'",
                "source_record_id": "TEXT NOT NULL DEFAULT ''",
                "source_url": "TEXT NOT NULL DEFAULT ''",
                "imported_at": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in hospital_additions.items():
                if column not in hospital_columns:
                    db.execute(f"ALTER TABLE appointment_hospitals ADD COLUMN {column} {definition}")
            location_columns = {row[1] for row in db.execute("PRAGMA table_info(appointment_locations)")}
            if "pincodes" not in location_columns:
                db.execute("ALTER TABLE appointment_locations ADD COLUMN pincodes TEXT NOT NULL DEFAULT ''")
            request_columns = {row[1] for row in db.execute("PRAGMA table_info(appointment_requests)")}
            request_additions = {
                "doctor_id": "INTEGER REFERENCES appointment_doctors(id) ON DELETE SET NULL",
                "appointment_date": "TEXT NOT NULL DEFAULT ''",
                "time_slot": "TEXT NOT NULL DEFAULT 'any'",
                "booking_key": "TEXT",
                "booking_mode": "TEXT NOT NULL DEFAULT 'demo_request'",
            }
            for column, definition in request_additions.items():
                if column not in request_columns:
                    db.execute(f"ALTER TABLE appointment_requests ADD COLUMN {column} {definition}")
            # Keep pre-migration requests distinguishable from new, unconfirmed demo requests.
            db.execute("UPDATE appointment_requests SET booking_mode='legacy_request' WHERE booking_key IS NULL AND appointment_date='' AND booking_mode='demo_request'")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS appointment_request_dedupe ON appointment_requests(booking_key) WHERE booking_key IS NOT NULL")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_firebase_uid ON users(firebase_uid)")
            if _appointment_directory_needs_seed(db):
                _seed_attached_appointment_directory(db)
    finally:
        db.close()


@contextmanager
def connection(path):
    if _is_postgres(path):
        database_url = os.environ.get("DATABASE_URL") or path
        db = _postgres_connection(database_url)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return

    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
