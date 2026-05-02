"""Start pane — lock badge, custom-task input, active session display."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon as FIF, LineEdit,
    PrimaryPushButton, PushButton, StrongBodyLabel,
)

from focuslock.paths import COMMAND_PATH, STATE_PATH

from .theme import (
    ACCENT, ACCENT_MUTED, BORDER, CARD, DANGER, INK, INK_MUTED, serif,
    is_dark, register_for_theme,
    CARD_D, BORDER_D, INK_D, INK_L, INK_MUTED_D, INK_MUTED_L,
)


def _make_card() -> QFrame:
    f = QFrame()
    f.setObjectName("startCard")
    return f


def _apply_card_style(card: QFrame, dark: bool):
    card_bg = CARD_D if dark else CARD
    border = BORDER_D if dark else BORDER
    card.setStyleSheet(
        f"#startCard {{ background: {card_bg}; border: 1px solid {border}; "
        f"border-radius: 12px; }}"
    )


# ── State ─────────────────────────────────────────────────────────────────────

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


# ── Lock badge ────────────────────────────────────────────────────────────────

class LockBadge(QWidget):
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
        body_w, body_h = 38, 30
        bx = cx - body_w / 2
        by = self.height() / 2 - 2

        sw = 26
        leg_left  = cx - sw / 2
        leg_right = cx + sw / 2
        arch_top  = by - 18
        leg_bot   = by + 1

        body = QPainterPath()
        body.addRoundedRect(bx, by, body_w, body_h, 6, 6)
        p.setBrush(fg); p.setPen(Qt.NoPen)
        p.drawPath(body)

        pen = QPen(fg)
        pen.setWidth(4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        sh = QPainterPath()
        if self._locked:
            sh.moveTo(leg_left, leg_bot)
            sh.lineTo(leg_left, arch_top + 8)
            sh.arcTo(leg_left, arch_top, sw, 16, 180, -180)
            sh.lineTo(leg_right, leg_bot)
        else:
            sh.moveTo(leg_left, leg_bot)
            sh.lineTo(leg_left, arch_top + 8)
            sh.arcTo(leg_left, arch_top, sw, 16, 180, -180)
            sh.lineTo(leg_right, arch_top + 12)
        p.drawPath(sh)


# ── Pane ──────────────────────────────────────────────────────────────────────

class StartInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("startInterface")
        self.state = BackendState([], None, 0.0, False)
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

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

        self.idle_card = self._build_idle()
        self.idle_card.setMaximumWidth(440)
        self.idle_card.setMinimumWidth(380)
        root.addWidget(self.idle_card, 0, Qt.AlignHCenter)

        self.active_card = self._build_active()
        self.active_card.setMaximumWidth(440)
        self.active_card.setMinimumWidth(380)
        root.addWidget(self.active_card, 0, Qt.AlignHCenter)
        self.active_card.hide()

        root.addStretch(1)

        self._apply_theme(is_dark())
        register_for_theme(self._apply_theme)

    def _apply_theme(self, dark: bool):
        ink = INK_D if dark else INK_L
        self.title.setStyleSheet(f"color: {ink}; margin-top: 14px;")
        _apply_card_style(self.idle_card, dark)
        _apply_card_style(self.active_card, dark)

    def _build_idle(self) -> QFrame:
        card = _make_card()
        v = QVBoxLayout(card)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(10)

        cap = CaptionLabel("WHAT ARE YOU WORKING ON?")
        cap.setStyleSheet(f"letter-spacing: 1.4px; font-weight: 600;")
        v.addWidget(cap)

        self.task_input = LineEdit()
        self.task_input.setPlaceholderText("e.g. Write essay intro")
        self.task_input.setClearButtonEnabled(True)
        self.task_input.returnPressed.connect(self._start_custom)
        self.task_input.textChanged.connect(self._refresh_button)
        v.addWidget(self.task_input)

        v.addSpacing(4)

        self.start_btn = PrimaryPushButton(FIF.PLAY, "  Start Session")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self._start_custom)
        self.start_btn.setEnabled(False)
        v.addWidget(self.start_btn)
        return card

    def _build_active(self) -> QFrame:
        card = _make_card()
        v = QVBoxLayout(card)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(8)
        v.setAlignment(Qt.AlignHCenter)

        self.session_title = StrongBodyLabel("")
        self.session_title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.session_title)

        self.session_sub = CaptionLabel("")
        self.session_sub.setAlignment(Qt.AlignCenter)
        v.addWidget(self.session_sub)

        v.addSpacing(10)
        end_btn = PushButton(FIF.PAUSE, "  End Session")
        end_btn.setMinimumHeight(40)
        end_btn.clicked.connect(lambda: send_command("end_session"))
        v.addWidget(end_btn)
        return card

    def _refresh_button(self):
        self.start_btn.setEnabled(bool(self.task_input.text().strip()))

    def _start_custom(self):
        text = self.task_input.text().strip()
        if not text:
            return
        send_command("start_custom_session", {"title": text})
        self.task_input.clear()

    def refresh(self):
        try:
            state = read_state()
        except Exception as e:
            print(f"[locus] start poll error: {e}")
            return
        self.state = state

        # Only show locked state when the daemon is actively running
        if state.session and state.is_running:
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
            dark = is_dark()
            muted = INK_MUTED_D if dark else INK_MUTED
            self.status.setText("What do you want to focus on?" if state.is_running else "Starting up…")
            self.status.setStyleSheet(f"color: {muted}; margin-top: 4px;")
            self.active_card.hide()
            self.idle_card.show()
