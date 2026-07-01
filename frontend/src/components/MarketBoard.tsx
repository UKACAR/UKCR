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
import { getBoard, getIndexChart, getNews } from '../api'
import { num, pct, tl } from '../format'
import BoardMovers from './BoardMovers'

const RANGES = [
  { id: '1mo', label: '1A' },
  { id: '3mo', label: '3A' },
  { id: '6mo', label: '6A' },
  { id: '1y', label: '1Y' },
]

const cls = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')

export default function MarketBoard({
  board,
  newsTopic,
  newsTitle,
  note,
  moversBoard,
  showStats,
  usdPrimary,
}: {
  board: string
  newsTopic: string
  newsTitle: string
  note?: string
  moversBoard?: string
  showStats?: boolean
  usdPrimary?: boolean // USD ana değer, TL ikincil (kripto)
}) {
  const [range, setRange] = useState('6mo')
  const [selected, setSelected] = useState<string | null>(null)

  const boardQ = useQuery({
    queryKey: ['board', board],
    queryFn: () => getBoard(board),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
  })
  const newsQ = useQuery({
    queryKey: ['news', newsTopic],
    queryFn: () => getNews(newsTopic),
    refetchInterval: 600_000,
  })

  const items = boardQ.data?.items ?? []
  const sel = items.find((i) => i.symbol === selected) ?? items[0]
  const chartQ = useQuery({
    queryKey: ['boardChart', sel?.symbol, range],
    queryFn: () => getIndexChart(sel!.symbol, range),
    enabled: !!sel,
  })
  const pts = chartQ.data ?? []

  // İstatistik şeridi (Dünya borsaları): kaç kalem yükselmiş/düşmüş, ortalama, en iyi/kötü.
  const withChg = items.filter((i) => i.change != null)
  const up = withChg.filter((i) => (i.change as number) > 0)
  const down = withChg.filter((i) => (i.change as number) < 0)
  const flat = withChg.length - up.length - down.length
  const avg = withChg.length
    ? withChg.reduce((s, i) => s + (i.change as number), 0) / withChg.length
    : null
  const best = withChg.length
    ? withChg.reduce((a, b) => ((a.change as number) >= (b.change as number) ? a : b))
    : null
  const worst = withChg.length
    ? withChg.reduce((a, b) => ((a.change as number) <= (b.change as number) ? a : b))
    : null

  return (
    <div className="stack">
      <div className="metals-grid">
        {items.map((it) => (
          <button
            key={it.symbol}
            className={`metal-card ${sel?.symbol === it.symbol ? 'active' : ''} ${
              it.change == null ? '' : it.change >= 0 ? 'up' : 'down'
            }`}
            onClick={() => setSelected(it.symbol)}
          >
            <div className="metal-name">{it.label}</div>
            <div className="metal-gram">
              {usdPrimary ? (
                <>
                  ${num(it.value, 2)}
                  {it.try_value != null && (
                    <span className="metal-unit"> {tl(it.try_value)}</span>
                  )}
                </>
              ) : (
                <>
                  {it.try_value != null ? tl(it.try_value) : num(it.value, 2)}
                  {it.try_value != null && (
                    <span className="metal-unit"> ${num(it.value, 2)}</span>
                  )}
                </>
              )}
            </div>
            {it.change != null && (
              <div className={`metal-chg ${cls(it.change)}`}>{pct(it.change)}</div>
            )}
          </button>
        ))}
        {boardQ.data && items.length === 0 && (
          <p className="muted small">Veri alınamadı.</p>
        )}
      </div>

      {showStats && withChg.length > 0 && (
        <div className="board-stats">
          <span className="bs-up">🟢 {up.length} yükselen</span>
          <span className="bs-down">🔴 {down.length} düşen</span>
          {flat > 0 && <span className="bs-flat">⚪ {flat} yatay</span>}
          <span className="bs-sep">·</span>
          <span>
            Ortalama <b className={cls(avg)}>{pct(avg)}</b>
          </span>
          {best && (
            <span>
              En iyi <b>{best.label}</b>{' '}
              <span className={cls(best.change)}>{pct(best.change)}</span>
            </span>
          )}
          {worst && (
            <span>
              En kötü <b>{worst.label}</b>{' '}
              <span className={cls(worst.change)}>{pct(worst.change)}</span>
            </span>
          )}
        </div>
      )}

      {note && <p className="muted small">{note}</p>}

      <div className="overview-cols">
        <div className="card ac-blue">
          <div className="enler-head">
            <h2>
              {sel?.label ?? '—'}{' '}
              {sel && (
                <span className="bist-val">
                  {usdPrimary
                    ? `$${num(sel.value, 2)}`
                    : sel.try_value != null
                      ? tl(sel.try_value)
                      : num(sel.value, 2)}
                </span>
              )}{' '}
              {sel?.change != null && (
                <span className={`bist-chg ${cls(sel.change)}`}>{pct(sel.change)}</span>
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
                <YAxis domain={['auto', 'auto']} width={64} fontSize={11} stroke="var(--muted)" />
                <Tooltip formatter={(v) => [num(Number(v), 2), sel?.label ?? '']} />
                <Line type="monotone" dataKey="close" stroke="var(--accent-2)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card ac-slate">
          <h2>{newsTitle}</h2>
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

      {moversBoard && <BoardMovers board={moversBoard} />}
    </div>
  )
}
