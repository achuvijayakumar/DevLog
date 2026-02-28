import time
import json
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import db
import session_manager as sm

db.init()

with open("config.json") as f:
    config = json.load(f)

WATCH_PATHS = config["watch"]

class CodeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        
        project = os.path.basename(os.path.dirname(event.src_path))
        sm.activity_detected(project)

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
    observer.stop()

observer.join()
