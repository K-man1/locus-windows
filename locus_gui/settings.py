"""Settings pane — General / Blocking / Allowlists / Notifications / Advanced."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, FluentIcon as FIF, LineEdit, PasswordLineEdit,
    SegmentedWidget, Slider, StrongBodyLabel, SwitchButton, TextEdit,
)

from .config import ConfigStore, Defaults
from .theme import (
    ACCENT, BORDER, CARD, INK, INK_MUTED, SURFACE, mono, serif,
    is_dark, register_for_theme,
    SURFACE_D, SURFACE_L, BORDER_D, BORDER_L, INK_D, INK_L, INK_MUTED_D, INK_MUTED_L,
)
from .widgets import Card, FieldLabel, Header, ListEditor, ResetButton, SaveRow


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scrollable(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setStyleSheet("QScrollArea { border: none; background: transparent; }")
    sa.setWidget(inner)
    return sa


def _content_host() -> tuple[QWidget, QVBoxLayout]:
    host = QWidget()
    host.setObjectName("contentHost")
    v = QVBoxLayout(host)
    v.setContentsMargins(40, 36, 40, 40)
    v.setSpacing(22)
    v.setAlignment(Qt.AlignTop)
    return host, v


def _slider_row(label: str, value: int, lo: int, hi: int, step: int, suffix: str,
                on_change, on_reset) -> QWidget:
    wrap = QWidget()
    v = QVBoxLayout(wrap)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(6)

    head = QHBoxLayout()
    fl = FieldLabel(label)
    head.addWidget(fl)
    head.addStretch(1)
    head.addWidget(ResetButton(on_reset))
    v.addLayout(head)

    row = QHBoxLayout()
    sl = Slider(Qt.Horizontal)
    sl.setRange(lo, hi)
    sl.setSingleStep(step)
    sl.setPageStep(step)
    sl.setValue(value)
    row.addWidget(sl, 1)

    out = QLabel(f"{value} {suffix}")
    out.setFont(mono(11))
    out.setStyleSheet(f"color: {ACCENT};")
    out.setMinimumWidth(70)
    out.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    row.addWidget(out)
    v.addLayout(row)

    def _on_change(val):
        snapped = round(val / step) * step
        if snapped != val:
            sl.blockSignals(True)
            sl.setValue(int(snapped))
            sl.blockSignals(False)
        out.setText(f"{int(snapped)} {suffix}")
        on_change(int(snapped))
    sl.valueChanged.connect(_on_change)
    wrap._slider = sl
    wrap._label = out
    wrap._suffix = suffix
    return wrap


def _set_slider(wrap: QWidget, value: int):
    wrap._slider.setValue(value)
    wrap._label.setText(f"{value} {wrap._suffix}")


def _toggle_row(label: str, subtitle: str, value: bool, on_change, on_reset) -> QWidget:
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(12)

    text_col = QVBoxLayout()
    text_col.setSpacing(3)
    t = StrongBodyLabel(label)
    text_col.addWidget(t)
    if subtitle:
        s = CaptionLabel(subtitle)
        s.setWordWrap(True)
        text_col.addWidget(s)
    h.addLayout(text_col, 1)

    h.addWidget(ResetButton(on_reset))

    sw = SwitchButton()
    sw.setChecked(bool(value))
    sw.checkedChanged.connect(on_change)
    h.addWidget(sw)
    row._switch = sw
    return row


def _hr() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"background: {BORDER}; max-height: 1px; color: {BORDER};")
    return line


# ── Sub-pages ─────────────────────────────────────────────────────────────────

class GeneralPage(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()

    def _build(self):
        host, v = _content_host()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_scrollable(host))

        v.addWidget(Header("General", "Appearance and global preferences."))

        appearance_card = Card()
        head = QHBoxLayout()
        head.addWidget(FieldLabel("Appearance"))
        head.addStretch(1)
        head.addWidget(ResetButton(lambda: self._reset_appearance()))
        appearance_card.add_layout(head)

        self.appearance_seg = SegmentedWidget()
        self.appearance_seg.addItem("system", "System", lambda: self._set_appearance("system"))
        self.appearance_seg.addItem("light",  "Light",  lambda: self._set_appearance("light"))
        self.appearance_seg.addItem("dark",   "Dark",   lambda: self._set_appearance("dark"))
        self.appearance_seg.setCurrentItem(self.config.appearance)
        appearance_card.add(self.appearance_seg)

        accent_row = QHBoxLayout()
        accent_row.setSpacing(12)
        swatch = QFrame()
        swatch.setFixedSize(32, 32)
        swatch.setStyleSheet(f"background: {ACCENT}; border-radius: 6px;")
        accent_row.addWidget(swatch)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(StrongBodyLabel("Accent colour"))
        cap = CaptionLabel("Warm amber — fixed")
        col.addWidget(cap)
        accent_row.addLayout(col)
        accent_row.addStretch(1)
        appearance_card.add_layout(accent_row)

        v.addWidget(appearance_card)
        v.addWidget(SaveRow(self.config.save, self.config.load))
        v.addStretch(1)

        v.addWidget(_hr())
        reset_btn = QLabel('<a style="color:%s; text-decoration:none;" href="#">⟳  Reset All Settings</a>' % "#D6453A")
        reset_btn.setTextFormat(Qt.RichText)
        reset_btn.linkActivated.connect(self._confirm_reset)
        reset_btn.setStyleSheet("font-weight: 600; padding-top: 4px;")
        v.addWidget(reset_btn)

    def _set_appearance(self, val: str):
        self.config.appearance = val
        from .theme import apply_appearance
        apply_appearance(val)

    def _reset_appearance(self):
        self.config.appearance = Defaults.appearance
        self.appearance_seg.setCurrentItem(self.config.appearance)

    def _confirm_reset(self):
        from qfluentwidgets import MessageBox
        box = MessageBox(
            "Reset All Settings?",
            "This will restore every setting to its default value and save to config.json.",
            self.window(),
        )
        if box.exec():
            self.config.reset_all()


class BlockingPage(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()

    def _build(self):
        host, v = _content_host()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_scrollable(host))

        v.addWidget(Header("Blocking", "Timing, polling, and AI strictness."))

        timing = Card()

        self.temp_slider = _slider_row(
            "Temporary Allow Duration", self.config.temp_allow_minutes, 5, 120, 5, "min",
            on_change=lambda val: setattr(self.config, "temp_allow_minutes", val),
            on_reset=lambda: self._reset_slider("temp_slider", "temp_allow_minutes", Defaults.temp_allow_minutes),
        )
        timing.add(self._with_caption(self.temp_slider,
            "How long a temporary override lasts before the site/app is re-blocked."))
        timing.add(_hr())

        self.sched_slider = _slider_row(
            "Schedule Refresh", self.config.schedule_refresh_minutes, 1, 60, 1, "min",
            on_change=lambda val: setattr(self.config, "schedule_refresh_minutes", val),
            on_reset=lambda: self._reset_slider("sched_slider", "schedule_refresh_minutes", Defaults.schedule_refresh_minutes),
        )
        timing.add(self._with_caption(self.sched_slider,
            "How often Notion events are re-fetched in the background."))
        timing.add(_hr())

        self.url_slider = _slider_row(
            "URL Poll Interval", self.config.url_poll_seconds, 1, 10, 1, "s",
            on_change=lambda val: setattr(self.config, "url_poll_seconds", val),
            on_reset=lambda: self._reset_slider("url_slider", "url_poll_seconds", Defaults.url_poll_seconds),
        )
        timing.add(self._with_caption(self.url_slider,
            "How often Chrome tabs are checked for blocked domains."))
        timing.add(_hr())

        self.app_slider = _slider_row(
            "App Poll Interval", self.config.app_poll_seconds, 5, 60, 5, "s",
            on_change=lambda val: setattr(self.config, "app_poll_seconds", val),
            on_reset=lambda: self._reset_slider("app_slider", "app_poll_seconds", Defaults.app_poll_seconds),
        )
        timing.add(self._with_caption(self.app_slider,
            "How often running GUI apps are checked against the blocklist."))
        v.addWidget(timing)

        override = Card()
        head = QHBoxLayout()
        head.addWidget(FieldLabel("Override Code"))
        head.addStretch(1)
        head.addWidget(ResetButton(lambda: self._reset_override()))
        override.add_layout(head)
        cap = CaptionLabel('Typed to bypass the lock. Default is "bob". Set to the first 100 digits of π for maximum security.')
        cap.setWordWrap(True)
        override.add(cap)
        self.override_input = PasswordLineEdit()
        self.override_input.setText(self.config.override_code)
        self.override_input.textChanged.connect(lambda t: setattr(self.config, "override_code", t))
        override.add(self.override_input)
        v.addWidget(override)

        harsh = Card()
        head2 = QHBoxLayout()
        head2.addWidget(FieldLabel("AI Harshness"))
        head2.addStretch(1)
        head2.addWidget(ResetButton(lambda: self._reset_harsh()))
        harsh.add_layout(head2)
        cap2 = CaptionLabel("Controls how strictly the AI evaluates your justifications.")
        cap2.setWordWrap(True)
        harsh.add(cap2)

        self.harsh_seg = SegmentedWidget()
        for v_ in ["Lenient", "Standard", "Strict"]:
            self.harsh_seg.addItem(v_, v_, lambda val=v_: setattr(self.config, "harshness", val))
        self.harsh_seg.setCurrentItem(self.config.harshness if self.config.harshness in ("Lenient", "Standard", "Strict") else "Standard")
        harsh.add(self.harsh_seg)
        v.addWidget(harsh)

        v.addWidget(SaveRow(self.config.save, self.config.load))
        v.addStretch(1)

    def _with_caption(self, slider_wrap: QWidget, caption: str) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        col.addWidget(slider_wrap)
        cap = CaptionLabel(caption)
        cap.setWordWrap(True)
        col.addWidget(cap)
        return wrap

    def _reset_slider(self, attr: str, config_attr: str, default: int):
        setattr(self.config, config_attr, default)
        _set_slider(getattr(self, attr), default)

    def _reset_override(self):
        self.config.override_code = Defaults.override_code
        self.override_input.setText(Defaults.override_code)

    def _reset_harsh(self):
        self.config.harshness = Defaults.harshness
        self.harsh_seg.setCurrentItem(Defaults.harshness)


class AllowlistsPage(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()

    def _build(self):
        host, v = _content_host()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_scrollable(host))

        v.addWidget(Header("Allowlists",
            "Always-allowed apps and domains, regardless of session."))

        apps_card = Card()
        apps_card.add(FieldLabel("Always-Allowed Apps"))
        cap = CaptionLabel('These apps are never blocked, even outside the session whitelist. Add the exact process name (e.g. "Notion", "Slack").')
        cap.setWordWrap(True)
        apps_card.add(cap)
        self.apps_editor = ListEditor(self.config.always_allowed_apps, "App name (e.g. Notion)")
        self.apps_editor.changed.connect(
            lambda: setattr(self.config, "always_allowed_apps", list(self.apps_editor.items)))
        apps_card.add(self.apps_editor)
        v.addWidget(apps_card)

        domains_card = Card()
        domains_card.add(FieldLabel("Always-Allowed Domains"))
        cap2 = CaptionLabel('These domains are never blocked in Chrome. Enter bare domains without https:// (e.g. "schoology.com").')
        cap2.setWordWrap(True)
        domains_card.add(cap2)
        self.domains_editor = ListEditor(self.config.always_allowed_domains, "Domain (e.g. schoology.com)")
        self.domains_editor.changed.connect(
            lambda: setattr(self.config, "always_allowed_domains", list(self.domains_editor.items)))
        domains_card.add(self.domains_editor)
        v.addWidget(domains_card)

        v.addWidget(SaveRow(self.config.save, self._reload))
        v.addStretch(1)

    def _reload(self):
        self.config.load()
        self.apps_editor.set_items(self.config.always_allowed_apps)
        self.domains_editor.set_items(self.config.always_allowed_domains)


class NotificationsPage(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()

    def _build(self):
        host, v = _content_host()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_scrollable(host))

        v.addWidget(Header("Notifications",
            "Control what Windows notifications Locus sends."))

        card = Card()
        self.show_toggle = _toggle_row(
            "Show Notifications",
            'Displays banners like "Evaluating your reason…" and "Override accepted".',
            self.config.show_notifications,
            on_change=lambda val: setattr(self.config, "show_notifications", val),
            on_reset=lambda: self._reset_toggle("show_toggle", "show_notifications", Defaults.show_notifications),
        )
        card.add(self.show_toggle)
        card.add(_hr())
        self.sound_toggle = _toggle_row(
            "Play Sound on Block",
            "Plays a system sound when a block is triggered.",
            self.config.play_sound_on_block,
            on_change=lambda val: setattr(self.config, "play_sound_on_block", val),
            on_reset=lambda: self._reset_toggle("sound_toggle", "play_sound_on_block", Defaults.play_sound_on_block),
        )
        card.add(self.sound_toggle)
        v.addWidget(card)

        v.addWidget(SaveRow(self.config.save, self.config.load))
        v.addStretch(1)

    def _reset_toggle(self, attr: str, config_attr: str, default: bool):
        setattr(self.config, config_attr, default)
        getattr(self, attr)._switch.setChecked(default)


class AdvancedPage(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()

    def _build(self):
        host, v = _content_host()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(_scrollable(host))

        v.addWidget(Header("Advanced", "AI prompt overrides and debug options."))

        debug_card = Card()
        self.debug_toggle = _toggle_row(
            "Debug Logging",
            "Enables verbose print output in the Python backend.",
            self.config.debug_logging,
            on_change=lambda val: setattr(self.config, "debug_logging", val),
            on_reset=lambda: self._reset_toggle("debug_toggle", "debug_logging", Defaults.debug_logging),
        )
        debug_card.add(self.debug_toggle)
        v.addWidget(debug_card)

        v.addWidget(self._prompt_card(
            "Evaluate Reason Prompt",
            "Used when the user submits a justification for a blocked site/app.",
            "{session_name}, {subject_type}, {subject}, {reason}",
            "prompt_evaluate_reason",
        ))
        v.addWidget(self._prompt_card(
            "Evaluate Site Relevance Prompt",
            "Used to pre-screen whether a blocked domain is obviously relevant.",
            "{session_name}, {domain}, {title_hint}",
            "prompt_evaluate_site",
        ))
        v.addWidget(self._prompt_card(
            "Evaluate Title Prompt",
            "Used to check if a page title on a temporarily-allowed site is off-topic.",
            "{session_name}, {domain}, {tab_title}",
            "prompt_evaluate_title",
        ))

        v.addWidget(SaveRow(self.config.save, self.config.load))
        v.addStretch(1)

    def _reset_toggle(self, attr: str, config_attr: str, default: bool):
        setattr(self.config, config_attr, default)
        getattr(self, attr)._switch.setChecked(default)

    def _prompt_card(self, label: str, subtitle: str, placeholders: str, attr: str) -> Card:
        card = Card()
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(3)
        col.addWidget(FieldLabel(label))
        cap = CaptionLabel(subtitle)
        cap.setWordWrap(True)
        col.addWidget(cap)
        head.addLayout(col, 1)
        head.addWidget(ResetButton(lambda: self._reset_prompt(attr, te)))
        card.add_layout(head)

        ph = QLabel(f"Placeholders: {placeholders}")
        ph.setFont(mono(9))
        ph.setStyleSheet(f"color: {INK_MUTED};")
        card.add(ph)
        hint = CaptionLabel("Leave empty to use the built-in default prompt.")
        card.add(hint)

        te = TextEdit()
        te.setPlainText(getattr(self.config, attr))
        te.setMinimumHeight(120)
        te.textChanged.connect(lambda: setattr(self.config, attr, te.toPlainText()))
        card.add(te)
        return card

    def _reset_prompt(self, attr: str, te: TextEdit):
        setattr(self.config, attr, "")
        te.setPlainText("")


# ── Top-level Settings interface ──────────────────────────────────────────────

class SettingsInterface(QWidget):
    def __init__(self, config: ConfigStore, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsInterface")
        self.config = config
        self._build()

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("settingsSide")
        side.setFixedWidth(180)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(10, 22, 10, 14)
        sv.setSpacing(2)

        cap = QLabel("SETTINGS")
        cap.setFont(mono(9, medium=True))
        cap.setStyleSheet(f"color: {INK_MUTED}; letter-spacing: 1.5px; padding-left: 8px; padding-bottom: 6px;")
        sv.addWidget(cap)

        self.stack = QStackedWidget()
        self.stack.addWidget(GeneralPage(self.config))
        self.stack.addWidget(BlockingPage(self.config))
        self.stack.addWidget(AllowlistsPage(self.config))
        self.stack.addWidget(NotificationsPage(self.config))
        self.stack.addWidget(AdvancedPage(self.config))

        self._rows = []
        items = [
            ("General",       FIF.SETTING),
            ("Blocking",      FIF.HIDE),
            ("Allowlists",    FIF.CHECKBOX),
            ("Notifications", FIF.RINGER),
            ("Advanced",      FIF.COMMAND_PROMPT),
        ]
        for i, (name, icon) in enumerate(items):
            row = _SubNavRow(name, icon)
            row.clicked.connect(lambda _=False, idx=i: self._select(idx))
            self._rows.append(row)
            sv.addWidget(row)
        sv.addStretch(1)
        h.addWidget(side)
        h.addWidget(self.stack, 1)

        self._apply_side_theme(is_dark())
        register_for_theme(self._apply_side_theme)

        self._select(0)

    def _apply_side_theme(self, dark: bool):
        card = CARD_D if dark else "#F0EBE0"
        border = BORDER_D if dark else BORDER
        self.findChild(QFrame, "settingsSide").setStyleSheet(
            f"#settingsSide {{ background: {card}; border-right: 1px solid {border}; }}"
        )

    def _select(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for i, r in enumerate(self._rows):
            r.set_selected(i == idx)


class _SubNavRow(QWidget):
    clicked = Signal(bool)

    def __init__(self, label: str, icon, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self._label = label
        self._icon = icon
        self._selected = False
        self._build()
        register_for_theme(lambda _: self._refresh())

    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(10)
        from qfluentwidgets import IconWidget
        self._iw = IconWidget(self._icon)
        self._iw.setFixedSize(14, 14)
        h.addWidget(self._iw)
        self._lab = QLabel(self._label)
        h.addWidget(self._lab)
        h.addStretch(1)
        self._refresh()

    def set_selected(self, sel: bool):
        if self._selected != sel:
            self._selected = sel
            self._refresh()

    def _refresh(self):
        dark = is_dark()
        ink = INK_D if dark else INK_L
        sel_bg = "#3A3020" if dark else "#FDF3E0"
        if self._selected:
            self.setStyleSheet(f"background: {sel_bg}; border-radius: 7px;")
            self._lab.setStyleSheet(f"color: {ink}; font-weight: 600;")
        else:
            self.setStyleSheet("background: transparent;")
            self._lab.setStyleSheet(f"color: {ink};")

    def mousePressEvent(self, e):
        self.clicked.emit(True)
        super().mousePressEvent(e)
