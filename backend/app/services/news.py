"""Finans/ekonomi haberleri — Google News RSS (Türkçe). Ücretsiz, anahtarsız."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

_SUFFIX = "&hl=tr&gl=TR&ceid=TR:tr"
RSS_URL = (
    "https://news.google.com/rss/search"
    "?q=borsa+OR+ekonomi+OR+%22yat%C4%B1r%C4%B1m+fonu%22+OR+d%C3%B6viz+OR+enflasyon+OR+TEFAS"
    + _SUFFIX
)
# Kıymetli madenler (altın/gümüş/platin/paladyum) piyasa haberleri
METALS_RSS = (
    "https://news.google.com/rss/search"
    "?q=alt%C4%B1n+OR+g%C3%BCm%C3%BC%C5%9F+OR+platin+OR+paladyum+OR+%22k%C4%B1ymetli+maden%22"
    + _SUFFIX
)
_TTL = 900  # 15 dk cache
_cache: dict = {"at": 0.0, "items": []}
_metals_cache: dict = {"at": 0.0, "items": []}


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


def _fetch(url: str = RSS_URL) -> list[dict]:
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
        source = (src_el.text.strip() if src_el is not None and src_el.text else "")
        # Google News başlıkları çoğu zaman "Başlık - Kaynak" biçiminde; eki temizle
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


def latest(limit: int = 12) -> list[dict]:
    now = time.time()
    if _cache["items"] and now - _cache["at"] < _TTL:
        return _cache["items"][:limit]
    items = _fetch()
    if items:
        _cache["items"] = items
        _cache["at"] = now
    return (_cache["items"] or [])[:limit]


def metals_news(limit: int = 12) -> list[dict]:
    """Kıymetli maden (altın/gümüş/platin/paladyum) piyasa haberleri."""
    now = time.time()
    if _metals_cache["items"] and now - _metals_cache["at"] < _TTL:
        return _metals_cache["items"][:limit]
    items = _fetch(METALS_RSS)
    if items:
        _metals_cache["items"] = items
        _metals_cache["at"] = now
    return (_metals_cache["items"] or [])[:limit]
