import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFund, getFundPrices, searchFunds } from '../api'
import { num, pctRaw } from '../format'
import NavChart from './NavChart'
import ValorEditor from './ValorEditor'
import FundAllocation from './FundAllocation'

const RETURNS: [string, 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_ytd' | 'ret_1y' | 'ret_3y' | 'ret_5y'][] = [
  ['1A', 'ret_1m'], ['3A', 'ret_3m'], ['6A', 'ret_6m'], ['YBB', 'ret_ytd'],
  ['1Y', 'ret_1y'], ['3Y', 'ret_3y'], ['5Y', 'ret_5y'],
]

export default function FundExplorer({
  onPick,
  openTarget,
}: {
  onPick?: (code: string) => void
  openTarget?: { code: string; n: number }
}) {
  const [term, setTerm] = useState('')
  const [query, setQuery] = useState('')
  const [code, setCode] = useState<string | null>(null)
  const [period, setPeriod] = useState(12)

  // Başka ekrandan bir fon açıldığında (Favorilerim/Enler/Karşılaştırma) onu seç.
  useEffect(() => {
    if (openTarget?.code) {
      setCode(openTarget.code)
      setTerm('')
      setQuery('')
    }
  }, [openTarget])

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

  const clearSearch = () => {
    setTerm('')
    setQuery('')
    setCode(null)
  }

  return (
    <div className="card ac-teal">
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
        <>
          <div className="result-head">
            <span className="muted small">{resultsQ.data.length} sonuç</span>
            <button type="button" className="btn-ghost-sm" onClick={clearSearch}>
              Temizle
            </button>
          </div>
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
        </>
      )}

      {code && (
        <div className="fund-detail">
          <div className="fund-detail-head">
            <div>
              <strong>{detailQ.data?.code ?? code}</strong>
              <div className="muted small">{detailQ.data?.title}</div>
            </div>
            <div className="detail-actions">
              {onPick && (
                <button className="btn btn-ghost" onClick={() => onPick(code)}>
                  İşleme ekle →
                </button>
              )}
              <button className="btn-icon" title="Kapat" onClick={() => setCode(null)}>
                ✕
              </button>
            </div>
          </div>

          <div className="kv">
            <span>Fon türü</span>
            <b>{detailQ.data?.fund_type_desc ?? '—'}</b>
            <span>Kategori</span>
            <b>{detailQ.data?.kind ?? '—'}</b>
            <span>Risk değeri</span>
            <b>{detailQ.data?.risk != null ? `${detailQ.data.risk} / 7` : '—'}</b>
            <span>TEFAS durumu</span>
            <b>
              {detailQ.data?.status == null
                ? '—'
                : detailQ.data.status === '1'
                  ? 'İşleme açık'
                  : detailQ.data.status === '0'
                    ? 'İşleme kapalı'
                    : detailQ.data.status}
            </b>
            <span>Son NAV</span>
            <b>
              {num(detailQ.data?.last_price, 6)}
              {detailQ.data?.last_price != null
                ? detailQ.data?.currency && detailQ.data.currency !== 'TRY'
                  ? ` ${detailQ.data.currency}`
                  : ' ₺'
                : ''}
            </b>
            <span>Son tarih</span>
            <b>{detailQ.data?.last_date ?? '—'}</b>
            <span>Kategori sırası</span>
            <b>
              {detailQ.data?.category_rank != null
                ? `${detailQ.data.category_rank} / ${detailQ.data.category_total ?? '—'}`
                : '—'}
            </b>
            <span>Kayıt</span>
            <b>{detailQ.data?.price_count ?? '—'}</b>
          </div>

          <div className="ret-strip">
            {RETURNS.map(([lbl, key]) => {
              const v = detailQ.data?.[key]
              return (
                <div className="ret-cell" key={lbl}>
                  <span className="ret-lbl">{lbl}</span>
                  <span className={`ret-val ${v == null ? '' : v >= 0 ? 'pos' : 'neg'}`}>
                    {pctRaw(v)}
                  </span>
                </div>
              )
            })}
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

          <FundAllocation code={code} />
        </div>
      )}
    </div>
  )
}
