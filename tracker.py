import time
import os
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, DirCreatedEvent

import db
import session_manager as sm
from config import WATCH_ROOTS, IGNORE_DIRS, setup_logging

log = setup_logging("devlog.tracker")

db.init()
sm.clear_active_session()  # Clear stale state if previous tracker exited unexpectedly.


def get_git_branch(directory):
    # Fast path: use git when available and permitted.
    try:
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=directory,
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        if branch and branch != 'HEAD':
            return branch
    except Exception:
        pass

    # Fallback for environments where git command is unavailable or blocked
    # (e.g. safe.directory ownership checks under another Windows user).
    try:
        git_path = os.path.join(directory, '.git')
        git_dir = None

        if os.path.isdir(git_path):
            git_dir = git_path
        elif os.path.isfile(git_path):
            with open(git_path, 'r', encoding='utf-8', errors='replace') as f:
                pointer = f.readline().strip()
            if pointer.lower().startswith('gitdir:'):
                target = pointer.split(':', 1)[1].strip()
                git_dir = target if os.path.isabs(target) else os.path.normpath(
                    os.path.join(directory, target)
                )

        if not git_dir:
            return None

        head_path = os.path.join(git_dir, 'HEAD')
        if not os.path.exists(head_path):
            return None

        with open(head_path, 'r', encoding='utf-8', errors='replace') as f:
            head = f.readline().strip()

        if head.startswith('ref:'):
            ref = head.split(':', 1)[1].strip()
            return os.path.basename(ref) if ref else None
    except Exception:
        pass

    return None


def discover_projects(watch_roots):
    """
    Scan each watch root and return a dict mapping normalized project paths
    to (project_name, category, original_project_root) tuples.
    """
    projects = {}
    for root_path, category in watch_roots.items():
        if not os.path.isdir(root_path):
            log.warning("Watch root does not exist, skipping: %s", root_path)
            continue
        try:
            for entry in os.scandir(root_path):
                if entry.is_dir() and entry.name not in IGNORE_DIRS:
                    norm_path = os.path.normcase(entry.path)
                    projects[norm_path] = (entry.name, category, entry.path)
        except Exception as e:
            log.error("Error scanning root %s: %s", root_path, e)
    return projects


def resolve_project(file_path, project_map, watch_roots):
    """
    Given a file path, find which project it belongs to by traversing up its parents.
    Returns (project_name, category, project_root_path) or (None, None, None).
    """
    current = os.path.normcase(file_path)
    
    # Climb up the directory tree to find a match in project_map
    while True:
        if current in project_map:
            return project_map[current]
        
        parent = os.path.dirname(current)
        if parent == current: # Reached root
            break
        current = parent

    return None, None, None


# ---- Build the initial project map ----
project_map = discover_projects(WATCH_ROOTS)

log.info("Discovered %d projects across %d watch roots", len(project_map), len(WATCH_ROOTS))
for norm_path, (name, category, _) in sorted(project_map.items()):
    log.info("  [%s] %s -> %s", category, name, norm_path)


class CodeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return

        # Ignore dirs
        normalized_path = event.src_path.replace(os.sep, '/')
        if any(f"/{d}/" in normalized_path for d in IGNORE_DIRS):
            return

        project_name, category, project_root = resolve_project(
            event.src_path, project_map, WATCH_ROOTS
        )

        if project_name:
            branch = get_git_branch(project_root)
            sm.activity_detected(project_name, branch, category)

    def on_created(self, event):
        """Auto-detect new project folders created inside watch roots."""
        if not isinstance(event, DirCreatedEvent):
            return

        for root_path, category in WATCH_ROOTS.items():
            norm_root = os.path.normcase(root_path)
            norm_new = os.path.normcase(event.src_path)
            parent_of_new = os.path.normcase(os.path.dirname(event.src_path))

            # Only react to immediate children of a watch root
            if parent_of_new == norm_root:
                folder_name = os.path.basename(event.src_path)
                if folder_name not in IGNORE_DIRS:
                    project_map[norm_new] = (folder_name, category, event.src_path)
                    log.info(
                        "[NEW PROJECT] Auto-detected '%s' [%s] at %s",
                        folder_name, category, event.src_path
                    )
                break


# ---- Set up watchers on each root ----
observer = Observer()

for root_path in WATCH_ROOTS:
    if os.path.isdir(root_path):
        observer.schedule(CodeHandler(), root_path, recursive=True)
        log.info("Watching root: %s [%s]", root_path, WATCH_ROOTS[root_path])
    else:
        log.warning("Watch root does not exist, skipping: %s", root_path)

observer.start()

log.info("DevLog tracking started (monitoring %d roots, %d projects)",
         len(WATCH_ROOTS), len(project_map))

try:
    while True:
        time.sleep(5)
        sm.check_idle()

except KeyboardInterrupt:
    log.info("Stopping observer (KeyboardInterrupt)...")
    observer.stop()
except Exception as e:
    log.error("Tracker crashed with unexpected error: %s", e, exc_info=True)
    observer.stop()
finally:
    sm.end_session()
    observer.join()
    log.info("DevLog tracker shut down cleanly.")
