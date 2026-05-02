"""ConfigStore — load/save config.json, mirror the macOS ConfigStore.

Acts as the single source of truth for every Settings/Connectors pane.
Emits ``changed`` so dependent UI can react if needed.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import List

from PySide6.QtCore import QObject, Signal

from focuslock.paths import CONFIG_PATH, COMMAND_PATH


# ── Defaults ──────────────────────────────────────────────────────────────────

class Defaults:
    temp_allow_minutes        = 15
    url_poll_seconds          = 3
    app_poll_seconds          = 5
    schedule_refresh_minutes  = 5
    override_code             = "bob"
    harshness                 = "Standard"
    appearance                = "system"
    show_notifications        = True
    play_sound_on_block       = False
    debug_logging             = False
    evaluate_reason_prompt    = ""
    evaluate_site_prompt      = ""
    evaluate_title_prompt     = ""


@dataclass
class ICalFeed:
    name: str
    url: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ConfigStore(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._raw: dict = {}

        # Notion
        self.notion_api_key = ""
        self.notion_database_id = ""
        self.notion_enabled = False

        # iCal
        self.ical_feeds: List[ICalFeed] = []

        # Blocking timing
        self.override_code           = Defaults.override_code
        self.temp_allow_minutes      = Defaults.temp_allow_minutes
        self.url_poll_seconds        = Defaults.url_poll_seconds
        self.app_poll_seconds        = Defaults.app_poll_seconds
        self.schedule_refresh_minutes = Defaults.schedule_refresh_minutes

        # Appearance / behaviour
        self.appearance         = Defaults.appearance
        self.harshness          = Defaults.harshness
        self.always_allowed_apps: List[str]    = []
        self.always_allowed_domains: List[str] = []
        self.show_notifications = Defaults.show_notifications
        self.play_sound_on_block = Defaults.play_sound_on_block

        # Advanced
        self.debug_logging         = Defaults.debug_logging
        self.prompt_evaluate_reason = Defaults.evaluate_reason_prompt
        self.prompt_evaluate_site   = Defaults.evaluate_site_prompt
        self.prompt_evaluate_title  = Defaults.evaluate_title_prompt

        self.load()

    def load(self):
        if not os.path.isfile(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return
        self._raw = raw or {}

        api_keys = raw.get("api_keys") or {}
        self.notion_api_key = api_keys.get("notion", "") or ""
        self.notion_database_id = raw.get("notion_database_id", "") or ""
        if isinstance(raw.get("notion_enabled"), bool):
            self.notion_enabled = raw["notion_enabled"]
        else:
            self.notion_enabled = bool(self.notion_api_key) and self.notion_api_key != "YOUR_NOTION_API_KEY"

        feeds = raw.get("ical_feeds") or []
        self.ical_feeds = [
            ICalFeed(name=f.get("name", "") or "", url=f.get("url", "") or "")
            for f in feeds if (f.get("url") or "").strip()
        ]

        self.override_code            = raw.get("override_code", Defaults.override_code) or ""
        self.temp_allow_minutes       = int(raw.get("temporary_allow_minutes", Defaults.temp_allow_minutes))
        self.url_poll_seconds         = int(raw.get("url_poll_interval_seconds", Defaults.url_poll_seconds))
        self.app_poll_seconds         = int(raw.get("app_poll_interval_seconds", Defaults.app_poll_seconds))
        self.schedule_refresh_minutes = int(raw.get("schedule_refresh_minutes", Defaults.schedule_refresh_minutes))

        self.appearance        = raw.get("appearance", Defaults.appearance)
        self.harshness         = raw.get("harshness", Defaults.harshness)
        self.always_allowed_apps    = list(raw.get("always_allowed_apps", []) or [])
        self.always_allowed_domains = list(raw.get("always_allowed_domains", []) or [])
        self.show_notifications  = bool(raw.get("show_notifications", Defaults.show_notifications))
        self.play_sound_on_block = bool(raw.get("play_sound_on_block", Defaults.play_sound_on_block))
        self.debug_logging       = bool(raw.get("debug_logging", Defaults.debug_logging))

        prompts = raw.get("prompts") or {}
        self.prompt_evaluate_reason = prompts.get("evaluate_reason", Defaults.evaluate_reason_prompt) or ""
        self.prompt_evaluate_site   = prompts.get("evaluate_site_relevance", Defaults.evaluate_site_prompt) or ""
        self.prompt_evaluate_title  = prompts.get("evaluate_title", Defaults.evaluate_title_prompt) or ""

        self.changed.emit()

    def save(self):
        out = dict(self._raw)
        api_keys = dict(out.get("api_keys") or {})
        api_keys["notion"] = self.notion_api_key
        out["api_keys"] = api_keys
        out["notion_database_id"] = self.notion_database_id
        out["notion_enabled"] = self.notion_enabled

        out["ical_feeds"] = [{"name": f.name, "url": f.url} for f in self.ical_feeds]
        out["override_code"] = self.override_code
        out["temporary_allow_minutes"] = int(self.temp_allow_minutes)
        out["url_poll_interval_seconds"] = int(self.url_poll_seconds)
        out["app_poll_interval_seconds"] = int(self.app_poll_seconds)
        out["schedule_refresh_minutes"] = int(self.schedule_refresh_minutes)

        out["appearance"] = self.appearance
        out["harshness"] = self.harshness
        out["always_allowed_apps"] = list(self.always_allowed_apps)
        out["always_allowed_domains"] = list(self.always_allowed_domains)
        out["show_notifications"] = bool(self.show_notifications)
        out["play_sound_on_block"] = bool(self.play_sound_on_block)
        out["debug_logging"] = bool(self.debug_logging)
        out["prompts"] = {
            "evaluate_reason": self.prompt_evaluate_reason,
            "evaluate_site_relevance": self.prompt_evaluate_site,
            "evaluate_title": self.prompt_evaluate_title,
        }
        self._raw = out

        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True)
        os.replace(tmp, CONFIG_PATH)
        self.changed.emit()

    def reset_all(self):
        self.override_code              = Defaults.override_code
        self.temp_allow_minutes         = Defaults.temp_allow_minutes
        self.url_poll_seconds           = Defaults.url_poll_seconds
        self.app_poll_seconds           = Defaults.app_poll_seconds
        self.schedule_refresh_minutes   = Defaults.schedule_refresh_minutes
        self.appearance                 = Defaults.appearance
        self.harshness                  = Defaults.harshness
        self.always_allowed_apps        = []
        self.always_allowed_domains     = []
        self.show_notifications         = Defaults.show_notifications
        self.play_sound_on_block        = Defaults.play_sound_on_block
        self.debug_logging              = Defaults.debug_logging
        self.prompt_evaluate_reason     = Defaults.evaluate_reason_prompt
        self.prompt_evaluate_site       = Defaults.evaluate_site_prompt
        self.prompt_evaluate_title      = Defaults.evaluate_title_prompt
        self.notion_enabled             = False
        self.save()

    # ── Daemon notifications ──────────────────────────────────────────────────

    @staticmethod
    def _send_command(cmd_type: str, data: dict | None = None):
        payload = {"type": cmd_type, "data": data or {}}
        tmp = COMMAND_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, COMMAND_PATH)
        except Exception as e:
            print(f"[locus] config command error: {e}")

    def notify_notion_changed(self):
        self._send_command("reconnect_notion")

    def notify_ical_changed(self):
        self._send_command("reconnect_ical")
