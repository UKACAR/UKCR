import { useQuery } from '@tanstack/react-query'
import { getFundAllocation } from '../api'

const fmtDate = (iso: string) => {
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}
const sign = (v: number) => (v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2))

export default function FundAllocation({ code }: { code: string }) {
  const q = useQuery({ queryKey: ['allocation', code], queryFn: () => getFundAllocation(code) })

  if (q.isLoading) return <p className="muted small">Dağılım yükleniyor…</p>
  const a = q.data
  if (!a) return null

  const latest = a.snapshots?.[0]
  const deltaOf = (name: string) => a.change?.find((c) => c.name === name)?.delta ?? null

  return (
    <div className="alloc">
      <div className="alloc-head">
        <h4>Portföy Dağılımı</h4>
        {a.source && <span className="muted small">Kaynak: {a.source}</span>}
      </div>

      {latest && latest.items.length > 0 ? (
        <>
          {a.update_dates && a.update_dates.length > 0 && (
            <div className="muted small alloc-dates">
              Son güncellemeler: {a.update_dates.map(fmtDate).join(' · ')}
            </div>
          )}
          <ul className="alloc-bars">
            {latest.items.map((it) => {
              const d = deltaOf(it.name)
              return (
                <li key={it.name}>
                  <span className="alloc-name" title={it.name}>
                    {it.name}
                  </span>
                  <span className="alloc-track">
                    <span
                      className="alloc-fill"
                      style={{ width: `${Math.min(100, Math.max(2, it.percent))}%` }}
                    />
                  </span>
                  <span className="alloc-pct">%{it.percent.toFixed(2)}</span>
                  {d != null && d !== 0 && (
                    <span className={`alloc-delta ${d > 0 ? 'pos' : 'neg'}`}>{sign(d)}</span>
                  )}
                </li>
              )
            })}
          </ul>
          <div className="alloc-links">
            {a.report_url && (
              <a href={a.report_url} target="_blank" rel="noreferrer">
                Aylık varlık raporu →
              </a>
            )}
            {a.source_url && (
              <a href={a.source_url} target="_blank" rel="noreferrer">
                Kurucu sayfası →
              </a>
            )}
          </div>
        </>
      ) : (
        <div className="alloc-fallback">
          <p className="muted small">
            {a.fallback?.note ??
              'Bu fon için otomatik dağılım verisi henüz yok.'}
          </p>
          <div className="alloc-links">
            {a.fallback?.kurucu_site && (
              <a href={a.fallback.kurucu_site} target="_blank" rel="noreferrer">
                {a.kurucu || 'Kurucu'} sitesi →
              </a>
            )}
            {a.fallback?.kap_search && (
              <a href={a.fallback.kap_search} target="_blank" rel="noreferrer">
                KAP bildirim sorgu →
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
