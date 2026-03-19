from datetime import datetime, timedelta
import threading
import json
import os

import db
from config import IDLE_TIMEOUT_SECONDS, ACTIVE_SESSION_FILE, setup_logging

log = setup_logging("devlog.session")

IDLE_TIMEOUT = timedelta(seconds=IDLE_TIMEOUT_SECONDS)

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
            "start_time": current_session_start.isoformat(),
            "last_activity": last_activity.isoformat() if last_activity else None,
            "tracker_pid": os.getpid(),
            "updated_at": datetime.now().isoformat()
        }
        tmp_file = f"{ACTIVE_SESSION_FILE}.tmp"
        try:
            # Atomic replace avoids UI reads on partially-written JSON.
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp_file, ACTIVE_SESSION_FILE)
        except OSError as e:
            log.warning("Could not write active session file: %s", e)
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except OSError:
                pass


def clear_active_session():
    """Removes the temp file to indicate no active session."""
    try:
        if os.path.exists(ACTIVE_SESSION_FILE):
            os.remove(ACTIVE_SESSION_FILE)
    except OSError as e:
        log.warning("Could not clear active session file: %s", e)


def activity_detected(project, git_branch=None, category=None):
    global current_session_start, last_activity, current_project, current_git_branch, current_category

    now = datetime.now()

    with session_lock:
        # Switch session if project, git branch, or category changes
        if current_session_start is not None and (
            current_project != project or
            current_git_branch != git_branch or
            current_category != category
        ):
            end_session_no_lock()

        if current_session_start is None:
            current_session_start = now
            current_project = project
            current_git_branch = git_branch
            current_category = category
            log.info("[START] %s (%s) [%s] @ %s", project, git_branch, category, now.strftime('%Y-%m-%d %H:%M:%S'))

        last_activity = now
        write_active_session()


def check_idle():
    global current_session_start, last_activity, current_project, current_git_branch, current_category

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

    end = last_activity
    duration = int((end - current_session_start).total_seconds())

    if duration > 0:
        log.info("[END] %s (%s) [%s] @ %s (Duration: %ds)",
                 current_project, current_git_branch, current_category,
                 end.strftime('%Y-%m-%d %H:%M:%S'), duration)
        db.insert_session(current_project, current_session_start, end,
                          git_branch=current_git_branch, category=current_category)
    else:
        log.info("[CANCELLED] %s session ignored (0s skipped).", current_project)

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
