"""Block websites in Chromium browsers via Chrome DevTools Protocol (CDP).

The browser must be launched with --remote-debugging-port=9222 for this to
work. run.ps1 handles launching Chrome/Edge/Brave with that flag.

tab_id is a str (CDP targetId) on Windows, versus int on macOS. The public
interface is otherwise identical to the macOS version — app.py only does
`if tab_id:` checks, so duck typing keeps it compatible.
"""

import json
import re
import threading
import time
from typing import Set, Dict, Callable, Optional, List, Tuple

import requests

try:
    import websocket as _websocket
except ImportError:
    _websocket = None

try:
    from .analytics import log_event as _log_event
except Exception:
    def _log_event(*a, **kw): pass


# Ports to probe for CDP endpoints (multiple browsers can each get a port)
DEBUG_PORTS = [9222, 9223, 9224, 9225]

INTERNAL_SCHEMES = {"chrome", "about", "data", "chrome-extension", "devtools"}

ALWAYS_ALLOWED_DOMAINS = {"notion.so", "notionusercontent.com", "music.youtube.com"}

TITLE_IGNORE = {"youtube", "youtube music", "google", "new tab", "claude", ""}


# ── CDP helpers ───────────────────────────────────────────────────────────────

def _cdp_send(ws_url: str, method: str, params: dict = None) -> Optional[dict]:
    """Open a WebSocket to the given CDP endpoint, send one command, and return the result."""
    if _websocket is None:
        return None
    params = params or {}
    try:
        ws = _websocket.create_connection(ws_url, timeout=3)
        try:
            msg = json.dumps({"id": 1, "method": method, "params": params})
            ws.send(msg)
            raw = ws.recv()
            return json.loads(raw)
        finally:
            ws.close()
    except Exception:
        return None


def _cdp_navigate(ws_url: str, url: str):
    """Navigate the tab described by ws_url to url."""
    _cdp_send(ws_url, "Page.navigate", {"url": url})


def _cdp_close(port: int, target_id: str):
    """Close the CDP target (tab) with the given targetId on port."""
    try:
        requests.get(f"http://localhost:{port}/json/close/{target_id}", timeout=2)
    except Exception:
        pass


# ── Main class ────────────────────────────────────────────────────────────────

