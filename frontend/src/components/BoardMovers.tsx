import { useQuery } from '@tanstack/react-query'
import { getBoardMovers } from '../api'
import { pct } from '../format'
import type { MoverRow } from '../types'

const clsOf = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')

function money(v: number | null, cur: string | null): string {
  if (v == null) return '—'
  const sym = cur === 'USD' ? '$' : '₺'
  const frac = Math.abs(v) > 0 && Math.abs(v) < 1 ? 4 : 2
  return sym + v.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: frac })
}

function compact(v: number | null, cur: string | null): string {
  if (v == null) return '—'
  const sym = cur === 'USD' ? '$' : '₺'
  const a = Math.abs(v)
  const f = (x: number, d: number) => x.toLocaleString('tr-TR', { maximumFractionDigits: d })
  if (a >= 1e9) return `${sym}${f(v / 1e9, 1)} Mr`
  if (a >= 1e6) return `${sym}${f(v / 1e6, 1)} Mn`
  if (a >= 1e3) return `${sym}${f(v / 1e3, 0)} B`
  return `${sym}${f(v, 0)}`
}

function Table({
  title,
  accent,
  rows,
  currency,
  metric,
}: {
  title: string
  accent: string
  rows: MoverRow[]
  currency: string | null
  metric: 'change' | 'volume'
}) {
  return (
    <div className={`card ${accent}`}>
      <h3 className="movers-title">{title}</h3>
      {rows.length === 0 ? (
        <p className="muted small">Veri yok.</p>
      ) : (
        <table className="movers-table">
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.code}>
                <td className="movers-rank">{i + 1}</td>
                <td className="movers-code" title={r.name ?? ''}>
                  {r.code}
                </td>
                <td className="movers-price">{money(r.price, currency)}</td>
                {metric === 'volume' ? (
                  <td className="movers-vol">{compact(r.volume, currency)}</td>
                ) : (
                  <td className={`movers-chg ${clsOf(r.change)}`}>{pct(r.change)}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function BoardMovers({ board }: { board: string }) {
  const q = useQuery({
    queryKey: ['boardMovers', board],
    queryFn: () => getBoardMovers(board),
    refetchInterval: 180_000,
    refetchIntervalInBackground: true,
  })
  const d = q.data
  const cur = d?.currency ?? null

  return (
    <div className="stack">
      <h2 className="movers-head">
        Günün Enleri{' '}
        {d && <span className="muted small">· {d.count} kalem taranıyor</span>}
      </h2>
      {q.isLoading && <p className="muted">Yükleniyor… (hisse taraması birkaç saniye sürebilir)</p>}
      {d && (
        <div className="movers-grid">
          <Table
            title="📈 En Çok Yükselen"
            accent="ac-green"
            rows={d.gainers}
            currency={cur}
            metric="change"
          />
          <Table
            title="📉 En Çok Düşen"
            accent="ac-red"
            rows={d.losers}
            currency={cur}
            metric="change"
          />
          <Table
            title="🔥 En Çok İşlem Gören"
            accent="ac-blue"
            rows={d.most_traded}
            currency={cur}
            metric="volume"
          />
        </div>
      )}
    </div>
  )
}
