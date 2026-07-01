import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addTransaction,
  createPortfolio,
  deleteTransaction,
  getSummary,
  listPortfolios,
  listTransactions,
} from '../api'
import type { Summary, TransactionCreate } from '../types'
import { num, pct, tl } from '../format'
import ImportExport from './ImportExport'

const STORAGE_KEY = 'ukcr.portfolio.selectedId'

function loadSelectedId(): number | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    const n = v ? Number(v) : NaN
    return Number.isFinite(n) ? n : null
  } catch {
    return null
  }
}

const today = () => new Date().toISOString().slice(0, 10)
const emptyForm = (): TransactionCreate => ({
  fund_code: '',
  type: 'BUY',
  quantity: 0,
  price: undefined,
  trade_date: today(),
  fee: 0,
})

export default function PortfolioPanel({ prefillCode }: { prefillCode?: string }) {
  const qc = useQueryClient()
  const portfoliosQ = useQuery({ queryKey: ['portfolios'], queryFn: listPortfolios })

  const [selectedId, setSelectedId] = useState<number | null>(loadSelectedId)
  const portfolios = portfoliosQ.data
  // Geçerli seçim: kaydedilen id listede varsa o, yoksa ilk portföy.
  const pid =
    selectedId != null && portfolios?.some((p) => p.id === selectedId)
      ? selectedId
      : portfolios?.[0]?.id ?? null

  // Son seçilen portföyü hatırla → uygulama açılınca o gelsin.
  useEffect(() => {
    if (selectedId != null) {
      try {
        localStorage.setItem(STORAGE_KEY, String(selectedId))
      } catch {
        /* yoksay */
      }
    }
  }, [selectedId])

  const [newName, setNewName] = useState('')
  const createM = useMutation({
    mutationFn: () => createPortfolio(newName.trim() || 'Portföyüm'),
    onSuccess: (p) => {
      setNewName('')
      setSelectedId(p.id)
      qc.invalidateQueries({ queryKey: ['portfolios'] })
    },
  })

  const summaryQ = useQuery({
    queryKey: ['summary', pid],
    queryFn: () => getSummary(pid as number),
    enabled: pid != null,
  })
  const txQ = useQuery({
    queryKey: ['transactions', pid],
    queryFn: () => listTransactions(pid as number),
    enabled: pid != null,
  })

  const [form, setForm] = useState<TransactionCreate>(emptyForm())
  useEffect(() => {
    if (prefillCode) setForm((f) => ({ ...f, fund_code: prefillCode }))
  }, [prefillCode])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['summary', pid] })
    qc.invalidateQueries({ queryKey: ['transactions', pid] })
  }

  const addM = useMutation({
    mutationFn: () =>
      addTransaction(pid as number, {
        ...form,
        fund_code: form.fund_code.trim().toUpperCase(),
        price: form.price || undefined,
        fee: form.fee || 0,
      }),
    onSuccess: () => {
      setForm((f) => ({ ...emptyForm(), fund_code: f.fund_code }))
      invalidate()
    },
  })
  const delM = useMutation({
    mutationFn: (txId: number) => deleteTransaction(pid as number, txId),
    onSuccess: invalidate,
  })

  const submitTx = (e: FormEvent) => {
    e.preventDefault()
    if (pid == null || !form.fund_code.trim() || form.quantity <= 0) return
    addM.mutate()
  }

  return (
    <div className="stack">
      <div className="card ac-blue">
        <div className="portfolio-bar">
          <select
            className="input"
            value={pid ?? ''}
            onChange={(e) => setSelectedId(Number(e.target.value))}
          >
            {portfoliosQ.data?.length ? (
              portfoliosQ.data.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))
            ) : (
              <option value="">Portföy yok</option>
            )}
          </select>
          <input
            className="input"
            placeholder="Yeni portföy adı"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button className="btn" onClick={() => createM.mutate()} disabled={createM.isPending}>
            + Oluştur
          </button>
        </div>
      </div>

      {pid != null && <SummaryCards data={summaryQ.data} loading={summaryQ.isLoading} />}

      <div className="card ac-green">
        <h2>İşlem Ekle</h2>
        <form className="tx-form" onSubmit={submitTx}>
          <input
            className="input"
            placeholder="Fon kodu"
            value={form.fund_code}
            onChange={(e) => setForm({ ...form, fund_code: e.target.value })}
          />
          <select
            className="input"
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value as 'BUY' | 'SELL' })}
          >
            <option value="BUY">Alış</option>
            <option value="SELL">Satış</option>
          </select>
          <input
            className="input"
            type="number"
            step="any"
            placeholder="Adet"
            value={form.quantity || ''}
            onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
          />
          <input
            className="input"
            type="date"
            value={form.trade_date}
            onChange={(e) => setForm({ ...form, trade_date: e.target.value })}
          />
          <input
            className="input"
            type="number"
            step="any"
            placeholder="Fiyat (boş = o günün NAV'ı)"
            value={form.price ?? ''}
            onChange={(e) =>
              setForm({ ...form, price: e.target.value ? Number(e.target.value) : undefined })
            }
          />
          <button className="btn" type="submit" disabled={addM.isPending}>
            Ekle
          </button>
        </form>
        {addM.isError && <p className="error">İşlem eklenemedi (fon kodu/tarih kontrol edin).</p>}
      </div>

      <div className="card ac-teal">
        <h2>Pozisyonlar</h2>
        {summaryQ.data && summaryQ.data.positions.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fon</th>
                  <th className="r">Adet</th>
                  <th className="r">Ort. Maliyet</th>
                  <th className="r">Son NAV</th>
                  <th className="r">Değer</th>
                  <th className="r">Gerç.olmayan K/Z</th>
                  <th className="r">Stopaj</th>
                </tr>
              </thead>
              <tbody>
                {summaryQ.data.positions.map((p) => (
                  <tr key={p.code}>
                    <td>
                      <b>{p.code}</b>
                      <div className="muted small">{p.title}</div>
                    </td>
                    <td className="r">{num(p.units, 2)}</td>
                    <td className="r">{num(p.avg_cost, 4)}</td>
                    <td className="r">{num(p.last_price, 4)}</td>
                    <td className="r">{tl(p.market_value)}</td>
                    <td className={`r ${p.unrealized_pl >= 0 ? 'pos' : 'neg'}`}>
                      {tl(p.unrealized_pl)}
                    </td>
                    <td className="r">{tl(p.estimated_stopaj)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">Henüz pozisyon yok. Yukarıdan işlem ekleyin.</p>
        )}
      </div>

      <div className="card ac-slate">
        <h2>İşlemler</h2>
        {txQ.data && txQ.data.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tarih</th>
                  <th>Fon</th>
                  <th>Tip</th>
                  <th className="r">Adet</th>
                  <th className="r">Fiyat</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {txQ.data.map((t) => (
                  <tr key={t.id}>
                    <td>{t.trade_date}</td>
                    <td>{t.code}</td>
                    <td>
                      <span className={`tag ${t.type === 'BUY' ? 'buy' : 'sell'}`}>
                        {t.type === 'BUY' ? 'Alış' : 'Satış'}
                      </span>
                    </td>
                    <td className="r">{num(t.quantity, 2)}</td>
                    <td className="r">{num(t.price, 4)}</td>
                    <td className="r">
                      <button
                        className="btn-icon"
                        title="Sil"
                        onClick={() => delM.mutate(t.id)}
                        disabled={delM.isPending}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">İşlem yok.</p>
        )}
      </div>

      {pid != null && <ImportExport portfolioId={pid} />}
    </div>
  )
}

function SummaryCards({ data, loading }: { data?: Summary; loading: boolean }) {
  if (loading) return <div className="card muted">Özet yükleniyor…</div>
  if (!data) return null

  const plClass = data.total_pl >= 0 ? 'pos' : 'neg'
  return (
    <div className="cards">
      <Metric label="Güncel Değer" value={tl(data.current_value)} accent="var(--ac-blue)" />
      <Metric label="Toplam K/Z" value={tl(data.total_pl)} cls={plClass} accent="var(--ac-green)" />
      <Metric
        label="Kümülatif Getiri"
        value={pct(data.simple_return)}
        cls={plClass}
        accent="var(--ac-teal)"
      />
      <Metric label="XIRR (yıllık)" value={pct(data.xirr)} accent="var(--ac-purple)" />
      <Metric
        label="Reel Getiri"
        value={data.real_return == null ? 'EVDS gerekli' : pct(data.real_return)}
        muted={data.real_return == null}
        accent="var(--ac-slate)"
      />
      <Metric label="Tahmini Stopaj" value={tl(data.estimated_stopaj)} accent="var(--ac-amber)" />
      <Metric label="Net Değer (vergi −)" value={tl(data.net_value)} accent="var(--ac-blue)" />
    </div>
  )
}

function Metric({
  label,
  value,
  cls,
  muted,
  accent,
}: {
  label: string
  value: string
  cls?: string
  muted?: boolean
  accent?: string
}) {
  return (
    <div className="metric" style={accent ? { borderTopColor: accent } : undefined}>
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${cls ?? ''} ${muted ? 'muted' : ''}`}>{value}</div>
    </div>
  )
}
