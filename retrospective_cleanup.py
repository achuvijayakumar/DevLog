import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_NAME = "/home/memoryping/apps/Devlog/devlog.db"
CONFIG_FILE = "/home/memoryping/apps/Devlog/config.json"

with open(CONFIG_FILE) as f:
    config = json.load(f)

MIN_SESSION_SECONDS = config.get("min_session_seconds", 10)
MERGE_GAP = timedelta(seconds=config.get("merge_gap_seconds", 300))
CROSS_PROJECT_MERGE = config.get("cross_project_merge", False)

conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

# 1. Delete short sessions
cur.execute("DELETE FROM sessions WHERE duration < ?", (MIN_SESSION_SECONDS,))
deleted_short = cur.rowcount
print(f"Deleted {deleted_short} noise sessions (< {MIN_SESSION_SECONDS}s).")

# 2. Merge older sessions
cur.execute("SELECT id, project, start_time, end_time, duration, git_branch FROM sessions ORDER BY start_time ASC")
rows = cur.fetchall()

merged_sessions = []
to_delete = []
updates = {}  # id -> (new_end_str, new_duration)

for row in rows:
    sid, proj, start_str, end_str, dur, branch = row
    
    try:
        # Some older entries might not have an end_time if it's missing (rare, but handle safely)
        start_dt = pd.to_datetime(start_str) if 'pd' in globals() else datetime.fromisoformat(start_str)
        # sqlite might return strings like "2026-03-22 10:00:00" without the T, but fromisoformat handles most.
    except Exception:
        # Fallback simple string parse
        try:
            start_dt = datetime.strptime(start_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                start_dt = datetime.strptime(start_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
            except Exception as e:
                print(f"Skipping unparseable date {start_str}: {e}")
                continue

    try:
        end_dt = datetime.fromisoformat(end_str) if end_str else start_dt + timedelta(seconds=dur or 0)
    except Exception:
        try:
            end_dt = datetime.strptime(end_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                end_dt = datetime.strptime(end_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                end_dt = start_dt + timedelta(seconds=dur or 0)

    s = {
        'id': sid,
        'project': proj,
        'start_dt': start_dt,
        'end_dt': end_dt,
    }
    
    if merged_sessions and (s['start_dt'] - merged_sessions[-1]['end_dt']) <= MERGE_GAP:
        if CROSS_PROJECT_MERGE or s['project'] == merged_sessions[-1]['project']:
            # Overlap/Close enough -> MERGE
            merged_sessions[-1]['end_dt'] = max(merged_sessions[-1]['end_dt'], s['end_dt'])
            to_delete.append(s['id'])
            
            new_dur = int((merged_sessions[-1]['end_dt'] - merged_sessions[-1]['start_dt']).total_seconds())
            updates[merged_sessions[-1]['id']] = (merged_sessions[-1]['end_dt'].isoformat(), new_dur)
            continue
            
    merged_sessions.append(s)

for sid, (new_end, new_dur) in updates.items():
    cur.execute("UPDATE sessions SET end_time = ?, duration = ? WHERE id = ?", (new_end, new_dur, sid))

for sid in to_delete:
    cur.execute("DELETE FROM sessions WHERE id = ?", (sid,))

conn.commit()
conn.close()

print(f"Merged {len(to_delete)} close/overlapping sessions into their parent sessions.")
