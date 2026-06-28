"""Valör (settlement) hesabı — iş günü bazlı.

'Bu fonu bugün satarsan paran ne zaman elinde?' sorusunu yanıtlar.
Serbest fonlarda ihbar (notice) süresi + satış valörü toplanır.

NOT: v1 yalnızca hafta sonlarını atlar; resmî tatiller (bayram vb.) henüz
dikkate alınmaz — ileride tatil takvimi eklenecek.
"""

from __future__ import annotations

from datetime import date, timedelta


def add_business_days(start: date, n: int) -> date:
    """start'tan itibaren n iş günü ileri (Cmt/Pzr atlanır)."""
    if n <= 0:
        return start
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # 0=Pzt ... 4=Cuma
            added += 1
    return d


def settlement_date(
    sell_date: date, sell_valor_days: int | None, notice_days: int | None = None
) -> date:
    """Satış emri sonrası paranın hesaba geçeceği tahmini tarih."""
    total = (notice_days or 0) + (sell_valor_days or 0)
    return add_business_days(sell_date, total)
