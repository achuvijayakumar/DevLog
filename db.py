import sqlite3
from datetime import datetime
import config

DB_NAME = config.DB_PATH

def connect():
    return sqlite3.connect(DB_NAME)

def init():
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
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
    
    # Simple migration: add category if it doesn't exist
    try:
        cur.execute("ALTER TABLE sessions ADD COLUMN category TEXT")
    except sqlite3.OperationalError:
        pass # Already exists
        
    conn.commit()
    conn.close()
    
def insert_session(project, start, end, git_branch=None, category="default"):
    duration = int((end-start).total_seconds())
    if duration < 1:
        return

    conn = connect()
    cur = conn.cursor()

    # Try to find the most recent session for this same project/branch/category
    cur.execute("""
        SELECT id, start_time, end_time, duration 
        FROM sessions 
        WHERE project = ? AND (git_branch = ? OR (git_branch IS NULL AND ? IS NULL)) AND category = ?
        ORDER BY id DESC LIMIT 1
    """, (project, git_branch, git_branch, category))
    
    last_row = cur.fetchone()
    
    merged = False
    if last_row:
        last_id, last_start_str, last_end_str, last_duration = last_row
        last_end = datetime.fromisoformat(last_end_str)
        
        # If the gap between last session and this one is less than MERGE_GAP
        gap = (start - last_end).total_seconds()
        if 0 <= gap <= config.MERGE_GAP_SECONDS:
            new_end = end
            new_duration = int((new_end - datetime.fromisoformat(last_start_str)).total_seconds())
            
            cur.execute("""
                UPDATE sessions SET end_time = ?, duration = ? WHERE id = ?
            """, (new_end.isoformat(), new_duration, last_id))
            merged = True

    if not merged:
        cur.execute("""
            INSERT INTO sessions(project, start_time, end_time, duration, git_branch, category)
            VALUES(?,?,?,?,?,?)
        """, (project, start.isoformat(), end.isoformat(), duration, git_branch, category))
    
    conn.commit()
    conn.close()