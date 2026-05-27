import time
import os
import re
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import db
import session_manager as sm
import config

# An event counts as activity only when it carries a verified human-editor
# signature. Bots that open(path, 'w') leave no such trace and are dropped.
# Pattern set: vim probe/swap/undo, emacs lock/backup, generic tilde backup,
# VS Code / Cursor / JetBrains atomic-write temp names.
EDITOR_ARTIFACT_RE = re.compile(
    r"""^(
        4913
      | \..*\.sw[a-z]
      | .*\.sw[a-z]
      | .*~
      | \.\#.*
      | .*\.un~
      | \..*\.tmp
      | \..*\.tmp\.\w+
      | \..*\.sb-[\w-]+
    )$""",
    re.VERBOSE,
)

# Initialize database and recover any stranded sessions from previous crash
db.init()
sm.recover_orphaned_session()

# Load configuration from centralized config module
WATCH_ROOTS = config.WATCH_ROOTS
IGNORE_DIRS = config.IGNORE_DIRS
DB_PATH = os.path.basename(config.DB_PATH)
LOG_FILE = os.path.basename(config.LOG_FILE)
ACTIVE_SESSION_FILE = os.path.basename(config.ACTIVE_SESSION_FILE)

def get_git_branch(directory):
    try:
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], 
            cwd=directory, 
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        return branch if branch != 'HEAD' else None
    except Exception:
        return None

def resolve_project(file_path):
    """
    Resolve which project a file belongs to.
    Returns (project_name, project_root_dir, category) or (None, None, None).
    """
    file_path = os.path.abspath(file_path)
    
    for watch_path, category in WATCH_ROOTS.items():
        watch_path = os.path.abspath(watch_path).rstrip(os.sep)
        if file_path.startswith(watch_path + os.sep):
            relative = file_path[len(watch_path) + 1:]
            parts = relative.split(os.sep)
            
            if parts and parts[0]:
                project_name = parts[0]
                project_root = os.path.join(watch_path, project_name)
                
                # We only track subdirectories as projects. 
                # Individual files in the root apps folder are ignored to avoid "Apps" noise.
                if os.path.isdir(project_root):
                    return project_name, project_root, category
    return None, None, None

_last_seen = {}
DEBOUNCE_SEC = 2

class CodeHandler(FileSystemEventHandler):
    def _handle_event(self, event, file_path):
        file_name = os.path.basename(file_path)

        # 1. Ignore own internal files
        if file_name in [DB_PATH, LOG_FILE, ACTIVE_SESSION_FILE]:
            return

        # 2. Ignore heavy database/log/temp extensions that cause phantom sessions
        ignored_exts = {'.db', '.db-journal', '.db-wal', '.db-shm', '.log', '.tmp', '.ipynb', '.pyc', '.csv'}
        if any(file_name.endswith(ext) for ext in ignored_exts):
            return

        # 3. Ignore configured junk directories
        if any(f"{os.sep}{d}{os.sep}" in file_path or file_path.endswith(f"{os.sep}{d}") for d in IGNORE_DIRS):
            return

        # Debounce
        now = time.time()
        prev = _last_seen.get(file_path, 0)
        if now - prev < DEBOUNCE_SEC:
            return
        _last_seen[file_path] = now

        project, project_root, category = resolve_project(file_path)
        if project:
            branch = get_git_branch(project_root)
            sm.activity_detected(project, branch, category)

    def on_moved(self, event):
        # The only path to a tracked event: an editor atomically renaming
        # its temp/swap file over the target. The src basename carries the
        # editor signature; the dest is the real file being edited.
        if event.is_directory:
            return
        src_name = os.path.basename(event.src_path)
        if not EDITOR_ARTIFACT_RE.match(src_name):
            return
        self._handle_event(event, event.dest_path)

observer = Observer()

if not WATCH_ROOTS:
    print("[WARNING] No watch paths configured in config.json. Tracking will not work.")
else:
    for path in WATCH_ROOTS.keys():
        if os.path.exists(path):
            print(f"Scheduling watcher for: {path}")
            observer.schedule(CodeHandler(), path, recursive=True)
        else:
            print(f"[ERROR] Watch path does not exist: {path}")

observer.start()

print("DevLog tracking started...")

try:
    while True:
        time.sleep(5)
        sm.check_idle()

except KeyboardInterrupt:
    print("Stopping observer...")
    observer.stop()
except Exception as e:
    print(f"Tracker encountered an error: {e}")
    observer.stop()
finally:
    # Ensure current session data is logged to DB safely on exit
    sm.end_session()
    observer.join()
