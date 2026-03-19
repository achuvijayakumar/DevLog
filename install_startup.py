import os
import sys


def resolve_pythonw():
    """Prefer pythonw.exe next to the current interpreter for startup runs."""
    interpreter_dir = os.path.dirname(sys.executable)
    pythonw_path = os.path.join(interpreter_dir, "pythonw.exe")
    if os.path.exists(pythonw_path):
        return pythonw_path
    return sys.executable


project_dir = os.path.dirname(os.path.abspath(__file__))
tracker_path = os.path.join(project_dir, "tracker.py")
pythonw_path = resolve_pythonw()

appdata = os.environ.get("APPDATA")
startup_folder = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
cmd_path = os.path.join(startup_folder, "DevLogTracker.cmd")
legacy_vbs_path = os.path.join(startup_folder, "DevLogTracker.vbs")

cmd_code = "\n".join([
    "@echo off",
    f'cd /d "{project_dir}"',
    f'start "" "{pythonw_path}" "{tracker_path}"',
    ""
])

try:
    os.makedirs(startup_folder, exist_ok=True)

    with open(cmd_path, "w", encoding="utf-8") as f:
        f.write(cmd_code)

    if os.path.exists(legacy_vbs_path):
        os.remove(legacy_vbs_path)

    print("Successfully configured DevLog to run automatically on startup!")
    print(f"Startup launcher installed at: {cmd_path}")
    print(f"Python launcher: {pythonw_path}")
    print(f"Tracker path: {tracker_path}")
except Exception as e:
    print(f"Error installing startup script: {e}")
