import { useQuery } from '@tanstack/react-query'
import { getFundHoldings } from '../api'

const fmtDate = (iso?: string | null) => (iso ? iso.split('-').reverse().join('.') : '')
const pctCls = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')
const chg = (v?: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`)

export default function FundHoldings({ code }: { code: string }) {
  const q = useQuery({
    queryKey: ['holdings', code],
    queryFn: () => getFundHoldings(code),
    refetchInterval: (query) => (query.state.data?.index_holdings ? 60_000 : false),
  })
  const d = q.data
  if (q.isLoading) return <p className="muted small">Hisse dökümü yükleniyor…</p>
  if (!d) return null

  return (
    <div className="holdings">
      <div className="alloc-head">
        <h4>Hisse Detayı</h4>
        {d.parsed && d.as_of && <span className="muted small">Aylık rapor · {fmtDate(d.as_of)}</span>}
      </div>

      {d.parsed && d.holdings.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="holdings-table">
              <thead>
                <tr>
                  <th>Kod</th>
                  <th>Ad</th>
                  <th className="r">Portföydeki %</th>
                </tr>
              </thead>
              <tbody>
                {d.holdings.map((h, i) => (
                  <tr key={h.code + i}>
                    <td>
                      <b>{h.code}</b>
                      {h.foreign && <span className="hold-badge">yabancı</span>}
                    </td>
                    <td className="muted small">{h.name}</td>
                    <td className="r">%{h.pct.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            Kaynak: fonun resmî aylık portföy raporu ({d.count} kalem). Oranlar rapor tarihine aittir.
          </p>
        </>
      ) : d.index_holdings && d.index_holdings.length > 0 ? (
        <>
          <p className="muted small">
            {d.note} Aşağıdaki <b>{d.index_name}</b> hisseleri <b>gösterge</b> içeriktir (fonun
            birebir portföyü değildir); canlı günlük değişimle:
          </p>
          <div className="holdings-chips">
            {d.index_holdings.map((h) => (
              <span key={h.code} className="hold-chip" title={h.name}>
                {h.code} <b className={pctCls(h.change)}>{chg(h.change)}</b>
              </span>
            ))}
          </div>
        </>
      ) : (
        <p className="muted small">{d.note}</p>
      )}

      <div className="alloc-links">
        {d.report_url && (
          <a href={d.report_url} target="_blank" rel="noreferrer">
            Resmî portföy raporu →
          </a>
        )}
        {d.source_url && (
          <a href={d.source_url} target="_blank" rel="noreferrer">
            Kurucu sayfası →
          </a>
        )}
      </div>
    </div>
  )
}
