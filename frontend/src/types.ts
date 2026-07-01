export interface FundListItem {
  code: string
  title: string
  kind: string
  fund_type_desc?: string | null
  risk?: number | null
  status?: string | null
  ret_1m?: number | null
  ret_6m?: number | null
  ret_ytd?: number | null
  ret_1y?: number | null
}

export interface FundDetail extends FundListItem {
  ret_3m?: number | null
  ret_3y?: number | null
  ret_5y?: number | null
  currency?: string
  last_price?: number | null
  last_date?: string | null
  price_count: number
  category_rank?: number | null
  category_total?: number | null
  buy_valor_days?: number | null
  sell_valor_days?: number | null
  redemption_notice_days?: number | null
  valor_note?: string | null
  settlement_if_sold_today?: string | null
}

export interface ValorUpdate {
  buy_valor_days?: number | null
  sell_valor_days?: number | null
  redemption_notice_days?: number | null
  valor_note?: string | null
}

export interface Reminder {
  id: number
  title: string
  date: string
  code: string
  kind: string
  done: boolean
}

export interface ReminderCreate {
  title: string
  date: string
  fund_code?: string | null
  kind?: string
}

export interface ImportResult {
  imported: number
  errors: string[]
}

export interface Alarm {
  id: number
  code: string
  title: string
  kind: string // PRICE_ABOVE | PRICE_BELOW
  threshold: number
  active: boolean
  note?: string | null
  last_price?: number | null
  triggered: boolean
  triggered_at?: string | null
}

export interface AlarmCreate {
  fund_code: string
  kind: string
  threshold: number
  note?: string | null
}

export interface MonthlyReturnsRow {
  year: number
  months: (number | null)[]
  total: number | null
}

export interface MonthlyReturns {
  code: string
  rows: MonthlyReturnsRow[]
}

export interface AllocItem {
  name: string
  percent: number
}

export interface AllocChange {
  name: string
  percent: number
  prev?: number | null
  delta?: number | null
}

export interface AllocSnapshot {
  as_of: string
  items: AllocItem[]
}

export interface FundAllocation {
  code: string
  title: string
  kurucu?: string
  supported: boolean
  source?: string | null
  source_url?: string | null
  report_url?: string | null
  snapshots: AllocSnapshot[]
  update_dates?: string[]
  change: AllocChange[]
  fallback?: {
    kurucu?: string
    kurucu_site?: string | null
    kap_search?: string
    note?: string
  }
  reason?: string
}

export interface Favorite {
  id: number
  type: 'FUND' | 'STOCK'
  code: string
  title: string
  last_price?: number | null
  change?: number | null
  last_date?: string | null
}

export interface FavoriteCreate {
  type: 'FUND' | 'STOCK'
  code: string
}

export interface MarketItem {
  label: string
  value: number
  change?: number | null
}

export interface Metal {
  key: string
  name: string
  symbol: string
  unit: string
  gram: boolean
  usd_price: number
  try_price: number | null
  usd_change: number | null
  try_change: number | null
  usd_gram?: number | null
  try_gram?: number | null
}

export interface MetalsData {
  metals: Metal[]
  usdtry: number | null
}

export interface MoverRow {
  code: string
  name: string | null
  price: number | null
  change: number | null
  volume: number | null
}

export interface BoardMovers {
  currency: 'TRY' | 'USD' | null
  count: number
  gainers: MoverRow[]
  losers: MoverRow[]
  most_traded: MoverRow[]
}

export type Sentiment = 'pozitif' | 'negatif' | 'karışık' | 'nötr'

export interface AiNum {
  etiket: string
  deger: string
  degisim: string
  hava: Sentiment
}

export interface AiReportSection {
  baslik: string
  yorum: string
  hava: Sentiment
  one_cikanlar: string[]
}

export interface AiHaber {
  baslik: string
  etki: string
}

export interface AiReportBody {
  ozet: string
  genel_hava: Sentiment
  gunun_rakamlari: AiNum[]
  bolumler: AiReportSection[]
  temalar: string[]
  one_cikan_haberler: AiHaber[]
  riskler: string[]
  firsatlar: string[]
  beklenti: string
  kapanis: string
  mode: 'ai' | 'kural'
  model?: string | null
}

export interface AiReport {
  date: string
  generated_at: string
  report: AiReportBody
  note?: string | null
}

export interface BoardItem {
  label: string
  symbol: string
  value: number
  change: number | null
  try_value?: number | null
}

export interface BoardData {
  items: BoardItem[]
  usdtry: number | null
}

export interface MoverItem {
  code: string
  title: string
  last_price: number
  change: number
}

export interface Overview {
  as_of?: string | null
  market: MarketItem[]
}

export interface Movers {
  as_of?: string | null
  gainers: MoverItem[]
  losers: MoverItem[]
}

export interface NewsItem {
  title: string
  link: string
  source: string
  when: string
}

export interface IndexPoint {
  date: string
  close: number
}

export interface PricePoint {
  date: string
  price: number
  category_rank?: number | null
  category_total?: number | null
}

export interface Portfolio {
  id: number
  name: string
}

export interface Transaction {
  id: number
  instrument_id: number
  code: string
  type: 'BUY' | 'SELL'
  quantity: number
  price: number
  trade_date: string
  fee: number
  note?: string | null
}

export interface TransactionCreate {
  fund_code: string
  type: 'BUY' | 'SELL'
  quantity: number
  price?: number | null
  trade_date: string
  fee?: number
  note?: string | null
}

export interface TransactionUpdate {
  type?: 'BUY' | 'SELL'
  quantity?: number
  price?: number | null
  trade_date?: string
  fee?: number
  note?: string | null
}

export interface Position {
  code: string
  title: string
  units: number
  avg_cost: number
  last_price: number
  last_date?: string | null
  cost_basis: number
  market_value: number
  unrealized_pl: number
  realized_pl: number
  total_pl: number
  estimated_stopaj: number
}

export interface CompareMetrics {
  code: string
  title: string
  last_price?: number | null
  last_date?: string | null
  ret_1m?: number | null
  ret_3m?: number | null
  ret_6m?: number | null
  ret_1y?: number | null
  ret_ytd?: number | null
  volatility?: number | null
  max_drawdown?: number | null
}

export interface CompareResponse {
  funds: CompareMetrics[]
  chart: Record<string, number | string>[]
}

export interface PerfDay {
  date: string
  value: number
  pl: number
  pl_pct: number
}

export interface PeriodMap {
  week: number | null
  m1: number | null
  m3: number | null
  m6: number | null
  y1: number | null
}

export interface PortfolioPerformance {
  mode: 'holdings' | 'none'
  daily: PerfDay[]
  returns: PeriodMap
  returns_tl: PeriodMap
}

export interface Summary {
  as_of: string
  total_invested: number
  current_value: number
  unrealized_pl: number
  realized_pl: number
  total_pl: number
  simple_return?: number | null
  xirr?: number | null
  estimated_stopaj: number
  net_value: number
  real_return?: number | null
  positions: Position[]
}
