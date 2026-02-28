# ⏱️ DevLog
Lightweight, automated coding-session tracker that watches your project folders, detects activity/idle time, and logs sessions to SQLite—no manual timers. View everything in a Streamlit dashboard while the tracker runs quietly in the background.

## ✨ Key Features
- Automated tracking based on filesystem activity (no start/stop buttons)
- Idle detection with configurable timeout
- Multi-project monitoring across directories
- Git branch capture for each session
- Interactive Streamlit dashboard (Plotly visualizations)
- Background-friendly on Windows Startup or Linux systemd

## 🗺️ Components
- `tracker.py`: Watchdog observer that listens for file changes and notifies the session manager.
- `session_manager.py`: Handles session lifecycle, idle cutoff, and writes live state to `/tmp/devlog_active.json` for the UI.
- `db.py`: SQLite storage in `devlog.db` at the repo root.
- `ui.py`: Streamlit dashboard for logs, metrics, and charts (port 8501 by default).

## 🛠️ Prerequisites
- Python 3.8 or newer
- `pip` available on your PATH
- (Recommended) Virtual environment for project isolation

## 💻 Local Setup (Windows)
1. Clone the repo and (optionally) create a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate
   pip install -r requirement.txt
   ```
2. Configure `config.json` with the folders you want to watch and your idle timeout (use absolute Windows paths with escaped backslashes):
   ```json
   {
     "watch": [
       "D:\\\\Projects\\\\DevLog",
       "C:\\\\Work\\\\AnotherProject"
     ],
     "idle_timeout_seconds": 300,
     "ignore_dirs": ["node_modules", ".git", "__pycache__", ".next", "dist", "build"]
   }
   ```
3. Run the dashboard (opens at http://localhost:8501):
   ```powershell
   streamlit run ui.py
   ```
4. Run the tracker:
   ```powershell
   python tracker.py
   ```

## 🕶️ Background on Windows
- One-time setup to launch the tracker silently on login:
  ```powershell
  python install_startup.py
  ```
  This drops `DevLogTracker.vbs` in your Windows Startup folder and runs `pythonw tracker.py` without a console window.
- To remove autostart, delete `DevLogTracker.vbs` from the Startup folder.

## 🌐 VPS / Linux Setup
1. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip3 install -r requirement.txt
   ```
2. Edit `config.json` with POSIX paths (e.g., `/home/devlog/projects`).
3. Run manually (optional):
   ```bash
   python3 tracker.py
   streamlit run ui.py --server.port 8501 --server.headless true
   ```

## 🛡️ systemd Services (Linux)
`/etc/systemd/system/devlog-tracker.service`
```ini
[Unit]
Description=DevLog Background Tracker
After=network.target

[Service]
Type=simple
User=devlog
WorkingDirectory=/path/to/Devlog
ExecStart=/usr/bin/python3 tracker.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/devlog-ui.service`
```ini
[Unit]
Description=DevLog Streamlit UI
After=network.target

[Service]
Type=simple
User=devlog
WorkingDirectory=/path/to/Devlog
ExecStart=/usr/bin/python3 -m streamlit run ui.py --server.port 8501 --server.headless true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start both:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now devlog-tracker devlog-ui
```

## ⚙️ Configuration
| Key | Type | Description |
| --- | --- | --- |
| `watch` | list of strings | Absolute paths to directories to monitor. |
| `idle_timeout_seconds` | integer | Seconds of inactivity before a session is ended. |
| `ignore_dirs` | list of strings | Directory names to skip while watching. |

- Live session status is written to `/tmp/devlog_active.json` for the dashboard banner.
- Session records are stored in `devlog.db` in the repo root.

## 📊 Usage
- Dashboard at `http://localhost:8501` shows total sessions, time tracked, projects, and charts (heatmap, per-project/branch pies, recent sessions).
- “Currently Tracking” banner appears when the tracker reports activity.
- Use the “Refresh Data” button in the UI to pull latest records.

## 🧪 Validation Checklist
- Start `python tracker.py`, edit a watched file, and confirm a new session row appears in the dashboard.
- On Windows reboot, tracker should auto-start (check Startup folder for `DevLogTracker.vbs`).
- On Linux, `systemctl status devlog-tracker` and `systemctl status devlog-ui` should show `active (running)`; services auto-restart on failure.

## 🧰 Tech Stack
- Python
- Watchdog
- SQLite
- Streamlit
- Plotly
