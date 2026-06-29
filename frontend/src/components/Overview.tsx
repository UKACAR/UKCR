import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getMovers, getNews, getOverview, getSummary, listPortfolios } from '../api'
import type { MoverItem } from '../types'
import { num, pct, tl } from '../format'

const KINDS = [
  { id: 'FON', label: 'Fonlar' },
  { id: 'ETF', label: 'ETF' },
]

function MoversTable({ items }: { items: MoverItem[] }) {
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
                <span className="rank">{i + 1}</span> <b>{m.code}</b>
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

export default function Overview({ onGoPortfolio }: { onGoPortfolio?: () => void }) {
  const [kind, setKind] = useState('FON')

  const overviewQ = useQuery({ queryKey: ['overview'], queryFn: getOverview })
  const newsQ = useQuery({ queryKey: ['news'], queryFn: getNews })
  const moversQ = useQuery({ queryKey: ['movers', kind], queryFn: () => getMovers(kind) })
  const portfoliosQ = useQuery({ queryKey: ['portfolios'], queryFn: listPortfolios })
  const pid = portfoliosQ.data?.[0]?.id
  const summaryQ = useQuery({
    queryKey: ['summary', pid],
    queryFn: () => getSummary(pid as number),
    enabled: pid != null,
  })

  return (
    <div className="stack">
      {/* Piyasa şeridi */}
      <div className="ticker-row">
        {overviewQ.data?.market.map((m) => (
          <div className="ticker" key={m.label}>
            <div className="ticker-label">{m.label}</div>
            <div className="ticker-value">{num(m.value, 4)}</div>
            {m.change != null && (
              <div className={`ticker-change ${m.change >= 0 ? 'pos' : 'neg'}`}>{pct(m.change)}</div>
            )}
          </div>
        ))}
        {overviewQ.data && overviewQ.data.market.length === 0 && (
          <div className="muted small">Piyasa verisi için EVDS API anahtarı gerekli.</div>
        )}
      </div>

      <div className="overview-cols">
        {/* Sol: portföy + günün enleri */}
        <div className="stack">
          {summaryQ.data && (
            <div className="card ac-blue">
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

          <div className="card ac-teal">
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
                <MoversTable items={moversQ.data?.gainers ?? []} />
              </div>
              <div>
                <div className="enler-title neg">▼ Kaybedenler</div>
                <MoversTable items={moversQ.data?.losers ?? []} />
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
