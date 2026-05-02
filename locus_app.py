"""Locus — Windows desktop GUI entry point."""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from qfluentwidgets import (
    FluentIcon as FIF, FluentWindow, NavigationItemPosition, Theme, setTheme, setThemeColor,
)

from focuslock.paths import APP_DATA_DIR

from locus_gui.analytics import AnalyticsInterface
from locus_gui.config import ConfigStore
from locus_gui.connectors import ConnectorsInterface
from locus_gui.settings import SettingsInterface
from locus_gui.start import StartInterface
from locus_gui.theme import ACCENT, load_fonts, resource_dir, apply_appearance


# ── Daemon launch ─────────────────────────────────────────────────────────────

_daemon_proc: subprocess.Popen | None = None


def _daemon_already_running() -> bool:
    """Return True if a live locusd process owns the lock file."""
    from focuslock.paths import LOCK_PATH
    try:
        with open(LOCK_PATH) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # signal 0 = liveness probe; raises if dead
        return True
    except Exception:
        return False


def start_daemon():
    global _daemon_proc
    if _daemon_already_running():
        print("[locus] daemon already running, skipping launch")
        return
    try:
        base = resource_dir()
        if getattr(sys, "frozen", False):
            cmd = [os.path.join(base, "locusd.exe")]
        else:
            cmd = [sys.executable, os.path.join(base, "locusd_entry.py")]
        _daemon_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print(f"[locus] failed to start daemon: {e}")


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(FluentWindow):
    def __init__(self, config: ConfigStore):
        super().__init__()
        self.config = config
        self.setWindowTitle("Locus")
        self.resize(1000, 680)

        self.start_iface      = StartInterface()
        self.settings_iface   = SettingsInterface(config)
        self.connectors_iface = ConnectorsInterface(config)
        self.analytics_iface  = AnalyticsInterface()

        self.addSubInterface(self.start_iface,      FIF.PLAY,    "Start")
        self.addSubInterface(self.settings_iface,   FIF.SETTING, "Settings")
        self.addSubInterface(self.connectors_iface, FIF.LINK,    "Connectors")
        self.addSubInterface(
            self.analytics_iface, FIF.PIE_SINGLE, "Analytics",
            position=NavigationItemPosition.SCROLL,
        )

        self.navigationInterface.setExpandWidth(220)

        # Re-apply theme when config is saved (e.g. reload from disk)
        config.changed.connect(lambda: apply_appearance(config.appearance))


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(APP_DATA_DIR, exist_ok=True)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Locus")
    app.setOrganizationName("Locus")

    load_fonts()

    # Suppress text-selection highlight across all labels
    app.setStyleSheet(
        "QLabel { selection-background-color: transparent; selection-color: inherit; }"
    )

    config = ConfigStore()

    # Apply initial theme before building the window so all widgets start correctly
    apply_appearance(config.appearance)
    setThemeColor(QColor(ACCENT))

    start_daemon()

    win = MainWindow(config)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
