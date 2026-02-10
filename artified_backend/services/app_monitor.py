from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple
import sys
import subprocess

import pygetwindow as gw


@dataclass
class BlacklistHit:
    kind: str                 # "title" | "app" | "url"
    keyword: str
    window_title: str
    app_name: Optional[str] = None
    url: Optional[str] = None


def _get_active_window_title() -> str:
    """Return current active window title (best-effort). Compatible with property/method title."""
    try:
        w = gw.getActiveWindow()
        if not w:
            return ""

        t = getattr(w, "title", "")
        # Some pygetwindow backends expose title as a method
        if callable(t):
            t = t()

        if isinstance(t, str) and t:
            return t
    except Exception:
        pass
    return ""



def _get_frontmost_app_macos() -> Optional[str]:
    """macOS only: return frontmost app name, e.g. 'Google Chrome'."""
    if sys.platform != "darwin":
        return None

    script = r'''
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    return frontApp
    '''
    try:
        out = subprocess.check_output(["osascript", "-e", script], text=True).strip()
        return out or None
    except Exception:
        return None


def _get_frontmost_browser_url_macos() -> Optional[str]:
    """
    macOS only:
    If frontmost app is Chrome or Safari, return active tab URL, else None.
    """
    if sys.platform != "darwin":
        return None

    # Chrome
    chrome_script = r'''
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    if frontApp is "Google Chrome" then
        tell application "Google Chrome"
            if (count of windows) = 0 then return ""
            return URL of active tab of front window
        end tell
    end if
    return ""
    '''
    try:
        out = subprocess.check_output(["osascript", "-e", chrome_script], text=True).strip()
        if out:
            return out
    except Exception:
        pass

    # Safari
    safari_script = r'''
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    if frontApp is "Safari" then
        tell application "Safari"
            if (count of windows) = 0 then return ""
            return URL of current tab of front window
        end tell
    end if
    return ""
    '''
    try:
        out = subprocess.check_output(["osascript", "-e", safari_script], text=True).strip()
        if out:
            return out
    except Exception:
        pass

    return None


def check_blacklist(
    keywords_or_title_keywords: List[str],
    app_names: Optional[List[str]] = None,
    url_keywords: Optional[List[str]] = None,
) -> Tuple[bool, Optional[BlacklistHit]]:
    """
    Backward compatible:
      - old usage: check_blacklist(keywords)
      - new usage: check_blacklist(title_keywords, app_names=[...], url_keywords=[...])

    Pauses when CURRENT active window/app/url matches blacklist.
    """
    title_keywords = keywords_or_title_keywords or []
    app_names = app_names or []
    url_keywords = url_keywords or []

    title = _get_active_window_title()
    title_l = title.lower()

    # 1) Title keyword match (active window only)
    for kw in title_keywords:
        if kw and kw.lower() in title_l:
            return True, BlacklistHit(kind="title", keyword=kw, window_title=title)

    # 2) App name match (macOS reliable; others skip)
    if app_names:
        app = _get_frontmost_app_macos()
        if app:
            app_l = app.lower()
            for a in app_names:
                if a and a.lower() in app_l:
                    return True, BlacklistHit(
                        kind="app",
                        keyword=a,
                        window_title=title,
                        app_name=app,
                    )

    # 3) URL match (macOS Chrome/Safari)
    if url_keywords:
        url = _get_frontmost_browser_url_macos()
        if url:
            url_l = url.lower()
            for u in url_keywords:
                if u and u.lower() in url_l:
                    return True, BlacklistHit(
                        kind="url",
                        keyword=u,
                        window_title=title,
                        app_name=_get_frontmost_app_macos(),
                        url=url,
                    )

    return False, None
