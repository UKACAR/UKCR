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
from datetime import date

import httpx

from .base import (
    AllocItem,
    AllocSnapshot,
    find_date,
    make_client,
    pct,
    pick_asset_allocation,
    plausible,
)


def slugify_tr(s: str, *, drop_paren: bool = True) -> str:
    if drop_paren:
        prev = None  # iç içe parantezleri içten dışa tekrarlı temizle
        while prev != s:
            prev = s
            s = re.sub(r"\([^()]*\)", "", s)
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
                    cm = re.match(r"\s*([A-Za-z0-9]{2,6})\s*-", t)
                    if cm and u:
                        url = u if u.startswith("http") else self.site + u
                        m.setdefault(cm.group(1).upper(), url)  # ilk eşleşme kalır
            if m:
                IsPortfoy._map = m
                IsPortfoy._map_at = time.time()
        except Exception:  # noqa: BLE001
            pass
        return self._map

    def fetch(self, code, title, client):
        url = self._code_url_map(client).get(code.upper())
        if not url:
            url = f"{self.site}/{slugify_tr(title)}"
        try:
            html = client.get(url).text
        except Exception:  # noqa: BLE001
            return None
        # Yanlış sayfaya düşmediğimizi doğrula (İş fon sayfaları kodu gösterir).
        if code.upper() not in html.upper():
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
        # Varlık dağılımı görünür HTML'de değil; amCharts donut'unu besleyen
        # inline `var fundAssetAlloc = [{category, value}, ...]` JSON'unda.
        # Dizi sonunu güvenle bulmak için regex yerine bracket-dengeli raw_decode.
        items: list[AllocItem] = []
        mark = re.search(r"var\s+fundAssetAlloc\s*=\s*", html)
        if mark:
            start = html.find("[", mark.end())
            if start != -1:
                try:
                    arr, _ = json.JSONDecoder().raw_decode(html, start)
                except ValueError:
                    arr = []
                for x in arr if isinstance(arr, list) else []:
                    name = str(x.get("category", "")).strip()
                    p = pct(x.get("value"))
                    if name and p is not None:
                        items.append(AllocItem(name, p))
        # Yapısal kaynak makul değilse (toplam ~%100 değil) genel çıkarıcıya düş.
        if not plausible(items):
            generic = pick_asset_allocation(html)
            if generic:
                items = generic
        if not items:
            return None
        report = None
        rm = re.search(r'id="asset-distribution".*?href="(/doc/\d+)"', html, re.S)
        if rm:
            report = self.site + rm.group(1)
        return AllocSnapshot(items=items, source=self.name, source_url=url, report_url=report)


# ----------------------------------------------------------------- Tera/Pusula
# Tera dağılım grafiği etiketlerini İngilizce yayınlıyor → Türkçeye çevir.
_TERA_TR = {
    "stocks instruments": "Hisse Senedi",
    "reverse repo instruments": "Ters Repo",
    "real estate investment funds participation shares": "Gayrimenkul Yatırım Fonları",
    "mutual funds participation shares": "Yatırım Fonları Katılma Payları",
    "futures cash collaterals": "Vadeli İşlem Nakit Teminatları",
    "private lease certificate": "Özel Sektör Kira Sertifikası",
    "public lease certificate": "Kamu Kira Sertifikası",
    "funding bonds": "Finansman Bonosu",
    "government bonds": "Devlet Tahvili",
    "government bond": "Devlet Tahvili",
    "treasury bills": "Hazine Bonosu",
    "bank bills": "Banka Bonosu",
    "term deposit": "Vadeli Mevduat",
    "participation account": "Katılma Hesabı",
    "deposit": "Mevduat",
    "eurobond": "Eurobond",
    "precious metals": "Kıymetli Madenler",
    "foreign": "Yabancı Menkul Kıymet",
}


def _tera_label(en: str) -> str:
    s = re.sub(r"\s*\(?\s*%\s*\)?\s*$", "", str(en)).strip()  # sondaki (%)/%
    s = re.sub(r"^Fund\s+", "", s, flags=re.I).strip()
    key = s.lower()
    if key in _TERA_TR:
        return _TERA_TR[key]
    for k, v in _TERA_TR.items():
        if k in key:
            return v
    return s  # çevrilemezse temizlenmiş İngilizce


