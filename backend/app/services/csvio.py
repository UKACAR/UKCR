"""CSV içe/dışa aktarma — işlemler ve pozisyonlar.

İçe aktarmada başlıklar esnek eşleştirilir (Türkçe/İngilizce), tip Alış/Satış →
BUY/SELL'e çevrilir, ondalık ayraç olarak hem virgül hem nokta kabul edilir,
ayraç olarak ',' veya ';' otomatik algılanır.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

# CSV başlığı -> iç alan adı
_HEADER_ALIASES = {
    "tarih": "trade_date", "date": "trade_date",
    "tip": "type", "type": "type", "işlem": "type", "islem": "type", "yön": "type", "yon": "type",
    "fon": "fund_code", "fund": "fund_code", "code": "fund_code", "kod": "fund_code",
    "fon kodu": "fund_code", "fonkodu": "fund_code", "sembol": "fund_code",
    "adet": "quantity", "quantity": "quantity", "miktar": "quantity", "pay": "quantity",
    "fiyat": "price", "price": "price", "nav": "price", "birim fiyat": "price",
    "komisyon": "fee", "fee": "fee", "masraf": "fee", "ücret": "fee",
    "not": "note", "note": "note", "açıklama": "note", "aciklama": "note",
}
_TYPE_MAP = {
    "BUY": "BUY", "SELL": "SELL",
    "ALIŞ": "BUY", "ALIS": "BUY", "AL": "BUY", "ALIM": "BUY",
    "SATIŞ": "SELL", "SATIS": "SELL", "SAT": "SELL", "SATIM": "SELL",
}


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _num(s) -> float | None:
    s = (str(s) if s is not None else "").strip()
    if not s:
        return None
    if "," in s and "." in s:       # 1.234,56 -> 1234.56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                   # 12,5 -> 12.5
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_transactions_csv(text: str) -> tuple[list[dict], list[str]]:
    """CSV metnini doğrulanmış işlem dict'lerine ve hata listesine çevirir."""
    errors: list[str] = []
    sample = text[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return [], ["Boş veya başlıksız CSV."]

    fieldmap = {h: _HEADER_ALIASES[h.strip().lower()] for h in reader.fieldnames if h and h.strip().lower() in _HEADER_ALIASES}
    missing = {"trade_date", "type", "fund_code", "quantity"} - set(fieldmap.values())
    if missing:
        return [], [f"Eksik zorunlu sütun(lar): {', '.join(sorted(missing))}. Beklenen: tarih, tip, fon, adet."]

    rows: list[dict] = []
    for i, raw in enumerate(reader, start=2):  # satır 1 = başlık
        rec = {key: raw.get(h) for h, key in fieldmap.items()}
        d = _parse_date(rec.get("trade_date", ""))
        typ = _TYPE_MAP.get((rec.get("type") or "").strip().upper())
        code = (rec.get("fund_code") or "").strip().upper()
        qty = _num(rec.get("quantity"))
        if not code or d is None or typ is None or not qty or qty <= 0:
            errors.append(
                f"Satır {i}: geçersiz (fon={code or '?'}, tarih={rec.get('trade_date')}, "
                f"tip={rec.get('type')}, adet={rec.get('quantity')})"
            )
            continue
        rows.append({
            "trade_date": d,
            "type": typ,
            "fund_code": code,
            "quantity": qty,
            "price": _num(rec.get("price")),
            "fee": _num(rec.get("fee")) or 0.0,
            "note": (rec.get("note") or "").strip() or None,
        })
    return rows, errors


def transactions_to_csv(transactions) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["tarih", "tip", "fon", "adet", "fiyat", "komisyon", "not"])
    for t in transactions:
        w.writerow([
            t.trade_date.isoformat(), t.type, t.code,
            t.quantity, t.price, t.fee or 0, t.note or "",
        ])
    return out.getvalue()


def positions_to_csv(summary) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "fon", "ad", "adet", "ort_maliyet", "son_nav",
        "deger", "gerceklesmemis_kz", "gerceklesen_kz", "tahmini_stopaj",
    ])
    for p in summary.positions:
        w.writerow([
            p.code, p.title, p.units, p.avg_cost, p.last_price,
            p.market_value, p.unrealized_pl, p.realized_pl, p.estimated_stopaj,
        ])
    return out.getvalue()
