import sqlite3
from datetime import datetime

from config import DB_PATH, setup_logging

log = setup_logging("devlog.db")

MAX_SESSION_DURATION = 12 * 3600  # 12 hours — sanity cap


def connect():
    return sqlite3.connect(DB_PATH)

def init():
    """Create the sessions table if it doesn't exist, and run any pending migrations."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT,
                start_time TEXT,
                end_time TEXT,
                duration INTEGER,
                git_branch TEXT,
                category TEXT
            )
        """)
        conn.commit()
        _migrate(conn)
    log.info("Database initialized at %s", DB_PATH)


def _migrate(conn):
    """Add columns that may be missing from older schemas."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(sessions)")
    columns = {row[1] for row in cur.fetchall()}

    if "git_branch" not in columns:
        log.info("Migrating DB: adding 'git_branch' column")
        conn.execute("ALTER TABLE sessions ADD COLUMN git_branch TEXT")
        conn.commit()

    if "category" not in columns:
        log.info("Migrating DB: adding 'category' column")
        conn.execute("ALTER TABLE sessions ADD COLUMN category TEXT")
        conn.commit()


def insert_session(project, start, end, git_branch=None, category=None):
    duration = int((end - start).total_seconds())

    # Duration validation — ignore impossibly long sessions
    if duration <= 0:
        log.warning("Skipping session with non-positive duration (%ds) for %s", duration, project)
        return
    if duration > MAX_SESSION_DURATION:
        log.warning(
            "Capping session duration from %ds to %ds for %s (possible sleep/hibernate)",
            duration, MAX_SESSION_DURATION, project
        )
        duration = MAX_SESSION_DURATION

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO sessions(project, start_time, end_time, duration, git_branch, category)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (project, start.isoformat(), end.isoformat(), duration, git_branch, category),
        )
        conn.commit()

    log.debug("Inserted session: %s [%s] [%s] %ds", project, git_branch, category, duration)