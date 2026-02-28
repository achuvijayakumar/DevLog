from datetime import datetime, timedelta
import threading
import db
import json
import os

with open("config.json") as f:
    config = json.load(f)

IDLE_TIMEOUT = timedelta(seconds=config.get("idle_timeout_seconds", 300))
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
    
    if duration > 0:
        print(f"[END] {current_project} ({current_git_branch}) @ {end.strftime('%Y-%m-%d %H:%M:%S')} (Duration: {duration}s)")
        db.insert_session(current_project, current_session_start, end, git_branch=current_git_branch)
    else:
        print(f"[CANCELLED] {current_project} session ignored (0 skipped).")

    current_session_start = None
    last_activity = None
    current_project = None
    current_git_branch = None
    
    clear_active_session()


def end_session():
    """Publicly safe wrapper for ending a session."""
    with session_lock:
        end_session_no_lock()
