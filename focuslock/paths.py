"""Canonical on-disk locations for Locus on Windows.

Everything lives under %APPDATA%\Locus so the app is ship-ready:
no hardcoded Desktop paths, no temp files that don't survive reboot.

On first import the directory is created if it doesn't exist.
"""

import os

APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Locus")

# Alias for compatibility with code that references APP_SUPPORT_DIR (macOS name)
APP_SUPPORT_DIR = APP_DATA_DIR

CONFIG_PATH     = os.path.join(APP_DATA_DIR, "config.json")
STATE_PATH      = os.path.join(APP_DATA_DIR, "state.json")
COMMAND_PATH    = os.path.join(APP_DATA_DIR, "command.json")
ANALYTICS_PATH  = os.path.join(APP_DATA_DIR, "analytics.json")
EVENTS_PATH     = os.path.join(APP_DATA_DIR, "events.jsonl")
LOCK_PATH       = os.path.join(APP_DATA_DIR, "locusd.lock")
PROMPT_PATH     = os.path.join(APP_DATA_DIR, "prompt.json")
RESPONSE_PATH   = os.path.join(APP_DATA_DIR, "response.json")

os.makedirs(APP_DATA_DIR, exist_ok=True)