class TeraPortfoy(Adapter):
    name = "Tera Portföy"
    site = "https://www.teraportfoy.com"
    aliases = ("TERA PORTFÖY", "TERA PORTFOY")

    # Dağılım, fon sayfasındaki data-portfolio-chart-labels/-values script'lerinde
    # (Highcharts donut). URL slug'ı genelde -{kod} ile biter (güvenilir eşleşme).
    # Not: Tera sunucusu ara sıra TLS bağlantısını resetliyor → o zaman yedek.
    def _parse(self, html: str, url: str) -> AllocSnapshot | None:
        lm = re.search(r"data-portfolio-chart-labels[^>]*>\s*(.*?)\s*</script>", html, re.S)
        vm = re.search(r"data-portfolio-chart-values[^>]*>\s*(.*?)\s*</script>", html, re.S)
        if not (lm and vm):
            return None
        try:
            labels = json.loads(lm.group(1))
            values = json.loads(vm.group(1))
        except Exception:  # noqa: BLE001
            return None
        items: list[AllocItem] = []
        for en, v in zip(labels, values):
            p = pct(v)
            name = _tera_label(en)
            if name and p is not None:
                items.append(AllocItem(name, p))
        if not plausible(items):
            return None
        as_of = None
        dm = re.search(r'data-portfolio-chart-update-date="([^"]*)"', html)
        if dm and dm.group(1).strip():
            as_of = find_date(dm.group(1))
        return AllocSnapshot(items=items, source=self.name, source_url=url, as_of=as_of)

    def fetch(self, code, title, client):
        try:
            fl = client.get(self.site + "/fonlarimiz").text
        except Exception:  # noqa: BLE001
            return None
        links = sorted(set(re.findall(r'href="(/fonlarimiz/[^"]+)"', fl)))
        low = code.lower()
        # Önce slug sonu "-{kod}" (kesin), yoksa başlık kelime örtüşmesi.
        cand = [l for l in links if l.lower().rstrip("/").endswith("-" + low)]
        if not cand:
            words = {w for w in slugify_tr(title).split("-") if len(w) > 3}
            cand = sorted(links, key=lambda u: -sum(1 for w in words if w in u.lower()))[:4]
        for l in cand[:4]:
            full = self.site + l
            try:
                h = client.get(full).text
            except Exception:  # noqa: BLE001
                continue
            snap = self._parse(h, full)
            if snap:
                return snap
        return None


class PusulaPortfoy(Adapter):
    name = "Pusula Portföy"
    site = "https://www.pusulaportfoy.com.tr"
    aliases = ("PUSULA PORTFÖY", "PUSULA PORTFOY")

    def fetch(self, code, title, client):
        # Pusula slug'ı parantez içeriğini de tutar (…fonu-hisse-senedi-yogun-fon).
        # Kurucu öneki bazen URL'de yok → öneksiz varyantları da dene.
        full = slugify_tr(title, drop_paren=False)
        dropp = slugify_tr(title)
        cand, seen = [], set()
        for sl in (full, dropp, re.sub(r"^pusula-portfoy-", "", full),
                   re.sub(r"^pusula-portfoy-", "", dropp)):
            if sl and sl not in seen:
                seen.add(sl)
                cand.append(sl)
        for slug in cand:
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


class GarantiPortfoy(Adapter):
    name = "Garanti Portföy"
    site = "https://www.garantibbvaportfoy.com.tr"
    aliases = ("GARANTİ PORTFÖY", "GARANTI PORTFOY", "GARANTİ BBVA", "GARANTI BBVA")

    def _last_date(self, client) -> date | None:
        try:
            r = client.post(
                f"{self.site}/webservice/lastdate",
                content="{}",
                headers={"Content-Type": "application/json"},
            )
            ds = json.loads(r.content.decode("utf-8"))
            if isinstance(ds, str) and re.match(r"\d{4}-\d{2}-\d{2}", ds):
                y, mo, d = ds[:10].split("-")
                return date(int(y), int(mo), int(d))
        except Exception:  # noqa: BLE001
            pass
        return None

    def fetch(self, code, title, client):
        # Dağılım HTML'de değil; site içi JSON web servisinde (POST, token yok).
        try:
            r = client.post(
                f"{self.site}/webservice/portfoliodistributions",
                params={"code": code.upper(), "lang": "tr"},
            )
        except Exception:  # noqa: BLE001
            return None
        if r.status_code != 200:  # 404 = Garanti fonu değil
            return None
        try:
            outer = json.loads(r.content.decode("utf-8"))
            if isinstance(outer, str):  # gövde çift-JSON kodlu
                outer = json.loads(outer)
            data = (outer.get("data") or {}).get("Data") or []
        except Exception:  # noqa: BLE001
            return None
        items: list[AllocItem] = []
        for x in data:
            name = str(x.get("Name", "")).replace("(%)", "").strip()
            p = pct(x.get("Percentage"))
            if name and p is not None:
                items.append(AllocItem(name, p))
        if not plausible(items):  # eksik/bozuk satır → yanlış göstermektense yedek
            return None
        return AllocSnapshot(
            items=items, source=self.name, source_url=f"{self.site}/",
            as_of=self._last_date(client),
        )


ADAPTERS: list[Adapter] = [
    IsPortfoy(), AkPortfoy(), GarantiPortfoy(), TeraPortfoy(), PusulaPortfoy(),
]


def resolve(title: str) -> Adapter | None:
    for a in ADAPTERS:
        if a.matches(title):
            return a
    return None
