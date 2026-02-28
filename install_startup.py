import os

# Get the Windows Startup folder path dynamically
appdata = os.environ.get('APPDATA')
startup_folder = os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')

# Path for the new VBScript file
vbs_path = os.path.join(startup_folder, 'DevLogTracker.vbs')

# VBScript code to run the tracker silently in the background
vbs_code = """Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "d:\\Devlog"
WshShell.Run "pythonw tracker.py", 0, False
"""

# Write the VBScript to the Startup folder
try:
    with open(vbs_path, 'w') as f:
        f.write(vbs_code)
    print(f"Successfully configured DevLog to run automatically on startup!")
    print(f"Startup script installed at: {vbs_path}")
except Exception as e:
    print(f"Error installing startup script: {e}")
