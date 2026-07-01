"""Finans/ekonomi haberleri — Google News RSS (Türkçe). Ücretsiz, anahtarsız.

Konu bazlı: general / metals / crypto / bist / etf / viop / world.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

_BASE = "https://news.google.com/rss/search?q="
_SUFFIX = "&hl=tr&gl=TR&ceid=TR:tr"
_TTL = 900  # 15 dk cache

# Konu -> Google News arama sorgusu
TOPICS: dict[str, str] = {
    "general": 'borsa OR ekonomi OR "yatırım fonu" OR döviz OR enflasyon OR TEFAS',
    "metals": 'altın OR gümüş OR platin OR paladyum OR "kıymetli maden"',
    "crypto": "kripto para OR bitcoin OR ethereum OR kripto borsa",
    "bist": "borsa istanbul OR BİST 100 OR hisse senedi",
    "etf": "borsa yatırım fonu OR ETF fonu",
    "viop": "VİOP OR vadeli işlem OR opsiyon piyasası",
    "world": "dünya borsaları OR küresel piyasalar OR Wall Street OR S&P 500",
}

_caches: dict[str, dict] = {}


def _relative(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = max(0.0, (now - dt).total_seconds())
    if secs < 3600:
        return f"{int(secs // 60)}dk"
    if secs < 86400:
        return f"{int(secs // 3600)}sa"
    return f"{int(secs // 86400)}g"


def _fetch(url: str) -> list[dict]:
    try:
        r = httpx.get(url, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception:  # noqa: BLE001
        return []

    out: list[dict] = []
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        src_el = item.find("source")
        source = src_el.text.strip() if src_el is not None and src_el.text else ""
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        when = ""
        pub = item.findtext("pubDate")
        if pub:
            try:
                when = _relative(parsedate_to_datetime(pub))
            except Exception:  # noqa: BLE001
                when = ""
        if title and link:
            out.append({"title": title, "link": link, "source": source, "when": when})
    return out


def news_for(topic: str = "general", limit: int = 12) -> list[dict]:
    query = TOPICS.get(topic, TOPICS["general"])
    cache = _caches.setdefault(topic, {"at": 0.0, "items": []})
    now = time.time()
    if cache["items"] and now - cache["at"] < _TTL:
        return cache["items"][:limit]
    items = _fetch(_BASE + quote(query) + _SUFFIX)
    if items:
        cache["items"] = items
        cache["at"] = now
    return (cache["items"] or [])[:limit]


def latest(limit: int = 12) -> list[dict]:
    return news_for("general", limit)


def metals_news(limit: int = 12) -> list[dict]:
    return news_for("metals", limit)
