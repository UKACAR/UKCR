import axios from 'axios'
import type {
  Alarm,
  AlarmCreate,
  BoardData,
  CompareResponse,
  Favorite,
  FavoriteCreate,
  FundAllocation,
  FundDetail,
  MonthlyReturns,
  FundListItem,
  ImportResult,
  IndexPoint,
  MetalsData,
  Movers,
  NewsItem,
  Overview,
  Portfolio,
  PortfolioPerformance,
  PricePoint,
  Reminder,
  ReminderCreate,
  Summary,
  Transaction,
  TransactionCreate,
  TransactionUpdate,
  ValorUpdate,
} from './types'

const http = axios.create({ baseURL: '/api' })

export const searchFunds = (q: string, kind?: string, limit = 30) =>
  http
    .get<FundListItem[]>('/funds', {
      params: { q: q || undefined, kind: kind || undefined, limit },
    })
    .then((r) => r.data)

export const getFund = (code: string) =>
  http.get<FundDetail>(`/funds/${code}`).then((r) => r.data)

export const getFundPrices = (code: string, period = 12) =>
  http.get<PricePoint[]>(`/funds/${code}/prices`, { params: { period } }).then((r) => r.data)

export const getFundAllocation = (code: string) =>
  http.get<FundAllocation>(`/funds/${code}/allocation`).then((r) => r.data)

export const getFundMonthlyReturns = (code: string, years = 3, real = false) =>
  http
    .get<MonthlyReturns>(`/funds/${code}/monthly-returns`, { params: { years, real } })
    .then((r) => r.data)

export const listPortfolios = () => http.get<Portfolio[]>('/portfolios').then((r) => r.data)

export const createPortfolio = (name: string) =>
  http.post<Portfolio>('/portfolios', { name }).then((r) => r.data)

export const listTransactions = (pid: number) =>
  http.get<Transaction[]>(`/portfolios/${pid}/transactions`).then((r) => r.data)

export const addTransaction = (pid: number, body: TransactionCreate) =>
  http.post<Transaction>(`/portfolios/${pid}/transactions`, body).then((r) => r.data)

export const updateTransaction = (pid: number, txId: number, body: TransactionUpdate) =>
  http.patch<Transaction>(`/portfolios/${pid}/transactions/${txId}`, body).then((r) => r.data)

export const deleteTransaction = (pid: number, txId: number) =>
  http.delete(`/portfolios/${pid}/transactions/${txId}`).then((r) => r.data)

export const getSummary = (pid: number) =>
  http.get<Summary>(`/portfolios/${pid}/summary`).then((r) => r.data)

export const getPortfolioPerformance = (pid: number, months = 6) =>
  http
    .get<PortfolioPerformance>(`/portfolios/${pid}/performance`, { params: { months } })
    .then((r) => r.data)

export const compareFunds = (codes: string[], periodDays = 365) =>
  http
    .get<CompareResponse>('/compare', { params: { codes: codes.join(','), period_days: periodDays } })
    .then((r) => r.data)

export const updateValor = (code: string, body: ValorUpdate) =>
  http.patch<FundDetail>(`/funds/${code}/valor`, body).then((r) => r.data)

export const listReminders = () => http.get<Reminder[]>('/reminders').then((r) => r.data)

export const createReminder = (body: ReminderCreate) =>
  http.post<Reminder>('/reminders', body).then((r) => r.data)

export const setReminderDone = (id: number, done: boolean) =>
  http.patch<Reminder>(`/reminders/${id}`, null, { params: { done } }).then((r) => r.data)

export const deleteReminder = (id: number) =>
  http.delete(`/reminders/${id}`).then((r) => r.data)

export const importTransactions = (pid: number, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return http
    .post<ImportResult>(`/portfolios/${pid}/import/transactions`, fd)
    .then((r) => r.data)
}

export const exportTransactionsUrl = (pid: number) =>
  `/api/portfolios/${pid}/export/transactions.csv`

export const exportPositionsUrl = (pid: number) =>
  `/api/portfolios/${pid}/export/positions.csv`

export const listAlarms = () => http.get<Alarm[]>('/alarms').then((r) => r.data)

export const createAlarm = (body: AlarmCreate) =>
  http.post<Alarm>('/alarms', body).then((r) => r.data)

export const toggleAlarm = (id: number, active: boolean) =>
  http.patch<Alarm>(`/alarms/${id}`, null, { params: { active } }).then((r) => r.data)

export const deleteAlarm = (id: number) => http.delete(`/alarms/${id}`).then((r) => r.data)

export const listFavorites = () => http.get<Favorite[]>('/favorites').then((r) => r.data)

export const addFavorite = (body: FavoriteCreate) =>
  http.post<Favorite>('/favorites', body).then((r) => r.data)

export const deleteFavorite = (id: number) =>
  http.delete(`/favorites/${id}`).then((r) => r.data)

export const getOverview = () => http.get<Overview>('/overview').then((r) => r.data)

export const getMovers = (kind = 'FON') =>
  http.get<Movers>('/movers', { params: { kind } }).then((r) => r.data)

export const getNews = (topic = 'general') =>
  http.get<NewsItem[]>('/news', { params: { topic } }).then((r) => r.data)

export const getBoard = (name: string) =>
  http.get<BoardData>(`/board/${name}`).then((r) => r.data)

export const getMetals = () => http.get<MetalsData>('/metals').then((r) => r.data)

export const getMetalsNews = () => http.get<NewsItem[]>('/metals/news').then((r) => r.data)

export const getIndexChart = (symbol = 'XU100.IS', range = '1mo') =>
  http.get<IndexPoint[]>('/index', { params: { symbol, range } }).then((r) => r.data)
