import { useQuery } from '@tanstack/react-query'
import { getNews, searchFunds } from '../api'
import { pctRaw } from '../format'

const cls = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')

export default function EtfMarket({ onOpenFund }: { onOpenFund?: (code: string) => void }) {
  const etfQ = useQuery({ queryKey: ['etfList'], queryFn: () => searchFunds('', 'ETF', 80) })
  const newsQ = useQuery({ queryKey: ['news', 'etf'], queryFn: () => getNews('etf') })

  const etfs = etfQ.data ?? []

  return (
    <div className="stack">
      <p className="muted small">
        BİST'te işlem gören borsa yatırım fonları (BYF). Koda tıklayınca fon detayına gidersin.
      </p>
      <div className="overview-cols">
        <div className="card ac-teal">
          <h2>ETF'ler ({etfs.length})</h2>
          {etfQ.isLoading ? (
            <p className="muted">Yükleniyor…</p>
          ) : etfs.length === 0 ? (
            <p className="muted">ETF verisi yok.</p>
          ) : (
            <div className="table-wrap etf-table">
              <table>
                <thead>
                  <tr>
                    <th>Fon</th>
                    <th className="r">1A</th>
                    <th className="r">YBB</th>
                    <th className="r">1Y</th>
                  </tr>
                </thead>
                <tbody>
                  {etfs.map((f) => (
                    <tr key={f.code}>
                      <td>
                        {onOpenFund ? (
                          <button
                            type="button"
                            className="link-code"
                            onClick={() => onOpenFund(f.code)}
                          >
                            {f.code}
                          </button>
                        ) : (
                          <b>{f.code}</b>
                        )}
                        <div className="muted small">{f.title}</div>
                      </td>
                      <td className={`r ${cls(f.ret_1m)}`}>{pctRaw(f.ret_1m)}</td>
                      <td className={`r ${cls(f.ret_ytd)}`}>{pctRaw(f.ret_ytd)}</td>
                      <td className={`r ${cls(f.ret_1y)}`}>{pctRaw(f.ret_1y)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card ac-slate">
          <h2>ETF & Piyasa Haberleri</h2>
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
