import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getIndexChart, getMetals, getMetalsNews } from '../api'
import { num, pct, tl } from '../format'

const RANGES = [
  { id: '1mo', label: '1A' },
  { id: '3mo', label: '3A' },
  { id: '6mo', label: '6A' },
  { id: '1y', label: '1Y' },
]

const usd = (v: number | null | undefined) => (v == null ? '—' : `$${num(v, 2)}`)
const cls = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')

export default function Metals() {
  const [selected, setSelected] = useState<string>('gold')
  const [range, setRange] = useState('6mo')

  const metalsQ = useQuery({
    queryKey: ['metals'],
    queryFn: getMetals,
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
  })
  const newsQ = useQuery({ queryKey: ['metalsNews'], queryFn: getMetalsNews, refetchInterval: 600_000 })

  const metals = metalsQ.data?.metals ?? []
  const sel = metals.find((m) => m.key === selected) ?? metals[0]
  const chartQ = useQuery({
    queryKey: ['metalChart', sel?.symbol, range],
    queryFn: () => getIndexChart(sel!.symbol, range),
    enabled: !!sel,
  })
  const pts = chartQ.data ?? []

  return (
    <div className="stack">
      <div className="metals-grid">
        {metals.map((m) => {
          const chg = m.try_change ?? m.usd_change
          return (
          <button
            key={m.key}
            className={`metal-card ${sel?.key === m.key ? 'active' : ''} ${
              chg == null ? '' : chg >= 0 ? 'up' : 'down'
            }`}
            onClick={() => setSelected(m.key)}
          >
            <div className="metal-name">{m.name}</div>
            <div className="metal-gram">
              {m.gram ? tl(m.try_gram) : tl(m.try_price)}{' '}
              <span className="metal-unit">/{m.gram ? 'gram' : m.unit}</span>
            </div>
            {m.try_change != null && (
              <div className={`metal-chg ${cls(m.try_change)}`}>{pct(m.try_change)}</div>
            )}
            <div className="metal-detail">
              {m.gram ? (
                <>
                  <span>USD/ons</span>
                  <b>{usd(m.usd_price)}</b>
                  <span>USD/gram</span>
                  <b>{usd(m.usd_gram)}</b>
                  <span>TL/ons</span>
                  <b>{tl(m.try_price)}</b>
                  <span>USD değ.</span>
                  <b className={cls(m.usd_change)}>{pct(m.usd_change)}</b>
                </>
              ) : (
                <>
                  <span>USD/{m.unit}</span>
                  <b>{usd(m.usd_price)}</b>
                  <span>TL/{m.unit}</span>
                  <b>{tl(m.try_price)}</b>
                  <span>USD değ.</span>
                  <b className={cls(m.usd_change)}>{pct(m.usd_change)}</b>
                </>
              )}
            </div>
          </button>
          )
        })}
        {metalsQ.data && metals.length === 0 && (
          <p className="muted small">Kıymetli maden verisi alınamadı.</p>
        )}
      </div>

      {metalsQ.data?.usdtry != null && (
        <p className="muted small">
          Fiyatlar ~15 dk gecikmeli (Yahoo). Kur: 1 USD = {num(metalsQ.data.usdtry, 2)} ₺ · kıymetli
          madende gram = ons / 31,1035; petrol varil, doğalgaz MMBtu, bakır libre başınadır.
        </p>
      )}

      <div className="overview-cols">
        <div className="card ac-amber">
          <div className="enler-head">
            <h2>
              {sel?.name ?? 'Kıymetli Maden'} — USD/{sel?.unit ?? 'ons'}{' '}
              {sel && <span className="bist-val">{usd(sel.usd_price)}</span>}{' '}
              {sel?.usd_change != null && (
                <span className={`bist-chg ${cls(sel.usd_change)}`}>{pct(sel.usd_change)}</span>
              )}
            </h2>
            <div className="period-row">
              {RANGES.map((r) => (
                <button
                  key={r.id}
                  className={`chip ${range === r.id ? 'active' : ''}`}
                  onClick={() => setRange(r.id)}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          {pts.length === 0 ? (
            <p className="muted">{chartQ.isLoading ? 'Grafik yükleniyor…' : 'Grafik verisi yok.'}</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={pts} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
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
                  width={60}
                  fontSize={11}
                  stroke="var(--muted)"
                  tickFormatter={(v: number) => v.toFixed(0)}
                />
                <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, `USD/${sel?.unit ?? 'ons'}`]} />
                <Line type="monotone" dataKey="close" stroke="var(--ac-amber)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card ac-slate">
          <h2>Kıymetli Maden Haberleri</h2>
          {newsQ.isLoading && <p className="muted">Yükleniyor…</p>}
          {newsQ.data && newsQ.data.length === 0 && <p className="muted">Haber alınamadı.</p>}
          <ul className="news-list">
            {newsQ.data?.map((n, i) => (
              <li key={i}>
                <a href={n.link} target="_blank" rel="noreferrer">
                  {n.title}
                </a>
                <div className="news-meta">
                  {n.source}
                  {n.when && ` · ${n.when}`}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
