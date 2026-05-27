from datetime import datetime, timedelta
import threading
import db
import json
import os
import config

IDLE_TIMEOUT = timedelta(seconds=config.IDLE_TIMEOUT_SECONDS)
MIN_SESSION_SECONDS = config.MIN_SESSION_SECONDS
ACTIVE_SESSION_FILE = config.ACTIVE_SESSION_FILE

current_session_start = None
current_project = None
current_git_branch = None
current_category = None
last_activity = None

session_lock = threading.Lock()

def write_active_session():
    """Dumps current active session data for UI representation."""
    if current_session_start and current_project:
        data = {
            "project": current_project,
            "git_branch": current_git_branch,
            "category": current_category,
            "start_time": current_session_start.isoformat()
        }
        try:
            with open(ACTIVE_SESSION_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

def clear_active_session():
    """Removes the temp file to indicate no active session."""
    if os.path.exists(ACTIVE_SESSION_FILE):
        os.remove(ACTIVE_SESSION_FILE)


def activity_detected(project, git_branch=None, category="default"):
    global current_session_start, last_activity, current_project, current_git_branch, current_category

    now = datetime.now()

    with session_lock:
        # Switch session if project or git branch or category changes
        if current_session_start is not None and (current_project != project or current_git_branch != git_branch or current_category != category):
            end_session_no_lock()
            
        if current_session_start is None:
            current_session_start = now
            current_project = project
            current_git_branch = git_branch
            current_category = category
            print(f"[START] {project} ({git_branch}) [{category}] @ {now.strftime('%Y-%m-%d %H:%M:%S')}")
            write_active_session()
        else:
            # Throttled update of the active session file mtime (every 30s)
            if last_activity and (now - last_activity).total_seconds() > 30:
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
    global current_session_start, last_activity, current_project, current_git_branch, current_category

    if current_session_start is None:
        return

    # If it's an idle timeout, the end time is last_activity.
    # Otherwise, it might be a project switch, in which case the end time is now.
    end = last_activity or datetime.now()
    duration = int((end - current_session_start).total_seconds())
    
    if duration >= MIN_SESSION_SECONDS:
        print(f"[END] {current_project} ({current_git_branch}) @ {end.strftime('%Y-%m-%d %H:%M:%S')} (Duration: {duration}s)")
        db.insert_session(current_project, current_session_start, end, git_branch=current_git_branch, category=current_category)
    else:
        print(f"[CANCELLED] {current_project} session ignored ({duration}s < {MIN_SESSION_SECONDS}s min).")

    current_session_start = None
    last_activity = None
    current_project = None
    current_git_branch = None
    current_category = None
    
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
        cat = data.get("category", "default")
        try:
            start_time = datetime.fromisoformat(data.get("start_time"))
        except (ValueError, TypeError):
            start_time = None
            
        if project and start_time:
            # The file is now touched regularly during activity.
            # mtime represents the last recorded activity.
            last_activity_time = datetime.fromtimestamp(os.path.getmtime(ACTIVE_SESSION_FILE))
            
            # Use whichever is later: start_time + buffer OR the file's mtime
            inferred_end = max(last_activity_time, start_time + timedelta(seconds=MIN_SESSION_SECONDS))
            duration = int((inferred_end - start_time).total_seconds())
            
            if duration >= MIN_SESSION_SECONDS:
                print(f"[RECOVERY] Recovered orphaned session for {project}. Duration: {duration}s")
                db.insert_session(project, start_time, inferred_end, git_branch=branch, category=cat)
                
    except Exception as e:
        print(f"[RECOVERY] Failed to recover session: {e}")
        
    clear_active_session()
