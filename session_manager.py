from datetime import datetime, timedelta
import threading
import db
import json
import os

with open("config.json") as f:
    config = json.load(f)

IDLE_TIMEOUT = timedelta(seconds=config.get("idle_timeout_seconds", 300))
MIN_SESSION_SECONDS = config.get("min_session_seconds", 10)
ACTIVE_SESSION_FILE = "/tmp/devlog_active.json"

current_session_start = None
current_project = None
current_git_branch = None
last_activity = None

session_lock = threading.Lock()

def write_active_session():
    """Dumps current active session data for UI representation."""
    if current_session_start and current_project:
        data = {
            "project": current_project,
            "git_branch": current_git_branch,
            "start_time": current_session_start.isoformat()
        }
        with open(ACTIVE_SESSION_FILE, "w") as f:
            json.dump(data, f)

def clear_active_session():
    """Removes the temp file to indicate no active session."""
    if os.path.exists(ACTIVE_SESSION_FILE):
        os.remove(ACTIVE_SESSION_FILE)


def activity_detected(project, git_branch=None):
    global current_session_start, last_activity, current_project, current_git_branch

    now = datetime.now()

    with session_lock:
        # Switch session if project or git branch changes
        if current_session_start is not None and (current_project != project or current_git_branch != git_branch):
            end_session_no_lock()
            
        if current_session_start is None:
            current_session_start = now
            current_project = project
            current_git_branch = git_branch
            print(f"[START] {project} ({git_branch}) @ {now.strftime('%Y-%m-%d %H:%M:%S')}")
            write_active_session()
            
        last_activity = now

def check_idle():
    global current_session_start, last_activity, current_project

    with session_lock:
        if current_session_start is None:
            return

        now = datetime.now()
        if now - last_activity > IDLE_TIMEOUT:
            end_session_no_lock()


def end_session_no_lock():
    """Ends the session without acquiring a lock (used internally when lock is already acquired)"""
    global current_session_start, last_activity, current_project, current_git_branch

    if current_session_start is None:
        return

    end = last_activity
    duration = int((end - current_session_start).total_seconds())
    
    if duration >= MIN_SESSION_SECONDS:
        print(f"[END] {current_project} ({current_git_branch}) @ {end.strftime('%Y-%m-%d %H:%M:%S')} (Duration: {duration}s)")
        db.insert_session(current_project, current_session_start, end, git_branch=current_git_branch)
    else:
        print(f"[CANCELLED] {current_project} session ignored ({duration}s < {MIN_SESSION_SECONDS}s min).")

    current_session_start = None
    last_activity = None
    current_project = None
    current_git_branch = None
    
    clear_active_session()


def end_session():
    """Publicly safe wrapper for ending a session."""
    with session_lock:
        end_session_no_lock()


def recover_orphaned_session():
    """Checks for a stranded active session file on startup and recovers it."""
    if not os.path.exists(ACTIVE_SESSION_FILE):
        return
        
    try:
        with open(ACTIVE_SESSION_FILE, "r") as f:
            data = json.load(f)
            
        project = data.get("project")
        branch = data.get("git_branch")
        try:
            start_time = datetime.fromisoformat(data.get("start_time"))
        except (ValueError, TypeError):
            start_time = None
            
        if project and start_time:
            # We don't know exactly when they stopped, so assume they stopped exactly 
            # at the idle timeout limit after their last known activity timestamp.
            # But the last activity isn't explicitly saved, so the safest conservative 
            # assumption is duration = MIN_SESSION_SECONDS + IDLE_TIMEOUT 
            # (or just close it 1 second after start to at least capture the session happened)
            
            # Since we only have start time in the file, we can either:
            # 1. Look at file mtime of devlog_active.json
            last_edit = datetime.fromtimestamp(os.path.getmtime(ACTIVE_SESSION_FILE))
            
            # We assume they worked from start_time up until the last time the file was written
            # Plus assuming they may have worked IDLE_TIMEOUT past that 
            # (since it didn't gracefully close)
            # Actually, the file is only written at *START*.
            # This means we truly don't know the end time.
            
            print(f"[RECOVERY] Found orphaned session for {project}. Stale data detected.")
            # We can't safely insert a multi-hour gap if we don't know when they stopped.
            # The Safest is to insert a default session of IDLE_TIMEOUT length.
            inferred_end = start_time + IDLE_TIMEOUT
            duration = int((inferred_end - start_time).total_seconds())
            
            if duration >= MIN_SESSION_SECONDS:
                print(f"[RECOVERY] Inserting recovered session to db: {project} ({branch}) {duration}s")
                db.insert_session(project, start_time, inferred_end, git_branch=branch)
                
    except Exception as e:
        print(f"[RECOVERY] Failed to recover session: {e}")
        
    clear_active_session()

