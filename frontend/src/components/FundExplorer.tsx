import { useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFund, getFundPrices, searchFunds } from '../api'
import { num, pctRaw } from '../format'
import NavChart from './NavChart'
import ValorEditor from './ValorEditor'

export default function FundExplorer({ onPick }: { onPick?: (code: string) => void }) {
  const [term, setTerm] = useState('')
  const [query, setQuery] = useState('')
  const [code, setCode] = useState<string | null>(null)
  const [period, setPeriod] = useState(12)

  const resultsQ = useQuery({
    queryKey: ['funds', query],
    queryFn: () => searchFunds(query, undefined, 25),
    enabled: query.length > 0,
  })
  const detailQ = useQuery({
    queryKey: ['fund', code],
    queryFn: () => getFund(code as string),
    enabled: !!code,
  })
  const pricesQ = useQuery({
    queryKey: ['prices', code, period],
    queryFn: () => getFundPrices(code as string, period),
    enabled: !!code,
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setQuery(term.trim())
  }

  return (
    <div className="card">
      <h2>Fon Keşfi</h2>
      <form className="row" onSubmit={submit}>
        <input
          className="input"
          placeholder="Fon kodu veya ad (örn. ALTIN, AAS)"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
        <button className="btn" type="submit">
          Ara
        </button>
      </form>

      {resultsQ.isFetching && <p className="muted">Aranıyor…</p>}
      {resultsQ.data && resultsQ.data.length === 0 && <p className="muted">Sonuç yok.</p>}
      {resultsQ.data && resultsQ.data.length > 0 && (
        <ul className="result-list">
          {resultsQ.data.map((f) => (
            <li key={f.code}>
              <button
                className={`result ${code === f.code ? 'active' : ''}`}
                onClick={() => setCode(f.code)}
              >
                <span className="code">{f.code}</span>
                <span className="title">{f.title}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {code && (
        <div className="fund-detail">
          <div className="fund-detail-head">
            <div>
              <strong>{detailQ.data?.code ?? code}</strong>
              <div className="muted small">{detailQ.data?.title}</div>
            </div>
            {onPick && (
              <button className="btn btn-ghost" onClick={() => onPick(code)}>
                İşleme ekle →
              </button>
            )}
          </div>

          <div className="kv">
            <span>Son NAV</span>
            <b>{num(detailQ.data?.last_price, 6)}</b>
            <span>Son tarih</span>
            <b>{detailQ.data?.last_date ?? '—'}</b>
            <span>1Y getiri</span>
            <b>{pctRaw(detailQ.data?.ret_1y)}</b>
            <span>Kayıt</span>
            <b>{detailQ.data?.price_count ?? '—'}</b>
          </div>

          <ValorEditor code={code} detail={detailQ.data} />

          <div className="period-row">
            {[3, 12, 36, 60].map((p) => (
              <button
                key={p}
                className={`chip ${period === p ? 'active' : ''}`}
                onClick={() => setPeriod(p)}
              >
                {p === 3 ? '3A' : `${p / 12}Y`}
              </button>
            ))}
          </div>

          {pricesQ.isFetching ? (
            <p className="muted">Grafik yükleniyor…</p>
          ) : (
            <NavChart data={pricesQ.data ?? []} />
          )}
        </div>
      )}
    </div>
  )
}
