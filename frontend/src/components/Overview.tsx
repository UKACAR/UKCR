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
import { getIndexChart, getMovers, getNews, getOverview, getSummary, listPortfolios } from '../api'
import type { MoverItem } from '../types'
import { num, pct, tl } from '../format'

const KINDS = [
  { id: 'FON', label: 'Fonlar' },
  { id: 'ETF', label: 'ETF' },
  { id: 'BES', label: 'BES' },
]

const RANGES = [
  { id: '1mo', label: '1A' },
  { id: '3mo', label: '3A' },
  { id: '6mo', label: '6A' },
  { id: '1y', label: '1Y' },
]

function MoversTable({ items, onOpen }: { items: MoverItem[]; onOpen?: (code: string) => void }) {
  if (items.length === 0) return <p className="muted small">Veri yok.</p>
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Fon</th>
            <th className="r">Son NAV</th>
            <th className="r">Değişim</th>
          </tr>
        </thead>
        <tbody>
          {items.map((m, i) => (
            <tr key={m.code}>
              <td>
                <span className="rank">{i + 1}</span>{' '}
                {onOpen ? (
                  <button type="button" className="link-code" onClick={() => onOpen(m.code)}>
                    {m.code}
                  </button>
                ) : (
                  <b>{m.code}</b>
                )}
                <div className="muted small">{m.title}</div>
              </td>
              <td className="r">{num(m.last_price, 4)}</td>
              <td className={`r ${m.change >= 0 ? 'pos' : 'neg'}`}>{pct(m.change)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Overview({
  onGoPortfolio,
  onOpenFund,
}: {
  onGoPortfolio?: () => void
  onOpenFund?: (code: string) => void
}) {
  const [kind, setKind] = useState('FON')
  const [range, setRange] = useState('1mo')

  // Piyasa şeridi ve enler açıkken kendiliğinden tazelensin (veri ~15 dk gecikmeli).
  // refetchIntervalInBackground: sekme arka planda olsa bile tazelensin.
  // Ticker'ı sunucu cache'inden (60sn) daha sık yokla ki taze değer gecikmeden
  // gelsin (eşit periyot faz kayması ~120sn gecikme yaratırdı).
  const overviewQ = useQuery({
    queryKey: ['overview'],
    queryFn: getOverview,
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
  })
  const indexQ = useQuery({
    queryKey: ['index', range],
    queryFn: () => getIndexChart('XU100.IS', range),
    refetchInterval: 300_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
  })
  const newsQ = useQuery({ queryKey: ['news'], queryFn: () => getNews(), refetchInterval: 600_000 })
  const moversQ = useQuery({
    queryKey: ['movers', kind],
    queryFn: () => getMovers(kind),
    refetchInterval: 300_000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
  })
  const portfoliosQ = useQuery({ queryKey: ['portfolios'], queryFn: listPortfolios })
  const pid = portfoliosQ.data?.[0]?.id
  const summaryQ = useQuery({
    queryKey: ['summary', pid],
    queryFn: () => getSummary(pid as number),
    enabled: pid != null,
  })

  const pts = indexQ.data ?? []
  const bistFirst = pts.length ? pts[0].close : null
  const bistChartLast = pts.length ? pts[pts.length - 1].close : null
  // Başlık: güncel BİST 100 değeri ve GÜNLÜK değişim (piyasa şeridiyle aynı kaynak,
  // diğer sitelerle uyumlu). Grafik dizisinin uçlarından hesaplanan oran ise
  // seçili DÖNEM getirisidir; ayrı ve etiketli gösteriyoruz (karışmasın diye).
  const bistMarket = overviewQ.data?.market.find((m) => m.label === 'BİST 100')
  const bistVal = bistMarket?.value ?? bistChartLast
  const bistDailyChg = bistMarket?.change ?? null
  const periodReturn =
    bistChartLast != null && bistFirst != null ? bistChartLast / bistFirst - 1 : null
  const rangeLabel = RANGES.find((r) => r.id === range)?.label ?? ''

  return (
    <div className="stack">
      {/* Piyasa şeridi */}
      <div className="ticker-row">
        {overviewQ.data?.market.map((m) => (
          <div
            className={`ticker ${m.change == null ? '' : m.change >= 0 ? 'up' : 'down'}`}
            key={m.label}
          >
            <div className="ticker-label">{m.label}</div>
            <div className="ticker-value">{num(m.value, 2)}</div>
            {m.change != null && (
              <div className={`ticker-change ${m.change >= 0 ? 'pos' : 'neg'}`}>{pct(m.change)}</div>
            )}
          </div>
        ))}
        {overviewQ.data && overviewQ.data.market.length === 0 && (
          <div className="muted small">Piyasa verisi alınamadı.</div>
        )}
      </div>

      {/* BİST 100 grafiği */}
      <div className="card ac-blue">
        <div className="enler-head">
          <h2>
            BİST 100{' '}
            {bistVal != null && <span className="bist-val">{num(bistVal, 2)}</span>}{' '}
            {bistDailyChg != null && (
              <span className={`bist-chg ${bistDailyChg >= 0 ? 'pos' : 'neg'}`}>
                {pct(bistDailyChg)}
              </span>
            )}
          </h2>
          <div className="period-row">
            {RANGES.map((rg) => (
              <button
                key={rg.id}
                className={`chip ${range === rg.id ? 'active' : ''}`}
                onClick={() => setRange(rg.id)}
              >
                {rg.label}
              </button>
            ))}
          </div>
        </div>
        {pts.length === 0 ? (
          <p className="muted">{indexQ.isLoading ? 'Grafik yükleniyor…' : 'Grafik verisi yok.'}</p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
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
                width={56}
                fontSize={11}
                stroke="var(--muted)"
                tickFormatter={(v: number) => v.toFixed(0)}
              />
              <Tooltip
                formatter={(v) => [Number(v).toFixed(2), 'BİST 100']}
                labelFormatter={(l) => String(l)}
              />
              <Line type="monotone" dataKey="close" stroke="var(--accent)" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
        {periodReturn != null && (
          <p className="muted small chart-caption">
            Seçili dönem ({rangeLabel}) getirisi:{' '}
            <span className={periodReturn >= 0 ? 'pos' : 'neg'}>{pct(periodReturn)}</span> · günlük
            değişim başlıkta
          </p>
        )}
      </div>

      <div className="overview-cols">
        {/* Sol: portföy + günün enleri */}
        <div className="stack">
          {summaryQ.data && (
            <div className="card ac-teal">
              <h2>Portföy Özeti</h2>
              <div className="overview-portfolio">
                <div>
                  <div className="muted small">Güncel Değer</div>
                  <b className="big">{tl(summaryQ.data.current_value)}</b>
                </div>
                <div>
                  <div className="muted small">Toplam K/Z</div>
                  <b className={`big ${summaryQ.data.total_pl >= 0 ? 'pos' : 'neg'}`}>
                    {tl(summaryQ.data.total_pl)}
                  </b>
                </div>
                <div>
                  <div className="muted small">Getiri</div>
                  <b className={`big ${(summaryQ.data.simple_return ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                    {pct(summaryQ.data.simple_return)}
                  </b>
                </div>
                <div>
                  <div className="muted small">Reel Getiri</div>
                  <b className="big">
                    {summaryQ.data.real_return == null ? '—' : pct(summaryQ.data.real_return)}
                  </b>
                </div>
                {onGoPortfolio && (
                  <button className="btn btn-ghost go-portfolio" onClick={onGoPortfolio}>
                    Portföyüm →
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="card ac-green">
            <div className="enler-head">
              <h2>Günün Enleri</h2>
              <div className="period-row">
                {KINDS.map((k) => (
                  <button
                    key={k.id}
                    className={`chip ${kind === k.id ? 'active' : ''}`}
                    onClick={() => setKind(k.id)}
                  >
                    {k.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="enler-grid">
              <div>
                <div className="enler-title pos">▲ Kazananlar</div>
                <MoversTable items={moversQ.data?.gainers ?? []} onOpen={onOpenFund} />
              </div>
              <div>
                <div className="enler-title neg">▼ Kaybedenler</div>
                <MoversTable items={moversQ.data?.losers ?? []} onOpen={onOpenFund} />
              </div>
            </div>
            {moversQ.data?.as_of && (
              <p className="muted small">Veri tarihi: {moversQ.data.as_of} · günlük NAV değişimi</p>
            )}
          </div>
        </div>

        {/* Sağ: haberler */}
        <div className="card ac-amber">
          <h2>Haberler</h2>
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
