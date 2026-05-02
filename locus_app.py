"""Locus — Windows desktop GUI.

Uses PySide6 + PySide6-Fluent-Widgets for a polished native-feeling shell.
Keeps the same warm cream/amber palette as the macOS app, but defers
chrome (sidebar, icons, cards, controls) to qfluentwidgets so things
align and render cleanly without hand-rolled QSS.

IPC unchanged: reads state.json, writes command.json. Daemon launched
as a subprocess on startup, same as the old tray app.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF, FluentWindow,
    LineEdit, NavigationItemPosition, PrimaryPushButton, PushButton, StrongBodyLabel,
    SubtitleLabel, TitleLabel, setTheme, setThemeColor, Theme,
)

from focuslock.paths import APP_DATA_DIR, COMMAND_PATH, STATE_PATH


# ── Palette ───────────────────────────────────────────────────────────────────

ACCENT       = "#E8A020"
ACCENT_MUTED = "#FDF3E0"
SURFACE      = "#FDFAF5"
CARD         = "#F7F2E8"
BORDER       = "#E8DFC8"
INK          = "#1A1410"
INK_MUTED    = "#7A6F60"
DANGER       = "#D6453A"

SERIF_FAMILY = "Instrument Serif"


# ── Resource helpers ──────────────────────────────────────────────────────────

def _resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_fonts():
    fonts_dir = os.path.join(_resource_dir(), "fonts")
    if not os.path.isdir(fonts_dir):
        return
    for name in os.listdir(fonts_dir):
        if name.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(fonts_dir, name))


def serif(size: int) -> QFont:
    f = QFont(SERIF_FAMILY, size)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


# ── Daemon ────────────────────────────────────────────────────────────────────

_daemon_proc: Optional[subprocess.Popen] = None


def start_daemon():
    global _daemon_proc
    try:
        base = _resource_dir()
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
        print(f"[locus] Failed to start daemon: {e}")


# ── IPC ───────────────────────────────────────────────────────────────────────

@dataclass
class BackendSession:
    title: str
    class_name: str
    event_type: str
    display_name: str


@dataclass
class BackendState:
    events: list
    session: Optional[BackendSession]
    updated_at: float
    is_running: bool


def read_state() -> BackendState:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return BackendState([], None, 0.0, False)
    sess = None
    if isinstance(raw.get("session"), dict):
        s = raw["session"]
        sess = BackendSession(
            title=s.get("title", ""),
            class_name=s.get("class_name", ""),
            event_type=s.get("event_type", ""),
            display_name=s.get("display_name", ""),
        )
    updated = float(raw.get("updated_at", 0.0) or 0.0)
    return BackendState(
        events=raw.get("events", []) or [],
        session=sess,
        updated_at=updated,
        is_running=(time.time() - updated) < 120,
    )


def send_command(cmd_type: str, data: Optional[dict] = None):
    payload = {"type": cmd_type, "data": data or {}}
    tmp = COMMAND_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, COMMAND_PATH)
    except Exception as e:
        print(f"[locus] send_command error: {e}")


# ── Lock indicator ────────────────────────────────────────────────────────────

class LockBadge(QWidget):
    """Filled circle with a centered lock glyph; switches between open/closed."""

    SIZE = 108

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._locked = False

    def set_locked(self, locked: bool):
        if self._locked != locked:
            self._locked = locked
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if self._locked:
            bg = QColor(DANGER); bg.setAlphaF(0.12)
            fg = QColor(DANGER)
        else:
            bg = QColor(ACCENT_MUTED)
            fg = QColor(ACCENT)

        p.setBrush(bg); p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self.width(), self.height())

        cx = self.width() / 2
        cy = self.height() / 2 + 4
        body_w, body_h = 36, 28
        bx, by = cx - body_w / 2, cy - body_h / 2

        path = QPainterPath()
        path.addRoundedRect(bx, by, body_w, body_h, 5, 5)
        p.setBrush(fg); p.setPen(Qt.NoPen)
        p.drawPath(path)

        # Shackle
        p.setBrush(Qt.NoBrush)
        pen = QPen(fg); pen.setWidth(4); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        sw, sh = 22, 20
        sx = cx - sw / 2
        sy = by - sh + 6
        arch = QPainterPath()
        arch.moveTo(sx, sy + sh)
        arch.arcTo(sx, sy, sw, sh * 2, 180, -180)
        p.drawPath(arch)
        if not self._locked:
            # Cut the right leg to suggest "open"
            p.setBrush(bg); p.setPen(Qt.NoPen)
            p.drawRect(int(sx + sw - 5), int(sy + sh - 3), 9, 12)


# ── Start interface ───────────────────────────────────────────────────────────

class StartInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("startInterface")
        self.state = BackendState([], None, 0.0, False)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 36, 40, 32)
        root.setSpacing(0)
        root.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        self.badge = LockBadge()
        root.addWidget(self.badge, 0, Qt.AlignHCenter)

        self.title = QLabel("Locus")
        self.title.setFont(serif(54))
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"color: {INK}; margin-top: 14px;")
        root.addWidget(self.title)

        self.status = BodyLabel("Ready to focus")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet(f"color: {INK_MUTED}; margin-top: 4px;")
        root.addWidget(self.status)

        root.addSpacing(28)

        # Card with custom-task input + start button
        self.idle_card = CardWidget()
        self.idle_card.setMaximumWidth(440)
        self.idle_card.setMinimumWidth(380)
        ic = QVBoxLayout(self.idle_card)
        ic.setContentsMargins(22, 20, 22, 20)
        ic.setSpacing(10)

        cap = CaptionLabel("WHAT ARE YOU WORKING ON?")
        cap.setStyleSheet(f"color: {INK_MUTED}; letter-spacing: 1.2px; font-weight: 600;")
        ic.addWidget(cap)

        self.task_input = LineEdit()
        self.task_input.setPlaceholderText("e.g. Write essay intro")
        self.task_input.setClearButtonEnabled(True)
        self.task_input.returnPressed.connect(self._start_custom)
        self.task_input.textChanged.connect(self._refresh_button)
        ic.addWidget(self.task_input)

        ic.addSpacing(4)

        self.start_btn = PrimaryPushButton(FIF.PLAY, "  Start Session")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self._start_custom)
        self.start_btn.setEnabled(False)
        ic.addWidget(self.start_btn)

        root.addWidget(self.idle_card, 0, Qt.AlignHCenter)

        # Active-session card (hidden until session starts)
        self.active_card = CardWidget()
        self.active_card.setMaximumWidth(440)
        self.active_card.setMinimumWidth(380)
        ac = QVBoxLayout(self.active_card)
        ac.setContentsMargins(22, 20, 22, 20)
        ac.setSpacing(8)
        ac.setAlignment(Qt.AlignHCenter)

        self.session_title = StrongBodyLabel("")
        self.session_title.setAlignment(Qt.AlignCenter)
        ac.addWidget(self.session_title)

        self.session_sub = CaptionLabel("")
        self.session_sub.setAlignment(Qt.AlignCenter)
        self.session_sub.setStyleSheet(f"color: {INK_MUTED};")
        ac.addWidget(self.session_sub)

        ac.addSpacing(10)

        end_btn = PushButton(FIF.PAUSE, "  End Session")
        end_btn.setMinimumHeight(40)
        end_btn.clicked.connect(lambda: send_command("end_session"))
        ac.addWidget(end_btn)

        root.addWidget(self.active_card, 0, Qt.AlignHCenter)
        self.active_card.hide()

        root.addStretch(1)

    def _refresh_button(self):
        self.start_btn.setEnabled(bool(self.task_input.text().strip()))

    def _start_custom(self):
        text = self.task_input.text().strip()
        if not text:
            return
        send_command("start_custom_session", {"title": text})
        self.task_input.clear()

    def apply_state(self, state: BackendState):
        self.state = state
        if state.session:
            s = state.session
            self.badge.set_locked(True)
            self.status.setText("●  " + (s.display_name or s.title))
            self.status.setStyleSheet(f"color: {DANGER}; margin-top: 4px; font-weight: 600;")
            self.session_title.setText(s.title)
            sub = s.class_name + (" · " + s.event_type if s.event_type else "")
            self.session_sub.setText(sub.strip(" ·"))
            self.idle_card.hide()
            self.active_card.show()
        else:
            self.badge.set_locked(False)
            self.status.setText("What do you want to focus on?" if state.is_running else "Starting up…")
            self.status.setStyleSheet(f"color: {INK_MUTED}; margin-top: 4px;")
            self.active_card.hide()
            self.idle_card.show()


# ── Placeholder interfaces ────────────────────────────────────────────────────

class PlaceholderInterface(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName(f"{name.lower()}Interface")
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 36, 40, 32)
        v.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        title = TitleLabel(name)
        title.setFont(serif(40))
        title.setStyleSheet(f"color: {INK};")
        v.addWidget(title)

        sub = BodyLabel("Coming soon on Windows.")
        sub.setStyleSheet(f"color: {INK_MUTED};")
        v.addWidget(sub)
        v.addStretch(1)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Locus")
        self.resize(960, 660)

        self.start_iface     = StartInterface()
        self.settings_iface  = PlaceholderInterface("Settings")
        self.connectors_iface = PlaceholderInterface("Connectors")
        self.analytics_iface = PlaceholderInterface("Analytics")

        self.addSubInterface(self.start_iface,      FIF.PLAY,        "Start")
        self.addSubInterface(self.settings_iface,   FIF.SETTING,     "Settings")
        self.addSubInterface(self.connectors_iface, FIF.LINK,        "Connectors")
        self.addSubInterface(
            self.analytics_iface, FIF.PIE_SINGLE, "Analytics",
            position=NavigationItemPosition.SCROLL,
        )

        self._poll = QTimer(self)
        self._poll.setInterval(1500)
        self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._tick()

    def _tick(self):
        try:
            self.start_iface.apply_state(read_state())
        except Exception as e:
            print(f"[locus] poll error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Locus")
    app.setOrganizationName("Locus")

    load_fonts()
    setTheme(Theme.LIGHT)
    setThemeColor(QColor(ACCENT))

    start_daemon()

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