class URLMonitor:
    def __init__(
        self,
        on_blocked_url: Callable[[str, str, Optional[str], str], None],
        on_off_topic: Optional[Callable[[str, str, Optional[str]], None]] = None,
        poll_seconds: float = 2,
        extra_always_allowed: Optional[List[str]] = None,
    ):
        self.session_allowed_domains: Set[str] = set()
        self.temporarily_allowed: Dict[str, float] = {}
        self.user_always_allowed: Set[str] = set(extra_always_allowed or [])
        self.on_blocked_url = on_blocked_url
        self.on_off_topic = on_off_topic
        self.poll_seconds = max(0.5, float(poll_seconds))
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._title_thread: Optional[threading.Thread] = None
        self._handling: Set[str] = set()
        self._handling_origin: Dict[str, str] = {}      # domain -> tab_id (str)
        self._last_url: str = ""
        self._last_url_by_tab: Dict[str, str] = {}      # tab_id -> url
        self._last_checked_title: str = ""
        self._last_title_by_tab: Dict[str, str] = {}    # tab_id -> title
        self._title_cooldown_until: Dict[str, float] = {}
        # Registry so we know how to talk to each tab
        self._tab_registry: Dict[str, dict] = {}        # target_id -> {ws_url, port}
        self.session_name: str = ""

    # ── Public session controls ───────────────────────────────────────────────

    def set_session_allowed_domains(self, domains: List[str]):
        self.session_allowed_domains = set(domains)

    def allow_domain_temporarily(self, domain: str, minutes: int = 15):
        self.temporarily_allowed[domain] = time.time() + minutes * 60
        self._handling.discard(domain)
        self._handling_origin.pop(domain, None)

    def set_title_cooldown(self, domain: str, seconds: int = 120):
        self._title_cooldown_until[domain] = time.time() + seconds

    def deny_domain(self, domain: str, close_tab: bool = True):
        if close_tab:
            self.redirect_chrome()
        self._handling.discard(domain)

    def revoke_domain(self, domain: str, tab_id: Optional[str] = None):
        self.temporarily_allowed.pop(domain, None)
        self._last_url = ""
        if tab_id:
            self.close_tab_by_id(tab_id)
        else:
            self.redirect_chrome()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._title_thread = threading.Thread(target=self._title_loop, daemon=True)
        self._title_thread.start()

    def stop(self):
        self._running = False
        self.session_allowed_domains.clear()
        self.temporarily_allowed.clear()
        self._handling.clear()
        self._handling_origin.clear()
        self._last_checked_title = ""
        self._title_cooldown_until.clear()

    # ── Domain allow logic ────────────────────────────────────────────────────

    def _is_allowed(self, domain: str) -> bool:
        candidate = domain[4:] if domain.startswith("www.") else domain
        for allowed in ALWAYS_ALLOWED_DOMAINS | self.user_always_allowed:
            if candidate == allowed or candidate.endswith("." + allowed):
                return True
        for allowed in self.session_allowed_domains:
            if candidate == allowed or candidate.endswith("." + allowed):
                return True
        if domain in self.temporarily_allowed:
            if self.temporarily_allowed[domain] > time.time():
                return True
            del self.temporarily_allowed[domain]
        return False

    def _is_temp_allowed(self, domain: str) -> bool:
        if domain in self.temporarily_allowed:
            return self.temporarily_allowed[domain] > time.time()
        return False

    def _extract_domain(self, url: str) -> Optional[str]:
        match = re.match(r'(\w+)://', url)
        if match and match.group(1) in INTERNAL_SCHEMES:
            return None
        match = re.search(r'https?://(?:www\.)?([^/?\s#]+)', url)
        return match.group(1).lower() if match else None

    # ── CDP tab enumeration ───────────────────────────────────────────────────

    def _get_all_tabs(self) -> List[Tuple[str, str, str, str, int]]:
        """Return (target_id, url, title, ws_url, port) for all page tabs across all debug ports."""
        results: List[Tuple[str, str, str, str, int]] = []
        for port in DEBUG_PORTS:
            try:
                resp = requests.get(f"http://localhost:{port}/json", timeout=1)
                if not resp.ok:
                    continue
                tabs = resp.json()
                for tab in tabs:
                    if tab.get("type") != "page":
                        continue
                    target_id = tab.get("id", "")
                    url = tab.get("url", "")
                    title = tab.get("title", "")
                    ws_url = tab.get("webSocketDebuggerUrl", "")
                    if target_id:
                        # Keep registry up to date
                        self._tab_registry[target_id] = {"ws_url": ws_url, "port": port}
                        results.append((target_id, url, title, ws_url, port))
            except Exception:
                pass
        return results

    def _get_active_tabs(self) -> List[Tuple[str, str, str]]:
        """Return (target_id, url, title) for all page tabs (used by monitoring loop)."""
        return [(tid, url, title) for tid, url, title, _, _ in self._get_all_tabs()]

    # ── Tab operations ────────────────────────────────────────────────────────

    def get_active_tab_id(self) -> Optional[str]:
        """Return the targetId of the first tab found across all debug ports."""
        tabs = self._get_all_tabs()
        if tabs:
            return tabs[0][0]
        return None

    def check_tab_status(self, tab_id: str) -> str:
        """
        Re-query all ports; return "active" if targetId still exists, "gone" if not.
        (No "background" concept on Windows — CDP doesn't expose focus state easily.)
        """
        for tid, _, _, _, _ in self._get_all_tabs():
            if tid == tab_id:
                return "active"
        return "gone"

    def close_tab_by_id(self, tab_id: str):
        """Close (or blank) the tab identified by tab_id."""
        info = self._tab_registry.get(tab_id)
        if not info:
            return
        port = info["port"]
        ws_url = info["ws_url"]
        # Count how many page tabs are on this port
        tabs_on_port = [t for t in self._get_all_tabs() if t[4] == port]
        if len(tabs_on_port) <= 1:
            # Only one tab — navigate to blank rather than closing the window
            _cdp_navigate(ws_url, "about:blank")
        else:
            _cdp_close(port, tab_id)

    def redirect_tab_by_id(self, tab_id: str):
        """Navigate the given tab to about:blank."""
        info = self._tab_registry.get(tab_id)
        if info and info.get("ws_url"):
            _cdp_navigate(info["ws_url"], "about:blank")

    def redirect_chrome(self):
        """Redirect the first tab found across all ports to about:blank."""
        tabs = self._get_all_tabs()
        if tabs:
            _, _, _, ws_url, _ = tabs[0]
            if ws_url:
                _cdp_navigate(ws_url, "about:blank")

    def navigate_tab_by_id(self, tab_id: str, url: str):
        """Navigate the given tab to url."""
        info = self._tab_registry.get(tab_id)
        if info and info.get("ws_url"):
            _cdp_navigate(info["ws_url"], url)

    def navigate_chrome_to(self, url: str):
        """Navigate the first tab found to url."""
        tabs = self._get_all_tabs()
        if tabs:
            _, _, _, ws_url, _ = tabs[0]
            if ws_url:
                _cdp_navigate(ws_url, url)

    def open_url_in_new_tab(self, url: str):
        """Open url in a new tab using CDP Target.createTarget."""
        tabs = self._get_all_tabs()
        if not tabs:
            return
        # Use the first available port's CDP endpoint
        port = tabs[0][4]
        try:
            resp = requests.get(
                f"http://localhost:{port}/json/new?{url}",
                timeout=3,
            )
            if resp.ok:
                return
        except Exception:
            pass
        # Fallback: createTarget via WebSocket
        _, _, _, ws_url, _ = tabs[0]
        if ws_url:
            _cdp_send(ws_url, "Target.createTarget", {"url": url})

    def pin_tab_to_blank(self, tab_id: str):
        """Spawn a watcher thread that keeps the tab on about:blank.

        Returns a callable; call it to stop the watcher.
        """
        stop = threading.Event()

        def watcher():
            while not stop.wait(0.4):
                try:
                    tabs = self._get_all_tabs()
                    for tid, url, _, ws_url, _ in tabs:
                        if tid == tab_id:
                            if url and url != "about:blank":
                                if ws_url:
                                    _cdp_navigate(ws_url, "about:blank")
                            break
                except Exception:
                    pass

        t = threading.Thread(target=watcher, daemon=True)
        t.start()
        return stop.set

    # ── URL monitoring loop ───────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                tabs = self._get_active_tabs()
                live_ids = {tid for tid, _, _ in tabs}

                # Clean up stale tab entries
                for stale in list(self._last_url_by_tab.keys()):
                    if stale not in live_ids:
                        self._last_url_by_tab.pop(stale, None)
                        self._tab_registry.pop(stale, None)

                for tab_id, url, title in tabs:
                    if not url or self._last_url_by_tab.get(tab_id) == url:
                        continue

                    domain = self._extract_domain(url)
                    if not domain:
                        self._last_url_by_tab[tab_id] = url
                        continue

                    if not self._is_allowed(domain):
                        self._last_url_by_tab.pop(tab_id, None)

                        if domain in self._handling:
                            if self._handling_origin.get(domain) != tab_id:
                                self.redirect_tab_by_id(tab_id)
                            continue

                        self._handling.add(domain)
                        self._handling_origin[domain] = tab_id

                        try:
                            _log_event("url_blocked", domain=domain, url=url,
                                       session_name=self.session_name)
                        except Exception:
                            pass

                        threading.Thread(
                            target=self._handle_violation,
                            args=(domain, url, tab_id, title or ""),
                            daemon=True,
                        ).start()
                    else:
                        self._last_url_by_tab[tab_id] = url
                        try:
                            _log_event("tab_visit", domain=domain,
                                       session_name=self.session_name)
                        except Exception:
                            pass

            except Exception:
                pass

            time.sleep(self.poll_seconds)

    def _handle_violation(self, domain: str, original_url: str, tab_id: Optional[str], tab_title: str):
        try:
            self.on_blocked_url(domain, original_url, tab_id, tab_title)
        finally:
            self._handling.discard(domain)
            self._handling_origin.pop(domain, None)

    # ── Title monitoring loop ─────────────────────────────────────────────────

    def _title_loop(self):
        time.sleep(2)
        while self._running:
            try:
                tabs = self._get_active_tabs()
                live_ids = {tid for tid, _, _ in tabs}

                for stale in list(self._last_title_by_tab.keys()):
                    if stale not in live_ids:
                        self._last_title_by_tab.pop(stale, None)

                now = time.time()
                for d in list(self._title_cooldown_until.keys()):
                    if self._title_cooldown_until[d] <= now:
                        self._title_cooldown_until.pop(d, None)

                for tab_id, url, title in tabs:
                    if not url:
                        continue
                    domain = self._extract_domain(url)
                    if not domain or not self._is_temp_allowed(domain):
                        continue
                    if not title or title.lower().strip() in TITLE_IGNORE:
                        continue
                    if self._title_cooldown_until.get(domain, 0) > now:
                        continue
                    if self._last_title_by_tab.get(tab_id) == title:
                        continue
                    self._last_title_by_tab[tab_id] = title

                    if domain in self._handling:
                        continue

                    if self.on_off_topic:
                        self._handling.add(domain)
                        threading.Thread(
                            target=self._handle_title_check,
                            args=(domain, title, tab_id),
                            daemon=True,
                        ).start()

            except Exception:
                pass

            time.sleep(8)

    def _handle_title_check(self, domain: str, title: str, tab_id: Optional[str]):
        try:
            if self.on_off_topic:
                self.on_off_topic(domain, title, tab_id)
        finally:
            self._handling.discard(domain)
