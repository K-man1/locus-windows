"""Locus — Windows desktop GUI (PySide6).

A real shippable app: launches from Start menu, shows sidebar + panes,
talks to the locusd daemon via state.json / command.json (same IPC as the
macOS SwiftUI app and the Windows tray app it replaces).

This is the first cut: Start pane is fully implemented; other panes are
placeholders that will be filled in in subsequent passes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from focuslock.paths import APP_DATA_DIR, COMMAND_PATH, STATE_PATH


# ── Theme ─────────────────────────────────────────────────────────────────────

ACCENT       = "#E8A020"
ACCENT_MUTED = "#FDF3E0"
SURFACE      = "#FDFAF5"
CARD         = "#F7F2E8"
BORDER       = "#E8DFC8"
INK          = "#1A1410"
INK_MUTED    = "#7A6F60"
DANGER       = "#D6453A"

SERIF_FAMILY = "Instrument Serif"
MONO_FAMILY  = "DM Mono"


def load_fonts():
    base = _resource_dir()
    fonts_dir = os.path.join(base, "fonts")
    if not os.path.isdir(fonts_dir):
        return
    for name in os.listdir(fonts_dir):
        if name.lower().endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(fonts_dir, name))


def _resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def serif(size: int) -> QFont:
    f = QFont(SERIF_FAMILY, size)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def ui(size: int, weight: QFont.Weight = QFont.Normal) -> QFont:
    f = QFont("Segoe UI", size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


# ── Daemon launch ─────────────────────────────────────────────────────────────

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


# ── IPC helpers ───────────────────────────────────────────────────────────────

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
    sess_raw = raw.get("session")
    sess = None
    if isinstance(sess_raw, dict):
        sess = BackendSession(
            title=sess_raw.get("title", ""),
            class_name=sess_raw.get("class_name", ""),
            event_type=sess_raw.get("event_type", ""),
            display_name=sess_raw.get("display_name", ""),
        )
    updated = float(raw.get("updated_at", 0.0) or 0.0)
    fresh = (time.time() - updated) < 120
    return BackendState(
        events=raw.get("events", []) or [],
        session=sess,
        updated_at=updated,
        is_running=fresh,
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


# ── Custom widgets ────────────────────────────────────────────────────────────

class IconCircle(QWidget):
    """Filled circle with a centered glyph — used for the big lock indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 100)
        self._locked = False

    def set_locked(self, locked: bool):
        if self._locked != locked:
            self._locked = locked
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if self._locked:
            bg = QColor(DANGER)
            bg.setAlphaF(0.10)
            fg = QColor(DANGER)
        else:
            bg = QColor(ACCENT_MUTED)
            fg = QColor(ACCENT)

        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self.width(), self.height())

        # Lock glyph: simple body + shackle
        cx, cy = self.width() / 2, self.height() / 2 + 4
        body_w, body_h = 32, 26
        body_x, body_y = cx - body_w / 2, cy - body_h / 2

        p.setBrush(fg)
        p.setPen(Qt.NoPen)
        path = QPainterPath()
        path.addRoundedRect(body_x, body_y, body_w, body_h, 5, 5)
        p.drawPath(path)

        # Shackle
        p.setBrush(Qt.NoBrush)
        pen = QPen(fg)
        pen.setWidth(4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        sh_w, sh_h = 20, 18
        sh_x = cx - sh_w / 2
        sh_y = body_y - sh_h + 4
        if self._locked:
            # Closed shackle: full arch attached on both sides
            arch = QPainterPath()
            arch.moveTo(sh_x, sh_y + sh_h)
            arch.arcTo(sh_x, sh_y, sh_w, sh_h * 2, 180, -180)
            p.drawPath(arch)
        else:
            # Open shackle: arch with right leg lifted
            arch = QPainterPath()
            arch.moveTo(sh_x, sh_y + sh_h + 2)
            arch.arcTo(sh_x, sh_y, sh_w, sh_h * 2, 180, -180)
            # break right leg
            p.drawPath(arch)
            p.setBrush(bg)
            p.setPen(Qt.NoPen)
            p.drawRect(int(sh_x + sh_w - 5), int(sh_y + sh_h - 4), 8, 12)


class SidebarRow(QPushButton):
    def __init__(self, label: str, glyph: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self._label = label
        self._glyph = glyph
        self._build()

    def _build(self):
        self.setText(f"  {self._glyph}   {self._label}")
        self.setFont(ui(11))
        self.setStyleSheet(self._stylesheet())

    def _stylesheet(self):
        return f"""
            QPushButton {{
                text-align: left;
                padding-left: 14px;
                border: none;
                border-radius: 8px;
                background: transparent;
                color: {INK};
            }}
            QPushButton:hover {{
                background: rgba(232, 160, 32, 0.08);
            }}
            QPushButton:checked {{
                background: {ACCENT_MUTED};
                font-weight: 600;
            }}
        """


class PrimaryButton(QPushButton):
    def __init__(self, text: str, wide: bool = False, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(ui(10, QFont.DemiBold))
        h = 40 if wide else 32
        self.setMinimumHeight(h)
        radius = 12 if wide else 8
        pad_h = 28 if wide else 16
        self.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: rgba(0,0,0,0.85);
                border: none;
                border-radius: {radius}px;
                padding: 0 {pad_h}px;
                font-weight: 600;
            }}
            QPushButton:hover  {{ background: #F0AC2F; }}
            QPushButton:pressed{{ background: #C98D1B; }}
            QPushButton:disabled {{ background: rgba(232,160,32,0.4); color: rgba(0,0,0,0.4); }}
        """)


# ── Pane: Start ───────────────────────────────────────────────────────────────

class StartPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = BackendState([], None, 0.0, False)
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 28, 0, 0)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        self.icon = IconCircle()
        outer.addWidget(self.icon, 0, Qt.AlignHCenter)

        self.title = QLabel("Locus")
        self.title.setFont(serif(48))
        self.title.setStyleSheet(f"color: {INK}; margin-top: 12px;")
        self.title.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.title)

        self.status = QLabel("Ready to focus")
        self.status.setFont(ui(10))
        self.status.setStyleSheet(f"color: {INK_MUTED}; margin-top: 6px;")
        self.status.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.status)

        outer.addSpacing(28)

        # Body container — swaps between idle / session-active
        self.body = QStackedWidget()
        self.body.setMaximumWidth(460)
        self.body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        outer.addWidget(self.body, 0, Qt.AlignHCenter)

        self.body.addWidget(self._build_idle())
        self.body.addWidget(self._build_active())

        outer.addStretch(1)

    def _build_idle(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 0, 32, 0)
        v.setSpacing(10)

        cap = QLabel("WHAT ARE YOU WORKING ON?")
        cap.setFont(ui(8, QFont.DemiBold))
        cap.setStyleSheet(f"color: {INK_MUTED}; letter-spacing: 1px;")
        v.addWidget(cap)

        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("e.g. Write essay intro")
        self.task_input.setFont(ui(11))
        self.task_input.setMinimumHeight(34)
        self.task_input.setStyleSheet(f"""
            QLineEdit {{
                background: white;
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 0 10px;
                color: {INK};
            }}
            QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
        """)
        self.task_input.returnPressed.connect(self._start_custom)
        self.task_input.textChanged.connect(self._refresh_button)
        v.addWidget(self.task_input)

        v.addSpacing(8)

        self.start_btn = PrimaryButton("▶  Start Session", wide=True)
        self.start_btn.clicked.connect(self._start_custom)
        self.start_btn.setEnabled(False)
        v.addWidget(self.start_btn, 0, Qt.AlignHCenter)

        return w

    def _build_active(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 0, 32, 0)
        v.setSpacing(6)
        v.setAlignment(Qt.AlignHCenter)

        self.session_title = QLabel("")
        self.session_title.setFont(ui(12, QFont.DemiBold))
        self.session_title.setStyleSheet(f"color: {INK};")
        self.session_title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.session_title)

        self.session_sub = QLabel("")
        self.session_sub.setFont(ui(10))
        self.session_sub.setStyleSheet(f"color: {INK_MUTED};")
        self.session_sub.setAlignment(Qt.AlignCenter)
        v.addWidget(self.session_sub)

        v.addSpacing(20)

        end_btn = PrimaryButton("■  End Session", wide=True)
        end_btn.clicked.connect(lambda: send_command("end_session"))
        v.addWidget(end_btn, 0, Qt.AlignHCenter)

        return w

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
            self.icon.set_locked(True)
            self.status.setText("● " + (s.display_name or s.title))
            self.status.setStyleSheet(f"color: {DANGER}; margin-top: 6px; font-weight: 600;")
            self.session_title.setText(s.title)
            sub = s.class_name + (" · " + s.event_type if s.event_type else "")
            self.session_sub.setText(sub.strip(" ·"))
            self.body.setCurrentIndex(1)
        else:
            self.icon.set_locked(False)
            if state.is_running:
                self.status.setText("What do you want to focus on?")
            else:
                self.status.setText("Starting up…")
            self.status.setStyleSheet(f"color: {INK_MUTED}; margin-top: 6px;")
            self.body.setCurrentIndex(0)


class PlaceholderPane(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignCenter)
        title = QLabel(name)
        title.setFont(serif(36))
        title.setStyleSheet(f"color: {INK};")
        title.setAlignment(Qt.AlignCenter)
        v.addWidget(title)
        sub = QLabel("Coming soon on Windows.")
        sub.setFont(ui(11))
        sub.setStyleSheet(f"color: {INK_MUTED};")
        sub.setAlignment(Qt.AlignCenter)
        v.addWidget(sub)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Locus")
        self.resize(900, 620)
        self.setMinimumSize(760, 520)
        self._build()
        self._build_polling()

    def _build(self):
        root = QWidget()
        root.setStyleSheet(f"background: {SURFACE};")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ── Sidebar ─────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background: {SURFACE}; border-right: 1px solid {BORDER};")
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(12, 22, 12, 16)
        sv.setSpacing(2)

        # Brand
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 0, 0, 16)
        brand_lock = QLabel("🔒")
        brand_lock.setStyleSheet(f"color: {ACCENT}; font-size: 14px;")
        brand_text = QLabel("Locus")
        brand_text.setFont(serif(22))
        brand_text.setStyleSheet(f"color: {INK};")
        brand_row.addWidget(brand_lock)
        brand_row.addWidget(brand_text)
        brand_row.addStretch(1)
        brand_wrap = QWidget()
        brand_wrap.setLayout(brand_row)
        sv.addWidget(brand_wrap)

        self.rows = []
        for label, glyph in [
            ("Start",      "▶"),
            ("Settings",   "⚙"),
            ("Connectors", "↯"),
            ("Analytics",  "▮▮"),
        ]:
            row = SidebarRow(label, glyph)
            row.clicked.connect(lambda _=False, n=label: self._select(n))
            self.rows.append((label, row))
            sv.addWidget(row)
        sv.addStretch(1)

        h.addWidget(sidebar)

        # ── Detail stack ────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {SURFACE};")
        self.start_pane = StartPane()
        self.stack.addWidget(self.start_pane)
        self.stack.addWidget(PlaceholderPane("Settings"))
        self.stack.addWidget(PlaceholderPane("Connectors"))
        self.stack.addWidget(PlaceholderPane("Analytics"))
        h.addWidget(self.stack, 1)

        # Default selection
        self.rows[0][1].setChecked(True)
        self.stack.setCurrentIndex(0)

    def _select(self, name: str):
        idx_map = {"Start": 0, "Settings": 1, "Connectors": 2, "Analytics": 3}
        idx = idx_map.get(name, 0)
        self.stack.setCurrentIndex(idx)
        for label, row in self.rows:
            row.setChecked(label == name)

    def _build_polling(self):
        self._poll = QTimer(self)
        self._poll.setInterval(1500)
        self._poll.timeout.connect(self._tick)
        self._poll.start()
        self._tick()

    def _tick(self):
        try:
            self.start_pane.apply_state(read_state())
        except Exception as e:
            print(f"[locus] poll error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName("Locus")
    app.setOrganizationName("Locus")
    load_fonts()
    start_daemon()
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
