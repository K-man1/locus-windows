"""Watches prompt.json and shows native Locus dialogs — replaces Swift/tkinter prompts."""

from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon as FIF,
    PasswordLineEdit, PrimaryPushButton, PushButton, StrongBodyLabel,
)

from focuslock.paths import PROMPT_PATH, RESPONSE_PATH
from .theme import ACCENT, DANGER, INK, INK_MUTED, is_dark, serif, mono
from .widgets import Card


# ── Base dialog ────────────────────────────────────────────────────────────

class _LocusDialog(QDialog):
    """Frameless, always-on-top dialog styled to match the Locus aesthetic."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setModal(True)
        self.result_data: dict = {"action": "cancel"}
        self._build_ui()
        self._apply_style()

    def _apply_style(self):
        dark = is_dark()
        bg = "#1E1E1E" if dark else "#FFFFFF"
        border = "#404040" if dark else "#E0D8C8"
        ink = "#F0EBE0" if dark else "#1A1410"
        self.setStyleSheet(
            f"_LocusDialog, QDialog {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: 16px; }}"
            f"QLabel {{ color: {ink}; background: transparent; }}"
            f"QTextEdit {{ border-radius: 8px; padding: 6px; }}"
        )

    def _build_ui(self):
        pass  # subclasses implement


# ── Reason dialog ─────────────────────────────────────────────────────────

class _ReasonDialog(_LocusDialog):
    def __init__(self, prompt: dict, off_topic: bool = False, parent=None):
        self._prompt = prompt
        self._off_topic = off_topic
        super().__init__(parent)
        self.setFixedWidth(440)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        blocked = self._prompt.get("blocked_name", "")
        btype = self._prompt.get("blocked_type", "")
        session = self._prompt.get("session_name", "Focus Session")
        ai_reason = self._prompt.get("ai_reason", "")

        # Header
        lbl_app = QLabel(f"Locus blocked “{blocked}”")
        lbl_app.setFont(serif(20))
        lbl_app.setWordWrap(True)
        root.addWidget(lbl_app)

        lbl_sess = CaptionLabel(f"Session: {session}")
        root.addWidget(lbl_sess)

        if ai_reason:
            lbl_ai = CaptionLabel(f"AI flagged: {ai_reason}")
            lbl_ai.setWordWrap(True)
            root.addWidget(lbl_ai)

        # Reason input
        ph_lbl = QLabel("Why do you need access?")
        ph_lbl.setStyleSheet(f"color: {INK_MUTED}; font-size: 12px;")
        root.addWidget(ph_lbl)

        self._reason_edit = QTextEdit()
        self._reason_edit.setFixedHeight(80)
        self._reason_edit.setPlaceholderText("Type your reason here…")
        dark = is_dark()
        edit_bg = "#2A2A2A" if dark else "#F7F2E8"
        edit_border = "#404040" if dark else "#D8CEB8"
        edit_fg = "#F0EBE0" if dark else "#1A1410"
        self._reason_edit.setStyleSheet(
            f"QTextEdit {{ background: {edit_bg}; border: 1px solid {edit_border}; "
            f"border-radius: 8px; color: {edit_fg}; padding: 8px; font-size: 13px; }}"
        )
        root.addWidget(self._reason_edit)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        submit_btn = PrimaryPushButton("Submit")
        submit_btn.setMinimumHeight(36)
        submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(submit_btn, 1)

        override_btn = PushButton("Override")
        override_btn.setMinimumHeight(36)
        override_btn.clicked.connect(self._on_override)
        btn_row.addWidget(override_btn, 1)

        cancel_btn = PushButton("Cancel")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.setStyleSheet(f"QPushButton {{ color: {DANGER}; }}")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn, 1)

        root.addLayout(btn_row)
        self.adjustSize()

    def _on_submit(self):
        reason = self._reason_edit.toPlainText().strip()
        self.result_data = {"action": "submit", "reason": reason}
        self.accept()

    def _on_override(self):
        self.result_data = {"action": "override", "reason": ""}
        self.accept()

    def _on_cancel(self):
        self.result_data = {"action": "cancel", "reason": ""}
        self.reject()


# ── Override dialog ───────────────────────────────────────────────────────

class _OverrideDialog(_LocusDialog):
    def __init__(self, prompt: dict, parent=None):
        self._prompt = prompt
        super().__init__(parent)
        self.setFixedWidth(340)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        hint = "Pi override" if self._prompt.get("is_pi_hint") else "Enter override code"
        lbl = QLabel(hint)
        lbl.setFont(serif(20))
        root.addWidget(lbl)

        self._code_edit = PasswordLineEdit()
        self._code_edit.setMinimumHeight(36)
        self._code_edit.returnPressed.connect(self._on_submit)
        root.addWidget(self._code_edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        submit_btn = PrimaryPushButton("Submit")
        submit_btn.setMinimumHeight(36)
        submit_btn.clicked.connect(self._on_submit)
        btn_row.addWidget(submit_btn, 1)
        cancel_btn = PushButton("Cancel")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn, 1)
        root.addLayout(btn_row)
        self.adjustSize()

    def _on_submit(self):
        self.result_data = {"action": "submit", "code": self._code_edit.text()}
        self.accept()

    def _on_cancel(self):
        self.result_data = {"action": "cancel", "code": ""}
        self.reject()


# ── Result dialog ─────────────────────────────────────────────────────────

class _ResultDialog(_LocusDialog):
    def __init__(self, prompt: dict, parent=None):
        self._prompt = prompt
        super().__init__(parent)
        self.setFixedWidth(360)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        approved = bool(self._prompt.get("approved"))
        explanation = self._prompt.get("explanation", "")
        target = self._prompt.get("target_name", "")
        minutes = self._prompt.get("minutes", 15)

        icon_lbl = QLabel("✓" if approved else "✗")
        icon_lbl.setFont(serif(36))
        color = "#2EA66B" if approved else DANGER
        icon_lbl.setStyleSheet(f"color: {color};")
        icon_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(icon_lbl)

        verdict = "Approved" if approved else "Denied"
        v_lbl = QLabel(verdict)
        v_lbl.setFont(serif(22))
        v_lbl.setStyleSheet(f"color: {color};")
        v_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(v_lbl)

        if approved and minutes:
            m_lbl = CaptionLabel(f"Allowed for {minutes} min")
            m_lbl.setAlignment(Qt.AlignCenter)
            root.addWidget(m_lbl)

        if explanation:
            ex_lbl = BodyLabel(explanation)
            ex_lbl.setWordWrap(True)
            ex_lbl.setAlignment(Qt.AlignCenter)
            root.addWidget(ex_lbl)

        ok_btn = PrimaryPushButton("OK")
        ok_btn.setMinimumHeight(36)
        ok_btn.clicked.connect(self.accept)
        root.addWidget(ok_btn)

        # Auto-dismiss after 6 seconds
        self._countdown = 6
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(1000)
        self._auto_timer.timeout.connect(self._tick)
        self._auto_timer.start()
        self.adjustSize()

    def _tick(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._auto_timer.stop()
            self.accept()


# ── Handler widget ────────────────────────────────────────────────────────

class PromptHandler(QWidget):
    """Invisible widget that polls prompt.json and shows dialogs on the main thread."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide()
        self._handling = False
        self._last_id: str | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _poll(self):
        if self._handling:
            return
        if not os.path.exists(PROMPT_PATH):
            return
        try:
            with open(PROMPT_PATH) as f:
                prompt = json.load(f)
        except Exception:
            return
        pid = prompt.get("id")
        if not pid or pid == self._last_id:
            return
        self._last_id = pid
        self._handling = True
        try:
            self._dispatch(prompt, pid)
        finally:
            self._handling = False

    def _dispatch(self, prompt: dict, pid: str):
        ptype = prompt.get("type")
        parent = self.window()

        if ptype in ("ask_reason", "ask_off_topic"):
            dlg = _ReasonDialog(prompt, off_topic=(ptype == "ask_off_topic"), parent=parent)
            dlg.exec()
            resp = dlg.result_data
        elif ptype == "ask_override":
            dlg = _OverrideDialog(prompt, parent=parent)
            dlg.exec()
            resp = dlg.result_data
        elif ptype == "show_result":
            dlg = _ResultDialog(prompt, parent=parent)
            dlg.exec()
            resp = {"action": "ok"}
        else:
            resp = {"action": "cancel"}

        self._write_response(pid, resp)

    def _write_response(self, pid: str, data: dict):
        data["id"] = pid
        tmp = RESPONSE_PATH + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, RESPONSE_PATH)
        except Exception as e:
            print(f"[locus] response write error: {e}")
        try:
            os.remove(PROMPT_PATH)
        except Exception:
            pass
