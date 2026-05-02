"""Canonical on-disk locations for Locus.

On macOS the data lives in ~/Library/Application Support/Locus (matching the
native macOS daemon).  On Windows it lives in %APPDATA%/Locus.
"""

import os
import sys

if sys.platform == "darwin":
    APP_DATA_DIR = os.path.join(
        os.path.expanduser("~"), "Library", "Application Support", "Locus"
    )
elif os.environ.get("APPDATA"):
    APP_DATA_DIR = os.path.join(os.environ["APPDATA"], "Locus")
else:
    APP_DATA_DIR = os.path.join(os.path.expanduser("~"), "Locus")

# Alias for compatibility with code that references APP_SUPPORT_DIR (macOS name)
APP_SUPPORT_DIR = APP_DATA_DIR

CONFIG_PATH    = os.path.join(APP_DATA_DIR, "config.json")
STATE_PATH     = os.path.join(APP_DATA_DIR, "state.json")
COMMAND_PATH   = os.path.join(APP_DATA_DIR, "command.json")
ANALYTICS_PATH = os.path.join(APP_DATA_DIR, "analytics.json")
EVENTS_PATH    = os.path.join(APP_DATA_DIR, "events.jsonl")
LOCK_PATH      = os.path.join(APP_DATA_DIR, "locusd.lock")
PROMPT_PATH    = os.path.join(APP_DATA_DIR, "prompt.json")
RESPONSE_PATH  = os.path.join(APP_DATA_DIR, "response.json")

os.makedirs(APP_DATA_DIR, exist_ok=True)
