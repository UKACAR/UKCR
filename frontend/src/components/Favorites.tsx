import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addFavorite, deleteFavorite, listFavorites, searchFunds } from '../api'
import type { FavoriteCreate } from '../types'
import { num, pct, tl } from '../format'

type FavType = 'FUND' | 'STOCK'

const cls = (v?: number | null) => (v == null ? '' : v >= 0 ? 'pos' : 'neg')

export default function Favorites() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['favorites'], queryFn: listFavorites })

  const [type, setType] = useState<FavType>('FUND')
  const [input, setInput] = useState('')
  const [err, setErr] = useState('')

  const invalidate = () => qc.invalidateQueries({ queryKey: ['favorites'] })
  const addM = useMutation({
    mutationFn: (body: FavoriteCreate) => addFavorite(body),
    onSuccess: () => {
      setInput('')
      setErr('')
      invalidate()
    },
    onError: () => setErr(type === 'FUND' ? 'Fon bulunamadı' : 'Hisse bulunamadı (örn. THYAO, GARAN)'),
  })
  const delM = useMutation({ mutationFn: (id: number) => deleteFavorite(id), onSuccess: invalidate })

  const term = input.trim()
  const suggestQ = useQuery({
    queryKey: ['favFundSuggest', term],
    queryFn: () => searchFunds(term, undefined, 8),
    enabled: type === 'FUND' && term.length >= 2,
  })
  const showSuggest = type === 'FUND' && term.length >= 2 && (suggestQ.data?.length ?? 0) > 0

  const add = (code: string) => {
    const c = code.trim().toUpperCase()
    if (!c) return
    addM.mutate({ type, code: c })
  }
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    add(input)
  }

  const favs = q.data ?? []
  const funds = favs.filter((f) => f.type === 'FUND')
  const stocks = favs.filter((f) => f.type === 'STOCK')

  return (
    <div className="card ac-amber">
      <h2>Favorilerim</h2>
      <p className="muted small">
        Fon, BES, ETF ve BİST hisselerini favorile; anlık fiyat ve günlük değişimleriyle tek
        ekranda takip et. (Hisse verisi ~15 dk gecikmeli.)
      </p>

      <form className="fav-form" onSubmit={onSubmit} autoComplete="off">
        <div className="seg">
          <button
            type="button"
            className={`seg-btn ${type === 'FUND' ? 'active' : ''}`}
            onClick={() => {
              setType('FUND')
              setErr('')
            }}
          >
            Fon / BES / ETF
          </button>
          <button
            type="button"
            className={`seg-btn ${type === 'STOCK' ? 'active' : ''}`}
            onClick={() => {
              setType('STOCK')
              setErr('')
            }}
          >
            Hisse
          </button>
        </div>

        <div className="suggest-wrap">
          <input
            className="input"
            placeholder={
              type === 'FUND' ? 'Fon kodu veya adı yaz (örn. ALTIN, AAS)' : 'Hisse kodu (örn. THYAO, GARAN)'
            }
            value={input}
            onChange={(e) => {
              setInput(e.target.value)
              setErr('')
            }}
          />
          {showSuggest && (
            <ul className="suggest-list">
              {suggestQ.data!.map((f) => (
                <li key={f.code}>
                  <button
                    type="button"
                    className="suggest-item"
                    onMouseDown={(e) => {
                      e.preventDefault()
                      add(f.code)
                    }}
                  >
                    <span className="code">{f.code}</span>
                    <span className="title">{f.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <button className="btn" type="submit" disabled={addM.isPending}>
          + Favoriye ekle
        </button>
      </form>

      {err && <p className="form-err">{err}</p>}

      {favs.length === 0 ? (
        <p className="muted">
          Henüz favori yok. Yukarıdan fon ya da hisse ekleyerek izleme listeni oluştur.
        </p>
      ) : (
        <>
          {funds.length > 0 && (
            <FavGroup
              title="Fonlar"
              rows={funds}
              priceFmt={(v) => num(v, 4)}
              onDelete={(id) => delM.mutate(id)}
            />
          )}
          {stocks.length > 0 && (
            <FavGroup
              title="Hisseler"
              rows={stocks}
              priceFmt={(v) => tl(v)}
              onDelete={(id) => delM.mutate(id)}
            />
          )}
        </>
      )}
    </div>
  )
}

function FavGroup({
  title,
  rows,
  priceFmt,
  onDelete,
}: {
  title: string
  rows: import('../types').Favorite[]
  priceFmt: (v: number | null | undefined) => string
  onDelete: (id: number) => void
}) {
  return (
    <div className="fav-group">
      <div className="fav-group-title">{title}</div>
      <ul className="fav-list">
        {rows.map((f) => (
          <li key={f.id} className="fav">
            <div className="fav-main">
              <b className="code">{f.code}</b>
              <span className="muted small fav-title">{f.title}</span>
            </div>
            <div className="fav-price">
              <div className="fav-last">{priceFmt(f.last_price)}</div>
              <div className={`fav-chg ${cls(f.change)}`}>{pct(f.change)}</div>
            </div>
            <button className="btn-icon" title="Favoriden çıkar" onClick={() => onDelete(f.id)}>
              ✕
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
