from datetime import datetime, timedelta
import db

current_session_start = None
current_project = None
last_activity = None
IDLE_TIMEOUT = timedelta(seconds=300)

def activity_detected(project):
    global current_session_start, last_activity, current_project

    now = datetime.now()

    if current_session_start is None:
        current_session_start = now
        current_project = project
        print(f"[START] {project} @ {now}")

    last_activity = now

def check_idle():
    global current_session_start, last_activity, current_project

    if current_session_start is None:
        return

    now = datetime.now()
    if now - last_activity > IDLE_TIMEOUT:
        end_session()

def end_session():
    global current_session_start, last_activity, current_project

    if current_session_start is None:
        return

    end = last_activity
    print(f"[END] {current_project} @ {end}")

    db.insert_session(current_project, current_session_start, end)

    current_session_start = None
    last_activity = None
    current_project = None
