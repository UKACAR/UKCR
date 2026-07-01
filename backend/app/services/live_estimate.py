"""Portföy için TAHMİNİ anlık (gün içi) K/Z.

TEFAS fonları günde bir kez NAV ile fiyatlanır; gün içi gerçek değer bilinemez.
Bu modül her fonun varlık DAĞILIMINI (kurucu sitesinden, önbellekli) dayanak
endekslerin gün içi değişimiyle çarparak kaba bir GÖSTERGE tahmini üretir —
kesin değildir, resmî NAV değildir.

Varlık sınıfı -> dayanak eşleştirmesi:
  - Yurt içi hisse                 -> BİST 100 (XU100)
  - Yabancı hisse / menkul kıymet  -> yarı iletken fonu: SOXX; teknoloji: Nasdaq;
                                      diğer: S&P 500   (+ USD/TRY, USD bazlı olduğu için)
  - Döviz mevduatı / eurobond      -> USD/TRY
  - Repo, para piyasası, tahvil/bono, fon, teminat, GYF, kira sert. -> ~0 (gün içi ihmal)
"""

from __future__ import annotations

import unicodedata

from sqlalchemy.orm import Session

from app.services import market
from app.services.allocation import get_allocation
from app.services.returns import portfolio_summary


def _norm(s: str) -> str:
    """Aksan/birleşik işaretleri kaldırıp küçük harfe indirir (Türkçe İ/ı güvenli).

    'YARI İLETKEN' -> 'yari iletken', 'Yabancı' -> 'yabanci'. İ.lower()'ın birleşik
    noktası NFKD ile, dotless ı (U+0131) ise açık eşlemeyle 'i'ye indirilir.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("ı", "i")


def _ret(symbol: str) -> float:
    """Bir sembolün günlük (önceki kapanışa göre) değişimi; alınamazsa 0."""
    q = market.quote_one(symbol)
    if not q or not q[1]:
        return 0.0
    price, prev = q
    return price / prev - 1.0


def _class_return(name: str, title: str, R: dict[str, float]) -> float:
    """Bir varlık sınıfının tahmini gün içi getirisi (dayanak proxy'sine göre)."""
    n = _norm(name)
    t = _norm(title)
    # Eurobond/döviz tahvili: hisse gibi değil; gün içi ~ sadece kur etkisi.
    if "eurobond" in n or "doviz" in n:
        return R["usdtry"]
    if "yabanci" in n:  # yabancı hisse / menkul kıymet
        if "iletken" in t or "semiconductor" in t:
            base = R["soxx"]  # yarı iletken fonu
        elif "teknoloji" in t or "nasdaq" in t or "abd" in t:
            base = R["nasdaq"]
        else:
            base = R["sp"]
        return base + R["usdtry"]  # USD bazlı -> kur etkisi eklenir
    if "hisse" in n:
        return R["bist"]
    return 0.0  # repo/para piyasası/tahvil/fon/teminat/GYF vb. gün içi ihmal


def portfolio_live_estimate(db: Session, portfolio_id: int) -> dict:
    """Portföyün tahmini anlık K/Z'ı: fon dağılımı × dayanak endekslerin gün içi hareketi."""
    s = portfolio_summary(db, portfolio_id)
    R = {
        "bist": _ret("XU100.IS"),
        "usdtry": _ret("TRY=X"),
        "soxx": _ret("SOXX"),
        "nasdaq": _ret("^IXIC"),
        "sp": _ret("^GSPC"),
    }

    positions: list[dict] = []
    total_est_pl = 0.0
    covered_value = 0.0
    uncovered_value = 0.0

    for p in s.positions:
        mv = float(p.market_value)
        try:
            a = get_allocation(db, p.code, refresh=False)
        except Exception:  # noqa: BLE001
            a = None
        snaps = (a or {}).get("snapshots") or []
        items = snaps[0].get("items") if snaps else None
        if not items:
            uncovered_value += mv
            positions.append({
                "code": p.code, "title": p.title, "market_value": mv,
                "est_return": None, "est_pl": None, "covered": False, "as_of": None,
            })
            continue
        est_return = sum(
            (it.get("percent") or 0.0) / 100.0 * _class_return(it.get("name", ""), p.title, R)
            for it in items
        )
        est_pl = mv * est_return
        total_est_pl += est_pl
        covered_value += mv
        positions.append({
            "code": p.code, "title": p.title, "market_value": mv,
            "est_return": est_return, "est_pl": est_pl, "covered": True,
            "as_of": snaps[0].get("as_of"),
        })

    total_value = float(s.current_value)
    return {
        "as_of": s.as_of.isoformat() if s.as_of else None,
        "estimated_pl": total_est_pl,
        "estimated_pct": (total_est_pl / total_value) if total_value else None,
        "current_value": total_value,
        "estimated_value": total_value + total_est_pl,
        "covered_value": covered_value,
        "uncovered_value": uncovered_value,
        "proxies": {k: v for k, v in R.items()},
        "positions": sorted(positions, key=lambda x: abs(x["est_pl"] or 0.0), reverse=True),
    }
