"""Small SQLite persistence layer; no ORM required for this starter app."""
import sqlite3
from contextlib import contextmanager


def init_db(path):
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL,
                granted INTEGER NOT NULL CHECK(granted IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                explanation TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS report_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS hospitals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                state TEXT NOT NULL,
                area TEXT NOT NULL,
                country TEXT NOT NULL DEFAULT 'India',
                address TEXT NOT NULL,
                website TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
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
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_firebase_uid ON users(firebase_uid)")


@contextmanager
def connection(path):
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
