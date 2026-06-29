"""Varlık dağılımı servisi — kurucu sitesinden çek, değişince sakla, son 3 + delta döndür."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Allocation, Instrument
from app.ingestion import store

from . import adapters, base

_TOL = 0.5  # yüzde-puan; bu kadar oynamayı "değişim" sayma (günlük gürültüyü ele)
_FRESH = timedelta(hours=12)  # son çekim bu kadar tazeyse tekrar çekme (UI hızlı kalsın)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _agg(items: list[dict]) -> dict[str, float]:
    """Aynı adlı kalemleri toplar (mükerrer ad delta'da çakışmasın)."""
    d: dict[str, float] = {}
    for i in items:
        d[i["name"]] = round(d.get(i["name"], 0.0) + i["percent"], 2)
    return d


def _changed(old_items: list[dict], new_items: list[dict]) -> bool:
    od, nd = _agg(old_items), _agg(new_items)
    if set(od) != set(nd):
        return True
    return any(abs(od[k] - nd[k]) >= _TOL for k in nd)


def _rows(db: Session, instrument_id: int) -> list[Allocation]:
    return list(
        db.execute(
            select(Allocation)
            .where(Allocation.instrument_id == instrument_id)
            .order_by(Allocation.as_of.desc(), Allocation.id.desc())
        ).scalars().all()
    )


def _diff(latest: list[dict], prev: list[dict] | None) -> list[dict]:
    nd, pd = _agg(latest), _agg(prev or [])
    out = []
    for name, cur in nd.items():
        p = pd.get(name)
        out.append({
            "name": name,
            "percent": cur,
            "prev": p,
            "delta": (round(cur - p, 2) if p is not None else None),
        })
    return out


def get_allocation(db: Session, code: str, *, refresh: bool = True) -> dict:
    code = code.upper().strip()
    inst = store.resolve_instrument(db, code)
    if inst is None:
        return {"supported": False, "code": code, "reason": "Fon bulunamadı"}

    adapter = adapters.resolve(inst.title)
    kurucu = adapters.kurucu_key(inst.title)

    # Tazelik: son çekim 12 saatten yeniyse tekrar çekme (özellikle yavaş
    # siteler için UI'ı hızlı tut; veri zaten en çok günlük değişir).
    existing_rows = _rows(db, inst.id)
    _fa = _aware(existing_rows[0].fetched_at) if existing_rows else None
    fresh = bool(_fa and datetime.now(timezone.utc) - _fa < _FRESH)

    # Canlı çek + değiştiyse sakla
    if refresh and adapter is not None and not fresh:
        snap = None
        try:
            with base.make_client() as client:
                snap = adapter.fetch(code, inst.title, client)
        except Exception:  # noqa: BLE001
            snap = None
        if snap and snap.items:
            as_of = snap.as_of or datetime.now(timezone.utc).date()
            new_items = [it.to_dict() for it in snap.items]
            existing = db.execute(
                select(Allocation).where(
                    Allocation.instrument_id == inst.id,
                    Allocation.as_of == as_of,
                    Allocation.source == snap.source,
                )
            ).scalars().first()
            rows = _rows(db, inst.id)
            # Aynı kaynağın en yeni kaydına göre değişim kontrolü (kaynaklar karışmasın).
            same_src = next((r for r in rows if r.source == snap.source), None)
            if existing is not None:
                existing.items = new_items
                existing.source_url = snap.source_url
                existing.report_url = snap.report_url
                existing.fetched_at = datetime.now(timezone.utc)
            elif same_src is None or _changed(same_src.items, new_items):
                db.add(Allocation(
                    instrument_id=inst.id, as_of=as_of, source=snap.source,
                    source_url=snap.source_url, report_url=snap.report_url, items=new_items,
                ))
            try:
                db.commit()
            except IntegrityError:
                # Eşzamanlı istek aynı (fon,tarih,kaynak) satırını eklemiş olabilir.
                db.rollback()

    rows = _rows(db, inst.id)
    last3 = rows[:3]

    base_out = {
        "code": code,
        "title": inst.title,
        "kurucu": kurucu,
        "supported": adapter is not None,
        "source": (rows[0].source if rows else (adapter.name if adapter else None)),
        "source_url": (rows[0].source_url if rows else None),
        "report_url": (rows[0].report_url if rows else None),
    }

    if not rows:
        # Henüz veri yok → yedek linkler
        base_out["snapshots"] = []
        base_out["change"] = []
        base_out["fallback"] = {
            "kurucu": kurucu,
            "kurucu_site": adapter.site if adapter else None,
            "kap_search": "https://www.kap.org.tr/tr/bildirim-sorgulama",
            "note": (
                "Bu kurucu için otomatik dağılım henüz eklenmedi."
                if adapter is None
                else "Dağılım kurucu sitesinden çekilemedi; siteden inceleyebilirsiniz."
            ),
        }
        return base_out

    base_out["snapshots"] = [
        {"as_of": r.as_of.isoformat(), "items": r.items} for r in last3
    ]
    base_out["update_dates"] = [r.as_of.isoformat() for r in last3]
    base_out["change"] = _diff(last3[0].items, last3[1].items if len(last3) > 1 else None)
    base_out["source"] = last3[0].source
    base_out["source_url"] = last3[0].source_url
    base_out["report_url"] = last3[0].report_url
    return base_out
