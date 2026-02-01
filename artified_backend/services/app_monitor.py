from dataclasses import dataclass
from typing import List, Optional, Tuple
import pygetwindow as gw


@dataclass
class BlacklistHit:
    keyword: str
    window_title: str


def _is_keyword_in_visible_window(keyword: str) -> Optional[str]:
    all_titles = gw.getAllTitles()
    for title in all_titles:
        if title and keyword.lower() in title.lower():
            wins = gw.getWindowsWithTitle(title)
            if wins:
                w = wins[0]
                if getattr(w, "visible", False):
                    return title
    return None


def check_blacklist(keywords: List[str]) -> Tuple[bool, Optional[BlacklistHit]]:
    for kw in keywords:
        title = _is_keyword_in_visible_window(kw)
        if title:
            return True, BlacklistHit(keyword=kw, window_title=title)
    return False, None
