"""Kurucu (portföy şirketi) bazlı varlık dağılımı adaptörleri.

Her kurucunun sitesi farklı olduğundan her biri için ayrı bir adaptör var.
Bir adaptör, bir fon kodu/ünvanı için kurucu sitesindeki sayfayı bulup
varlık dağılımını (AllocSnapshot) döndürür. Çıkaramazsa None döner; üst katman
(service.py) o zaman kurucu sitesine/KAP'a yedek link gösterir.

Şu an: İş Portföy (tam), Ak Portföy (ilk-10 dağılımı). Tera/Pusula best-effort.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata

import httpx

from .base import (
    AllocSnapshot,
    find_date,
    make_client,
    pick_asset_allocation,
)


def slugify_tr(s: str, *, drop_paren: bool = True) -> str:
    if drop_paren:
        s = re.sub(r"\(.*?\)", "", s)       # parantez içini tamamen at (İş tarzı)
    else:
        s = s.replace("(", " ").replace(")", " ")  # paren içeriğini koru (Pusula tarzı)
    # Türkçe büyük harfleri lower'DAN ÖNCE sadeleştir: "İ".lower() == "i̇"
    # (birleşik nokta) olduğundan slug'da yanlış "-" oluşmasını önler.
    pre = {"İ": "i", "I": "i", "Ş": "s", "Ğ": "g", "Ç": "c", "Ö": "o", "Ü": "u", "Â": "a"}
    for a, b in pre.items():
        s = s.replace(a, b)
    s = s.lower()
    for a, b in {"ı": "i", "ş": "s", "ğ": "g", "ç": "c", "ö": "o", "ü": "u", "â": "a"}.items():
        s = s.replace(a, b)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def kurucu_key(title: str) -> str:
    """Fon ünvanından kurucu adını çıkarır (ör. 'İŞ PORTFÖY ...' → 'İş Portföy')."""
    t = (title or "").strip()
    m = re.match(r"([A-Za-zÇĞİıÖŞÜçğöşü0-9]+)\s+PORTFÖY", t, re.I)
    if m:
        return f"{m.group(1).title()} Portföy"
    return ""


class Adapter:
    name: str = ""          # görünen ad / kurucu adı
    site: str = ""          # ana site
    aliases: tuple = ()     # ünvanda aranan kurucu öneki (büyük harf)

    def matches(self, title: str) -> bool:
        up = (title or "").upper()
        return any(a in up for a in self.aliases)

    def fetch(self, code: str, title: str, client: httpx.Client) -> AllocSnapshot | None:
        raise NotImplementedError


# --------------------------------------------------------------------------- İş
class IsPortfoy(Adapter):
    name = "İş Portföy"
    site = "https://www.isportfoy.com.tr"
    aliases = ("İŞ PORTFÖY", "IS PORTFOY", "İŞ PORTFÖY")

    _map: dict[str, str] = {}
    _map_at: float = 0.0

    def _code_url_map(self, client: httpx.Client) -> dict[str, str]:
        if self._map and time.time() - self._map_at < 6 * 3600:
            return self._map
        try:
            html = client.get(f"{self.site}/yatirim-fonlari").text
            m = {}
            for am in re.finditer(r'data-autocomplete="(\[.*?\])"', html, re.S):
                raw = am.group(1).replace("&quot;", '"').replace("&#34;", '"')
                try:
                    arr = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                for it in arr:
                    t = it.get("title") or ""
                    u = it.get("url") or ""
                    cm = re.match(r"\s*([A-Z0-9]{2,4})\s*-", t)
                    if cm and u:
                        m[cm.group(1)] = u if u.startswith("http") else self.site + u
            if m:
                IsPortfoy._map = m
                IsPortfoy._map_at = time.time()
        except Exception:  # noqa: BLE001
            pass
        return self._map

    def fetch(self, code, title, client):
        url = self._code_url_map(client).get(code.upper())
        if not url:
            slug = slugify_tr(title)
            url = f"{self.site}/{slug}"
        try:
            html = client.get(url).text
        except Exception:  # noqa: BLE001
            return None
        items = pick_asset_allocation(html)
        if not items:
            return None
        report = None
        rm = re.search(r'href="([^"]+)"[^>]*>\s*Detaylı Aylık Varlık Raporu', html)
        if rm:
            r = rm.group(1)
            report = r if r.startswith("http") else self.site + r
        return AllocSnapshot(
            items=items, source=self.name, source_url=url,
            as_of=find_date(html, "Varlık Dağılım"), report_url=report,
        )


# --------------------------------------------------------------------------- Ak
class AkPortfoy(Adapter):
    name = "Ak Portföy"
    site = "https://www.akportfoy.com.tr"
    aliases = ("AK PORTFÖY", "AK PORTFOY")

    def fetch(self, code, title, client):
        url = f"{self.site}/tr/fon/{code.upper()}"
        try:
            html = client.get(url).text
        except Exception:  # noqa: BLE001
            return None
        items = pick_asset_allocation(html)
        if not items:
            return None
        return AllocSnapshot(
            items=items, source=self.name, source_url=url,
            as_of=find_date(html, "Portföy Dağılım"),
        )


# ----------------------------------------------------------------- Tera/Pusula
class TeraPortfoy(Adapter):
    name = "Tera Portföy"
    site = "https://www.teraportfoy.com"
    aliases = ("TERA PORTFÖY", "TERA PORTFOY")

    # Not: Tera sunucusu bazı IP'lerden (ör. veri merkezi) TLS bağlantısını
    # resetliyor; kullanıcının TR yerel IP'sinden genelde erişilebilir.
    def fetch(self, code, title, client):
        try:
            fl = client.get(self.site + "/fonlarimiz").text
        except Exception:  # noqa: BLE001
            return None
        links = []
        seen = set()
        for l in re.findall(r'href="([^"]*(?:yatirim-fonlari|/fon)[^"]+)"', fl):
            full = l if l.startswith("http") else self.site + l
            if full not in seen:
                seen.add(full)
                links.append(full)
        # Başlık kelimeleriyle URL slug'ı en çok örtüşen ilk birkaç adayı dene
        # (tüm fonları çekip siteyi yormamak ve API'yi kilitlememek için).
        words = {w for w in slugify_tr(title).split("-") if len(w) > 3}
        links.sort(key=lambda u: -sum(1 for w in words if w in u.lower()))
        up = code.upper()
        for full in links[:4]:
            try:
                h = client.get(full).text
            except Exception:  # noqa: BLE001
                continue
            items = pick_asset_allocation(h)
            if items and (up in h.upper() or len(items) >= 2):
                return AllocSnapshot(items=items, source=self.name,
                                     source_url=full, as_of=find_date(h, "Dağılım"))
        return None


class PusulaPortfoy(Adapter):
    name = "Pusula Portföy"
    site = "https://www.pusulaportfoy.com.tr"
    aliases = ("PUSULA PORTFÖY", "PUSULA PORTFOY")

    def fetch(self, code, title, client):
        # Pusula slug'ı parantez içeriğini de tutar (…fonu-hisse-senedi-yogun-fon).
        for slug in (slugify_tr(title, drop_paren=False), slugify_tr(title)):
            u = f"{self.site}/fonlar/{slug}"
            try:
                h = client.get(u).text
            except Exception:  # noqa: BLE001
                continue
            items = pick_asset_allocation(h)
            if items:
                return AllocSnapshot(items=items, source=self.name, source_url=u,
                                     as_of=find_date(h, "Portföy Dağılım"))
        return None


ADAPTERS: list[Adapter] = [IsPortfoy(), AkPortfoy(), TeraPortfoy(), PusulaPortfoy()]


def resolve(title: str) -> Adapter | None:
    for a in ADAPTERS:
        if a.matches(title):
            return a
    return None
