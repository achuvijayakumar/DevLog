"""
Centralized configuration loader for DevLog.
All modules should import config values from here instead of reading config.json directly.
"""

import json
import os
import sys
import logging
import tempfile

# --- Resolve project root (directory containing this file) ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# --- Load config.json once ---
_config_path = os.path.join(PROJECT_ROOT, "config.json")

try:
    with open(_config_path) as _f:
        _config = json.load(_f)
except FileNotFoundError:
    print(f"[FATAL] config.json not found at {_config_path}", file=sys.stderr)
    _config = {}
except json.JSONDecodeError as e:
    print(f"[FATAL] config.json is invalid JSON: {e}", file=sys.stderr)
    _config = {}

# --- Exported config values ---

# New: watch_roots maps root folders to category labels (personal / work).
# Each immediate subfolder inside a root is treated as a separate project.
WATCH_ROOTS = _config.get("watch_roots", {})

# Legacy: flat watch list (kept for backward compatibility, ignored if watch_roots is set)
WATCH_PATHS = _config.get("watch", [])

IDLE_TIMEOUT_SECONDS = _config.get("idle_timeout_seconds", 300)
IGNORE_DIRS = _config.get("ignore_dirs", [".git", "__pycache__", "node_modules", "venv"])

# --- Platform-aware paths ---
DB_PATH = os.path.join(PROJECT_ROOT, "devlog.db")
ACTIVE_SESSION_FILE = os.path.join(tempfile.gettempdir(), "devlog_active.json")
LOG_FILE = os.path.join(PROJECT_ROOT, "devlog.log")

# --- Logging setup ---
def setup_logging(name: str = "devlog") -> logging.Logger:
    """Configure and return a logger with both file and console handlers."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.DEBUG)

    # File handler — persistent log for background debugging
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Console handler — for interactive runs
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "[%(levelname)s] %(message)s"
    ))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
