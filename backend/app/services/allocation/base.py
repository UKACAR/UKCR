"""Kurucu (portföy şirketi) sitelerinden varlık dağılımı çıkarımı — ortak araçlar.

TEFAS ve KAP fon portföy dağılımını yapısal vermediği için (bkz. tefas.py notu),
dağılımı fonun KURUCUSUNUN kendi resmî sitesinden çekiyoruz. Her kurucu farklı
teknoloji kullanıyor (düz tablo / Chart.js / Next.js), bu yüzden burada birden
çok çıkarım stratejisi var; adaptörler (adapters.py) bunları kullanır.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from html import unescape

import httpx

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

# Bilinen varlık sınıfı anahtar kelimeleri (dağılım grafiğini diğerlerinden ayırt etmek için)
ASSET_HINTS = (
    "hisse", "repo", "tahvil", "bono", "borçlanma", "mevduat", "katılma",
    "para piyasası", "kıymet", "eurobond", "vadeli", "fon", "altın", "döviz",
    "kira sertifika", "menkul", "diğer", "varant", "girişim", "gayrimenkul",
    "sermaye", "teminat", "endeks", "hesap",
)


@dataclass
class AllocItem:
    name: str
    percent: float

    def to_dict(self) -> dict:
        return {"name": self.name, "percent": self.percent}


@dataclass
class AllocSnapshot:
    items: list[AllocItem]
    source: str           # kurucu adı, ör. "İş Portföy"
    source_url: str       # fonun kurucu sitesindeki sayfası
    as_of: date | None = None       # kaynakta belirtilen tarih (varsa)
    report_url: str | None = None   # "Detaylı Aylık Varlık Raporu" vb. resmî belge


def make_client(timeout: float = 40.0) -> httpx.Client:
    # Bazı kurucu siteleri eski/eksik sertifika zinciri sunuyor → verify kapalı.
    return httpx.Client(timeout=timeout, headers=_UA, follow_redirects=True, verify=False)


def pct(raw) -> float | None:
    """'%65,64' / '65.64' / '4,21 %' → 65.64 (float)."""
    if raw is None:
        return None
    s = str(raw).replace("%", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")  # 1.234,56 → 1234.56
    else:
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except (TypeError, ValueError):
        return None


def is_label(name: str) -> bool:
    """Geçerli bir varlık-sınıfı adı mı? (yalnız-sayı/çoğunlukla-sayı hücreleri ele;
    ama 'BIST 30 Hisse', '10 Yıllık Tahvil' gibi rakamlı GERÇEK adları KORU)."""
    n = (name or "").strip()
    if not (1 < len(n) <= 60):
        return False
    if re.fullmatch(r"[\d.,%\s+-]+", n):  # tamamen sayı/işaret
        return False
    nonspace = sum(1 for c in n if not c.isspace())
    digits = sum(1 for c in n if c.isdigit())
    return not (nonspace and digits / nonspace > 0.5)


def plausible(items: list["AllocItem"]) -> bool:
    """Bir dağılımın makul olup olmadığı: ~%100'e toplanır ve 1-25 kalem."""
    if not items or len(items) > 25:
        return False
    total = sum(i.percent for i in items)
    return 85 <= total <= 110


def _looks_asset(labels: list[str]) -> int:
    """Etiket listesinin varlık-dağılımı gibi görünme skoru."""
    joined = " ".join(labels).lower()
    return sum(1 for h in ASSET_HINTS if h in joined)


def from_chartjs(html: str) -> list[list[AllocItem]]:
    """Chart.js canvas'larındaki data-options JSON'undan (labels+data) dağılımlar."""
    out: list[list[AllocItem]] = []
    for m in re.finditer(r'data-options="([^"]+)"', html):
        raw = unescape(m.group(1))
        try:
            obj = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        data = obj.get("data") or {}
        labels = data.get("labels") or []
        datasets = data.get("datasets") or []
        if not labels or not datasets:
            continue
        vals = (datasets[0] or {}).get("data") or []
        items = []
        for lab, v in zip(labels, vals):
            p = pct(v)
            if lab and p is not None:
                items.append(AllocItem(str(lab).strip(), p))
        if items:
            out.append(items)
    return out


def from_legend(html: str) -> list[AllocItem]:
    """`.title` + `.percent` ikili düzeni (İş Portföy tarzı legend)."""
    items: list[AllocItem] = []
    for m in re.finditer(
        r'class="title"[^>]*>(.*?)</span>\s*<span[^>]*class="percent"[^>]*>(.*?)</span>',
        html, re.S,
    ):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
        p = pct(re.sub(r"<[^>]+>", "", m.group(2)))
        if name and p is not None:
            items.append(AllocItem(name, p))
    return items


