import { useQuery } from '@tanstack/react-query'
import { getPortfolioPerformance } from '../api'
import { pct, tl } from '../format'

const fmtDate = (iso: string) => {
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

const RETURN_ROWS: [string, 'week' | 'm1' | 'm3' | 'm6' | 'y1'][] = [
  ['Haftalık', 'week'],
  ['1 Ay', 'm1'],
  ['3 Ay', 'm3'],
  ['6 Ay', 'm6'],
  ['1 Yıl', 'y1'],
]

const sgn = (v: number) => (v >= 0 ? 'pos' : 'neg')

export default function PortfolioPerformance({ pid }: { pid: number }) {
  const q = useQuery({
    queryKey: ['performance', pid],
    queryFn: () => getPortfolioPerformance(pid),
  })

  if (q.isLoading) return <div className="card ac-purple muted">Performans hesaplanıyor…</div>
  const data = q.data
  if (!data || data.daily.length === 0) {
    return (
      <div className="card ac-purple">
        <h2>Günlük Kâr/Zarar</h2>
        <p className="muted">
          Bu portföyde işlem yok. Günlük kâr/zarar tablosu ve dönem getirileri için işlem ekleyin
          (ya da yukarıdan işlemi olan bir portföy seçin).
        </p>
      </div>
    )
  }

  const rows = [...data.daily].reverse() // en yeni üstte

  return (
    <div className="card ac-purple">
      <div className="perf-head">
        <h2>Günlük Kâr/Zarar</h2>
        <span className="muted small">Güncel dağılımın son 6 aydaki performansı</span>
      </div>

      <div className="perf-grid">
        <div className="perf-table table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tarih</th>
                <th className="r">Değer</th>
                <th className="r">Günlük K/Z</th>
                <th className="r">%</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.date}>
                  <td>{fmtDate(d.date)}</td>
                  <td className="r">{tl(d.value)}</td>
                  <td className={`r ${sgn(d.pl)}`}>{tl(d.pl)}</td>
                  <td className={`r ${sgn(d.pl_pct)}`}>{pct(d.pl_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="perf-returns">
          <div className="perf-returns-title">Dönem Getirisi (TL)</div>
          <ul className="perf-returns-list">
            {RETURN_ROWS.map(([label, key]) => {
              const v = data.returns_tl[key]
              return (
                <li key={key}>
                  <span className="prl-label">{label}</span>
                  <span className={`prl-val ${v == null ? 'muted' : sgn(v)}`}>
                    {v == null ? '—' : tl(v)}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </div>
  )
}
