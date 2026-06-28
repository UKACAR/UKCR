"""API şemaları (Pydantic v2). Para alanları taşımada float olarak verilir."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class FundListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    title: str
    kind: str
    fund_type_desc: str | None = None
    risk: int | None = None
    status: str | None = None
    ret_1m: float | None = None
    ret_6m: float | None = None
    ret_ytd: float | None = None
    ret_1y: float | None = None


class FundDetail(FundListItem):
    last_price: float | None = None
    last_date: date | None = None
    price_count: int = 0
    # Vade/valör
    buy_valor_days: int | None = None
    sell_valor_days: int | None = None
    redemption_notice_days: int | None = None
    valor_note: str | None = None
    settlement_if_sold_today: date | None = None  # bugün satılırsa paranın geçeceği tarih


class ValorUpdate(BaseModel):
    buy_valor_days: int | None = None
    sell_valor_days: int | None = None
    redemption_notice_days: int | None = None
    valor_note: str | None = None


class ReminderCreate(BaseModel):
    title: str
    date: date
    fund_code: str | None = None
    kind: str = "VADE"


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    date: date
    code: str = ""
    kind: str
    done: bool


class ImportResult(BaseModel):
    imported: int
    errors: list[str] = []


class MarketItem(BaseModel):
    label: str
    value: float
    change: float | None = None


class MoverItem(BaseModel):
    code: str
    title: str
    last_price: float
    change: float


class OverviewOut(BaseModel):
    as_of: date | None = None
    market: list[MarketItem] = []
    gainers: list[MoverItem] = []
    losers: list[MoverItem] = []


class AlarmCreate(BaseModel):
    fund_code: str
    kind: str = Field(pattern="^(PRICE_ABOVE|PRICE_BELOW)$")
    threshold: float
    note: str | None = None


class AlarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str = ""
    title: str = ""
    kind: str
    threshold: float
    active: bool
    note: str | None = None
    last_price: float | None = None
    triggered: bool = False
    triggered_at: datetime | None = None


class PriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: date
    price: float
    category_rank: int | None = None
    category_total: int | None = None


class PortfolioCreate(BaseModel):
    name: str = "Portföyüm"


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class TransactionCreate(BaseModel):
    fund_code: str
    type: str = Field(pattern="^(BUY|SELL)$")
    quantity: float = Field(gt=0)
    price: float | None = None  # boşsa o günün (veya öncesinin) NAV'ı kullanılır
    trade_date: date
    fee: float = 0.0
    note: str | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instrument_id: int
    code: str = ""
    type: str
    quantity: float
    price: float
    trade_date: date
    fee: float
    note: str | None = None


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    title: str
    units: float
    avg_cost: float
    last_price: float
    last_date: date | None = None
    cost_basis: float
    market_value: float
    unrealized_pl: float
    realized_pl: float
    total_pl: float
    estimated_stopaj: float


class CompareMetrics(BaseModel):
    code: str
    title: str
    last_price: float | None = None
    last_date: date | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_1y: float | None = None
    ret_ytd: float | None = None
    volatility: float | None = None
    max_drawdown: float | None = None


class CompareResponse(BaseModel):
    funds: list[CompareMetrics] = []
    chart: list[dict] = []  # [{date, KOD1: 100.0, ...}] — rebased NAV overlay


class SummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    as_of: date
    total_invested: float
    current_value: float
    unrealized_pl: float
    realized_pl: float
    total_pl: float
    simple_return: float | None = None
    xirr: float | None = None
    estimated_stopaj: float
    net_value: float
    real_return: float | None = None
    positions: list[PositionOut] = []
