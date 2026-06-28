import { useState } from 'react'
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
import { compareFunds } from '../api'
import { num, pct } from '../format'

const COLORS = ['#1d9e75', '#2f6feb', '#d8453a', '#e07b39', '#7f77dd', '#caa21f']
const cls = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')

export default function FundCompare() {
  const [codes, setCodes] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [period, setPeriod] = useState(12)
  const [submitted, setSubmitted] = useState<string[]>([])

  const q = useQuery({
    queryKey: ['compare', submitted, period],
    queryFn: () => compareFunds(submitted, period),
    enabled: submitted.length > 0,
  })

  const addCode = (e: FormEvent) => {
    e.preventDefault()
    const c = input.trim().toUpperCase()
    if (c && !codes.includes(c) && codes.length < 6) setCodes([...codes, c])
    setInput('')
  }
  const remove = (c: string) => setCodes(codes.filter((x) => x !== c))

  return (
    <div className="card">
      <h2>Fon Karşılaştırma</h2>

      <form className="row" onSubmit={addCode}>
        <input
          className="input"
          placeholder="Fon kodu ekle (örn. AAS) — en çok 6"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
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
        </div>
      )}

      <div className="compare-actions">
        <div className="period-row">
          {[3, 12, 36, 60].map((p) => (
            <button
              key={p}
              className={`chip ${period === p ? 'active' : ''}`}
              onClick={() => setPeriod(p)}
            >
              {p === 3 ? '3A' : `${p / 12}Y`}
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
                      <b>{f.code}</b>
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

          <div className="muted small chart-caption">Rebased NAV (başlangıç = 100)</div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={q.data.chart} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="date"
                tickFormatter={(d: string) => d.slice(5)}
                minTickGap={28}
                fontSize={11}
                stroke="var(--muted)"
              />
              <YAxis domain={['auto', 'auto']} width={46} fontSize={11} stroke="var(--muted)" />
              <Tooltip />
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
        </>
      )}
    </div>
  )
}
