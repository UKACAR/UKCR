"""Veri modeli (SQLAlchemy 2.0).

Tasarım notları:
- Çok kullanıcıya hazır: portföyler `user_id` ile sahiplenir.
- İşlemler (transactions) DEĞİŞMEZ lot kayıtlarıdır; maliyet/getiri bunlardan türetilir.
- Fiyatlar (prices) fon başına günlük NAV zaman serisidir.
- Stopaj oranı (tax_rates) iktisap tarihine göre uygulanan bir takvimdir.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Enstrüman türleri
KIND_FON = "FON"
KIND_BES = "BES"
KIND_ETF = "ETF"
KIND_HISSE = "HISSE"

# İşlem türleri
TX_BUY = "BUY"
TX_SELL = "SELL"

# Alarm türleri (NAV eşiği)
ALARM_ABOVE = "PRICE_ABOVE"
ALARM_BELOW = "PRICE_BELOW"

# Favori türleri
FAV_FUND = "FUND"    # TEFAS fonu/BES/ETF (DB'de instruments)
FAV_STOCK = "STOCK"  # BİST hissesi (Yahoo Finance)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    portfolios: Mapped[list["Portfolio"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Instrument(Base):
    """Takip edilebilir bir enstrüman (fon/BES/ETF/hisse). Fonlar için TEFAS verisi."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # FONKODU
    kind: Mapped[str] = mapped_column(String(8), default=KIND_FON)
    title: Mapped[str] = mapped_column(String(255), default="")
    fund_type_desc: Mapped[str | None] = mapped_column(String(160), default=None)  # fonTurAciklama
    risk: Mapped[int | None] = mapped_column(Integer, default=None)  # riskDegeri 1-7
    status: Mapped[str | None] = mapped_column(String(32), default=None)  # tefasDurum
    currency: Mapped[str] = mapped_column(String(3), default="TRY")

    # Liste ucundan gelen son bilinen dönem getirileri (anlık görüntü, % olarak)
    ret_1m: Mapped[float | None] = mapped_column(Float, default=None)
    ret_3m: Mapped[float | None] = mapped_column(Float, default=None)
    ret_6m: Mapped[float | None] = mapped_column(Float, default=None)
    ret_ytd: Mapped[float | None] = mapped_column(Float, default=None)
    ret_1y: Mapped[float | None] = mapped_column(Float, default=None)
    ret_3y: Mapped[float | None] = mapped_column(Float, default=None)
    ret_5y: Mapped[float | None] = mapped_column(Float, default=None)

    # Vade/valör (kullanıcı girer; TEFAS fiyat API'sinde yok)
    buy_valor_days: Mapped[int | None] = mapped_column(Integer, default=None)       # alış valörü (iş günü)
    sell_valor_days: Mapped[int | None] = mapped_column(Integer, default=None)      # satış valörü (iş günü)
    redemption_notice_days: Mapped[int | None] = mapped_column(Integer, default=None)  # ihbar süresi (serbest fon)
    valor_note: Mapped[str | None] = mapped_column(String(255), default=None)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    prices: Mapped[list["Price"]] = relationship(
        back_populates="instrument", cascade="all, delete-orphan"
    )


class Price(Base):
    """Bir enstrümanın belirli bir gündeki NAV (pay fiyatı) kaydı."""

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("instrument_id", "date", name="uq_price_instrument_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    category_rank: Mapped[int | None] = mapped_column(Integer, default=None)
    category_total: Mapped[int | None] = mapped_column(Integer, default=None)

    instrument: Mapped["Instrument"] = relationship(back_populates="prices")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="Portföyüm")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="portfolios")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class Transaction(Base):
    """Değişmez alım/satım (lot) kaydı. trade_date = iktisap/satış tarihi (stopaj için kritik)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    type: Mapped[str] = mapped_column(String(4))  # BUY / SELL
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))  # adet (pay)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6))  # işlem fiyatı (NAV)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="transactions")
    instrument: Mapped["Instrument"] = relationship()

    @property
    def code(self) -> str:
        return self.instrument.code if self.instrument else ""


class TaxRate(Base):
    """Stopaj oranı takvimi — iktisap (alış) tarihine göre uygulanır.

    rate ondalıktır: 0.175 = %17.5. valid_to None ise hâlen geçerli.
    """

    __tablename__ = "tax_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    valid_from: Mapped[date] = mapped_column(Date, index=True)
    valid_to: Mapped[date | None] = mapped_column(Date, default=None)
    rate: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(255), default=None)


class Reminder(Base):
    """Vade/valör/özel hatırlatma. Bir fona bağlı olabilir (instrument_id) ya da serbest."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), default=None)
    title: Mapped[str] = mapped_column(String(200))
    date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="VADE")  # VADE / VALOR / CUSTOM
    done: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    instrument: Mapped["Instrument | None"] = relationship()

    @property
    def code(self) -> str:
        return self.instrument.code if self.instrument else ""


class Favorite(Base):
    """İzleme listesi öğesi — fon (TEFAS) ya da hisse (BİST/Yahoo).

    Fonlar `instruments` tablosundan zenginleştirilir; hisseler Yahoo'dan
    canlı çekilir. title, ekleme anında çözülüp saklanır (kod -> ad).
    """

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "code", name="uq_favorite_user_type_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(8))  # FUND / STOCK
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Alarm(Base):
    """Fon NAV (fiyat) eşik alarmı: fiyat eşiğin üstüne/altına geçince tetiklenir."""

    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # PRICE_ABOVE / PRICE_BELOW
    threshold: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    instrument: Mapped["Instrument"] = relationship()

    @property
    def code(self) -> str:
        return self.instrument.code if self.instrument else ""

    @property
    def title(self) -> str:
        return self.instrument.title if self.instrument else ""
