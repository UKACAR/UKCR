import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFundMonthlyReturns } from '../api'

const MONTHS = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']

// Ondalık getiriyi yüzde metnine çevir (0.0234 -> "2,3")
const fmt = (v: number | null | undefined) =>
  v == null
    ? ''
    : (v * 100).toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

// Pozitif yeşil / negatif kırmızı; yoğunluk büyüklükle artar (ısı haritası).
const bg = (v: number | null | undefined): string | undefined => {
  if (v == null) return undefined
  const a = Math.min(0.85, 0.12 + Math.abs(v) * 4)
  return v >= 0 ? `rgba(29, 158, 117, ${a})` : `rgba(216, 69, 58, ${a})`
}

export default function MonthlyReturns({ code }: { code: string }) {
  const [real, setReal] = useState(false)
  const q = useQuery({
    queryKey: ['monthly', code, real],
    queryFn: () => getFundMonthlyReturns(code, 3, real),
  })

  const rows = q.data?.rows ?? []

  return (
    <div className="monthly">
      <div className="monthly-head">
        <div className="chart-caption muted small">
          Aylık getiri (%) — son {rows.length || 3} yıl
          {real ? ' · reel (TÜFE’den arındırılmış)' : ''}
        </div>
        <div className="seg seg-sm">
          <button
            type="button"
            className={`seg-btn ${real ? '' : 'active'}`}
            onClick={() => setReal(false)}
          >
            Nominal
          </button>
          <button
            type="button"
            className={`seg-btn ${real ? 'active' : ''}`}
            onClick={() => setReal(true)}
          >
            Reel
          </button>
        </div>
      </div>

      {q.isLoading ? (
        <p className="muted small">Aylık getiriler yükleniyor…</p>
      ) : rows.length === 0 ? (
        <p className="muted small">Aylık getiri verisi yok.</p>
      ) : (
      <div className="table-wrap">
        <table className="monthly-table">
          <thead>
            <tr>
              <th>Yıl</th>
              {MONTHS.map((m) => (
                <th key={m} className="r">
                  {m}
                </th>
              ))}
              <th className="r">Yıl</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.year}>
                <td>
                  <b>{r.year}</b>
                </td>
                {r.months.map((v, i) => (
                  <td key={i} className="r mr-cell" style={{ background: bg(v) }}>
                    {fmt(v)}
                  </td>
                ))}
                <td className="r mr-cell mr-total" style={{ background: bg(r.total) }}>
                  <b>{fmt(r.total)}</b>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}
