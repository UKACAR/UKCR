import { useQuery } from '@tanstack/react-query'
import { getOverview, getSummary, listPortfolios } from '../api'
import type { MoverItem } from '../types'
import { num, pct, tl } from '../format'

function MoversTable({ title, items, cls }: { title: string; items: MoverItem[]; cls: string }) {
  return (
    <div className={`card ${cls}`}>
      <h2>{title}</h2>
      {items.length === 0 ? (
        <p className="muted">Veri yok.</p>
      ) : (
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
      )}
    </div>
  )
}

export default function Overview({ onGoPortfolio }: { onGoPortfolio?: () => void }) {
  const q = useQuery({ queryKey: ['overview'], queryFn: getOverview })
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
        {q.data?.market.map((m) => (
          <div className="ticker" key={m.label}>
            <div className="ticker-label">{m.label}</div>
            <div className="ticker-value">{num(m.value, 4)}</div>
            {m.change != null && (
              <div className={`ticker-change ${m.change >= 0 ? 'pos' : 'neg'}`}>{pct(m.change)}</div>
            )}
          </div>
        ))}
        {q.data && q.data.market.length === 0 && (
          <div className="muted small">Döviz verisi için EVDS API anahtarı gerekli.</div>
        )}
      </div>

      {/* Portföy özeti mini */}
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

      {/* Günün Enleri (Fonlar) */}
      <div className="enler-grid">
        <MoversTable title="Günün Kazananları" items={q.data?.gainers ?? []} cls="ac-green" />
        <MoversTable title="Günün Kaybedenleri" items={q.data?.losers ?? []} cls="ac-red" />
      </div>

      {q.isLoading && <p className="muted">Yükleniyor…</p>}
      {q.data?.as_of && (
        <p className="muted small">
          Veri tarihi: {q.data.as_of} · fonların son günlük NAV değişimine göre
        </p>
      )}
    </div>
  )
}
