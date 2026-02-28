import sqlite3
from datetime import datetime

DB_NAME = "devlog.db"

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
                git_branch TEXT
                )
                """)
    conn.commit()
    conn.close()
    
def insert_session(project,start,end, git_branch=None):
    duration = int((end-start).total_seconds())

    conn=connect()
    cur=conn.cursor()

    cur.execute("""
        INSERT INTO sessions(project, start_time, end_time, duration, git_branch)
        VALUES(?,?,?,?,?)
    
    """, (project, start.isoformat(), end.isoformat(), duration, git_branch))
    
    conn.commit()
    conn.close()