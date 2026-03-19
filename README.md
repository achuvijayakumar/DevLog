# ⏱️ DevLog

Lightweight, automated coding-session tracker that watches your project root folders, detects activity/idle time, dynamically discovers new projects, and logs categorized sessions to SQLite—no manual timers. View everything in a beautiful Streamlit dashboard while the tracker runs quietly in the background.

## ✨ Key Features
- **Zero-Touch Tracking:** Automated tracking based on filesystem activity (no start/stop buttons).
- **Dynamic Project Discovery:** Automatically discovers all projects inside root folders (e.g., all folders under your `Personal Projects` dir).
- **Auto-Detects New Folders:** Creating a new project folder inside a tracked root immediately starts tracking it without restarting the system.
- **Categorization:** Tag entire root folders with custom categories (e.g., "Personal" vs "Work").
- **Git Integration:** Captures the active git branch for each session.
- **Interactive Dashboard:** Beautiful Streamlit dashboard with Plotly visualisations, daily heatmaps, and category/date/project filters.
- **Background Autostart:** One-click script to install the background tracker into Windows Startup.

## 🗺️ Components
- `tracker.py`: Watchdog observer that monitors root folders, dynamically detects new project directories, and notifies the session manager of file modifications.
- `session_manager.py`: Handles session lifecycle, idle cutoff, maintains project categories, and writes live state to a temp file for the UI.
- `config.py`: Centralized configuration loader for paths, parsing watch roots, and logging setup.
- `db.py`: SQLite storage in `devlog.db` tracking sessions, project names, branches, and categories.
- `ui.py`: Streamlit dashboard for filtering logs, displaying metrics, and rendering productivity charts (port 8501 by default).

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
2. Configure `config.json` with the root folders you want to watch mapped to their categories, and your idle timeout:
   ```json
   {
     "watch_roots": {
       "D:\\Personal Projects": "personal",
       "D:\\Work": "work"
     },
     "idle_timeout_seconds": 300,
     "ignore_dirs": ["node_modules", ".git", "__pycache__", ".next", "dist", "build", ".venv"]
   }
   ```
3. Run the dashboard (opens at `http://localhost:8501`):
   ```powershell
   streamlit run ui.py
   ```
4. Run the tracker in the background:
   ```powershell
   python tracker.py
   ```

## 🕶️ Background on Windows
- One-time setup to launch the tracker on login:
  ```powershell
  python install_startup.py
  ```
  This drops `DevLogTracker.cmd` in the Windows Startup folder and launches `tracker.py` with an absolute `pythonw.exe` path, which avoids environments where Windows Script Host / `.vbs` execution is disabled.
- To remove autostart, delete `DevLogTracker.cmd` from the Startup folder.

## 🌐 VPS / Linux Setup
1. Install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip3 install -r requirement.txt
   ```
2. Edit `config.json` with POSIX paths and map them to their categories (e.g., `{"/home/devlog/projects": "personal"}`).
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

## ⚙️ Configuration Properties
| Key | Type | Description |
| --- | --- | --- |
| `watch_roots` | object | Dictionary mapping absolute root folder paths to their category (e.g., `{"C:\\Projects": "personal"}`). Each immediate subfolder within these roots is treated as a separate project. |
| `idle_timeout_seconds` | integer | Seconds of inactivity before a session automatically ends. |
| `ignore_dirs` | list of strings | Directory names to completely skip while watching (avoids CPU spikes from build processes). |

- Live session status is written to a platform-specific temp file (e.g., `%TEMP%\devlog_active.json` on Windows, `/tmp/devlog_active.json` on Linux) for the dashboard's live banner.
- Session records are securely stored in `devlog.db` in the repository root.
- Background logs are written to `devlog.log`.

## 📊 Analytics Dashboard
Launch the dashboard via `streamlit run ui.py`. The dashboard provides:
- **Filters:** Isolate data by Category (e.g., Personal vs Work), Date Range, and specific Projects.
- **Top Level Metrics:** Total sessions, time tracked, deep work percentage, and current daily/weekly streaks.
- **Session Log:** A raw table of all historical sessions.
- **Visual Analytics:** Daily coding heatmaps, time-per-project donuts, peak hour bar charts, and weekly consistency trends.
- **Insights:** Auto-generated productivity analysis determining your coder persona (Night Owl, Early Bird, etc.).

## 🧰 Tech Stack
- Python
- Watchdog (File System Events)
- SQLite (Storage)
- Streamlit (Frontend Dashboard)
- Plotly Express (Data Visualization)
- Pandas (Data Manipulation)
