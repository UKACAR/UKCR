import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { compareFunds, searchFunds } from '../api'
import { num, pct } from '../format'
import MonthlyReturns from './MonthlyReturns'

const COLORS = ['#1d9e75', '#2f6feb', '#d8453a', '#e07b39', '#7f77dd', '#caa21f']
const cls = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')

const PERIODS = [
  { label: '1H', days: 7 },
  { label: '1A', days: 30 },
  { label: '3A', days: 90 },
  { label: '1Y', days: 365 },
  { label: '3Y', days: 1095 },
  { label: '5Y', days: 1825 },
]

const STORAGE_KEY = 'ukcr.compare.codes'

function loadCodes(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string').slice(0, 6) : []
  } catch {
    return []
  }
}

export default function FundCompare({ onOpenFund }: { onOpenFund?: (code: string) => void }) {
  const [codes, setCodes] = useState<string[]>(loadCodes)
  const [input, setInput] = useState('')
  const [period, setPeriod] = useState(365)
  const [submitted, setSubmitted] = useState<string[]>(loadCodes)

  // Karşılaştırma listesini tarayıcıda sakla (tekrar açınca gelsin)
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(codes))
    } catch {
      /* yoksay */
    }
  }, [codes])

  const q = useQuery({
    queryKey: ['compare', submitted, period],
    queryFn: () => compareFunds(submitted, period),
    enabled: submitted.length > 0,
  })

  const term = input.trim()
  const suggestQ = useQuery({
    queryKey: ['fundSuggest', term],
    queryFn: () => searchFunds(term, undefined, 8),
    enabled: term.length >= 2,
  })
  const showSuggest = term.length >= 2 && (suggestQ.data?.length ?? 0) > 0

  const addCode = (raw: string) => {
    const c = raw.trim().toUpperCase()
    if (c && !codes.includes(c) && codes.length < 6) setCodes([...codes, c])
    setInput('')
  }
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    addCode(input)
  }
  const remove = (c: string) => {
    setCodes(codes.filter((x) => x !== c))
    setSubmitted((prev) => prev.filter((x) => x !== c))
  }
  const clearAll = () => {
    setCodes([])
    setSubmitted([])
  }

  return (
    <div className="card ac-purple">
      <h2>Fon Karşılaştırma</h2>

      <form className="row" onSubmit={onSubmit} autoComplete="off">
        <div className="suggest-wrap">
          <input
            className="input"
            placeholder="Fon kodu veya adı yaz (örn. ALTIN, AAS) — en çok 6"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          {showSuggest && (
            <ul className="suggest-list">
              {suggestQ.data!.map((f) => (
                <li key={f.code}>
                  <button
                    type="button"
                    className="suggest-item"
                    onMouseDown={(e) => {
                      e.preventDefault()
                      addCode(f.code)
                    }}
                  >
                    <span className="code">{f.code}</span>
                    <span className="title">{f.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <button className="btn btn-ghost" type="submit">
          + Ekle
        </button>
      </form>

      {codes.length > 0 && (
        <div className="chip-row">
          {codes.map((c, i) => (
            <span key={c} className="chip removable">
              <span className="dot" style={{ background: COLORS[i % COLORS.length] }} />
              {c}
              <button type="button" onClick={() => remove(c)}>
                ✕
              </button>
            </span>
          ))}
          <button type="button" className="btn-ghost-sm clear-all" onClick={clearAll}>
            Tümünü temizle
          </button>
        </div>
      )}

      <div className="compare-actions">
        <div className="period-row">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              className={`chip ${period === p.days ? 'active' : ''}`}
              onClick={() => setPeriod(p.days)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <button className="btn" disabled={codes.length === 0} onClick={() => setSubmitted(codes)}>
          Karşılaştır
        </button>
      </div>

      {q.isFetching && (
        <p className="muted">Karşılaştırılıyor… (eksik veriler TEFAS'tan çekiliyor)</p>
      )}

      {q.data && q.data.funds.length > 0 && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fon</th>
                  <th className="r">Son NAV</th>
                  <th className="r">1A</th>
                  <th className="r">3A</th>
                  <th className="r">6A</th>
                  <th className="r">1Y</th>
                  <th className="r">YBB</th>
                  <th className="r">Volatilite</th>
                  <th className="r">Max Düşüş</th>
                </tr>
              </thead>
              <tbody>
                {q.data.funds.map((f, i) => (
                  <tr key={f.code}>
                    <td>
                      <span className="dot" style={{ background: COLORS[i % COLORS.length] }} />
                      {onOpenFund ? (
                        <button type="button" className="link-code" onClick={() => onOpenFund(f.code)}>
                          {f.code}
                        </button>
                      ) : (
                        <b>{f.code}</b>
                      )}
                      <div className="muted small">{f.title}</div>
                    </td>
                    <td className="r">{num(f.last_price, 4)}</td>
                    <td className={`r ${cls(f.ret_1m)}`}>{pct(f.ret_1m)}</td>
                    <td className={`r ${cls(f.ret_3m)}`}>{pct(f.ret_3m)}</td>
                    <td className={`r ${cls(f.ret_6m)}`}>{pct(f.ret_6m)}</td>
                    <td className={`r ${cls(f.ret_1y)}`}>{pct(f.ret_1y)}</td>
                    <td className={`r ${cls(f.ret_ytd)}`}>{pct(f.ret_ytd)}</td>
                    <td className="r">{pct(f.volatility)}</td>
                    <td className="r neg">{pct(f.max_drawdown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="muted small chart-caption">
            Başlangıca göre kümülatif % değişim (başlangıç = %0)
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart
              data={q.data.chart.map((row) => {
                const o: Record<string, number | string> = { date: row.date as string }
                for (const f of q.data!.funds) {
                  const v = row[f.code]
                  o[f.code] = typeof v === 'number' ? Number((v - 100).toFixed(2)) : v
                }
                return o
              })}
              margin={{ top: 8, right: 12, bottom: 4, left: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tickFormatter={(d: string) => d.slice(5)}
                minTickGap={28}
                fontSize={11}
                stroke="var(--muted)"
              />
              <YAxis
                domain={['auto', 'auto']}
                width={52}
                fontSize={11}
                stroke="var(--muted)"
                tickFormatter={(v: number) => `%${v.toFixed(0)}`}
              />
              <Tooltip formatter={(v, name) => [`%${Number(v).toFixed(2)}`, name]} />
              <Legend />
              {q.data.funds.map((f, i) => (
                <Line
                  key={f.code}
                  type="monotone"
                  dataKey={f.code}
                  stroke={COLORS[i % COLORS.length]}
                  dot={false}
                  strokeWidth={2}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>

          <div className="compare-monthly">
            <h3>Aylık Getiriler</h3>
            {q.data.funds.map((f, i) => (
              <div key={f.code} className="cmp-monthly-fund">
                <div className="cmp-monthly-head">
                  <span className="dot" style={{ background: COLORS[i % COLORS.length] }} />
                  <b>{f.code}</b> <span className="muted small">{f.title}</span>
                </div>
                <MonthlyReturns code={f.code} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
