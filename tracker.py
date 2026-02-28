import time
import json
import os
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import db
import session_manager as sm

db.init()

with open("config.json") as f:
    config = json.load(f)

WATCH_PATHS = config.get("watch", [])
IGNORE_DIRS = config.get("ignore_dirs", [".git", "__pycache__", "node_modules", "venv"])

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

class CodeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Ignore configured junk directories
        if any(f"/{d}/" in event.src_path or event.src_path.endswith(f"/{d}") for d in IGNORE_DIRS):
            return
            
        # Match configured project path natively
        project = None
        for watch_path in WATCH_PATHS:
            if event.src_path.startswith(watch_path):
                project = os.path.basename(watch_path)
                break
                
        if project:
            branch = get_git_branch(os.path.dirname(event.src_path))
            sm.activity_detected(project, branch)

observer = Observer()

for path in WATCH_PATHS:
    observer.schedule(CodeHandler(), path, recursive=True)

observer.start()

print("DevLog tracking started...")

try:
    while True:
        time.sleep(5)
        sm.check_idle()

except KeyboardInterrupt:
    print("Stopping observer...")
    observer.stop()
finally:
    # Ensure current session data is logged to DB safely on exit
    sm.end_session()
    observer.join()