def from_table(html: str) -> list[AllocItem]:
    """Düz HTML tablosundaki (etiket | yüzde) ikilileri."""
    text = re.sub(r"(?is)<script.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    cells = re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", text)
    cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip() for x in cells]
    cells = [x for x in cells if x]
    items: list[AllocItem] = []
    seen: set[str] = set()
    for i, cell in enumerate(cells):
        m = re.fullmatch(r"%?\s*(-?\d{1,3}(?:[.,]\d{1,2})?)\s*%?", cell)
        if m and i > 0:
            lab = cells[i - 1]
            p = pct(m.group(1))
            if is_label(lab) and p is not None:
                key = lab.lower()
                if key not in seen:
                    seen.add(key)
                    items.append(AllocItem(lab, p))
    return items


def from_rsc(html: str) -> list[AllocItem]:
    """Next.js app-router RSC akışındaki ({label, percentage}) dağılımı (Pusula tarzı)."""
    pushes = re.findall(r'self\.__next_f\.push\(\[\d+,(".*?")\]\)', html, re.S)
    if not pushes:
        return []
    parts = []
    for p in pushes:
        try:
            parts.append(json.loads(p))
        except Exception:  # noqa: BLE001
            continue
    blob = "".join(parts)
    items: list[AllocItem] = []
    lc = r'(?:[^"\\]|\\.)*'  # kaçışlı karakterleri de kapsayan etiket

    def _add(name_raw: str, val: str) -> None:
        try:
            name = json.loads('"' + name_raw + '"')  # \" \\ \uXXXX çözülür
        except Exception:  # noqa: BLE001
            name = name_raw
        p = pct(val)
        if name and p is not None:
            items.append(AllocItem(str(name).strip(), p))

    # Anahtar sırası ve boşluklara toleranslı (Next.js serileştirmesi değişebilir).
    for m in re.finditer(
        r'"label"\s*:\s*"(' + lc + r')"\s*,\s*"percentage"\s*:\s*(-?\d+(?:\.\d+)?)', blob
    ):
        _add(m.group(1), m.group(2))
    if not items:
        for m in re.finditer(
            r'"percentage"\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*"label"\s*:\s*"(' + lc + r')"', blob
        ):
            _add(m.group(2), m.group(1))
    return items


def pick_asset_allocation(html: str) -> list[AllocItem]:
    """Sayfadaki adaylar arasından varlık-dağılımına en çok benzeyeni seçer.

    Önce Chart.js doughnut'ları, sonra legend, sonra tablo denenir; varlık
    sınıfı anahtar kelimelerine en çok uyan ve toplamı ~%100 olan tercih edilir.
    """
    raw_candidates: list[list[AllocItem]] = []
    raw_candidates.extend(from_chartjs(html))
    rsc = from_rsc(html)
    if rsc:
        raw_candidates.append(rsc)
    leg = from_legend(html)
    if leg:
        raw_candidates.append(leg)
    tbl = from_table(html)
    if tbl:
        raw_candidates.append(tbl)

    # Etiket temizliği: yalnız-sayı/çoğunlukla-sayı gürültüsünü at, ama 'BIST 30
    # Hisse' gibi rakamlı gerçek adları koru (is_label).
    def _clean(items: list[AllocItem]) -> list[AllocItem]:
        return [AllocItem(it.name.strip(), it.percent) for it in items if is_label(it.name)]

    candidates = [c for c in (_clean(x) for x in raw_candidates) if c]

    best: list[AllocItem] = []
    best_score = (-1, 0.0)
    for items in candidates:
        if not items or len(items) > 20:
            continue
        labels = [it.name for it in items]
        total = sum(it.percent for it in items)
        score = _looks_asset(labels)
        # Gerçek bir varlık dağılımı ~%100'e toplanır; aksi (tek başına "Fon
        # Getiri %-0.02" gibi) gürültüyü ele.
        if not (85 <= total <= 110):
            continue
        close = 1 if 90 <= total <= 105 else 0
        key = (score + close, -abs(100 - total))
        # Varlık ipucu içeren VEYA tek başına ~%100 olan (tek-sınıflı fon) adayı kabul et.
        ok_kind = score >= 1 or (len(items) == 1 and 95 <= total <= 105)
        if ok_kind and key > best_score:
            best_score = key
            best = items
    return best


def find_date(html: str, near: str | None = None) -> date | None:
    """HTML'de (opsiyonel olarak `near` ifadesinin yakınında) bir tarih bulur."""
    region = html
    if near:
        idx = html.find(near)
        if idx >= 0:
            region = html[max(0, idx - 200): idx + 400]
    m = re.search(r"(\d{2})[./](\d{2})[./](\d{4})", region)
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def snapshot_to_dict(s: AllocSnapshot) -> dict:
    return {
        "items": [it.to_dict() for it in s.items],
        "source": s.source,
        "source_url": s.source_url,
        "as_of": s.as_of.isoformat() if s.as_of else None,
        "report_url": s.report_url,
    }
