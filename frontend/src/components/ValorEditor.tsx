import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateValor } from '../api'
import type { FundDetail, ValorUpdate } from '../types'

const numOrNull = (v: number | null | undefined): number | null =>
  v == null || Number.isNaN(v) ? null : v

export default function ValorEditor({ code, detail }: { code: string; detail?: FundDetail }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<ValorUpdate>({})

  useEffect(() => {
    if (detail) {
      setForm({
        buy_valor_days: detail.buy_valor_days ?? undefined,
        sell_valor_days: detail.sell_valor_days ?? undefined,
        redemption_notice_days: detail.redemption_notice_days ?? undefined,
        valor_note: detail.valor_note ?? '',
      })
    }
  }, [detail])

  const saveM = useMutation({
    mutationFn: () =>
      updateValor(code, {
        buy_valor_days: numOrNull(form.buy_valor_days),
        sell_valor_days: numOrNull(form.sell_valor_days),
        redemption_notice_days: numOrNull(form.redemption_notice_days),
        valor_note: form.valor_note || null,
      }),
    onSuccess: () => {
      setOpen(false)
      qc.invalidateQueries({ queryKey: ['fund', code] })
    },
  })

  const num = (v: number | null | undefined) => (v ?? '') as number | ''

  return (
    <div className="valor">
      <div className="valor-head">
        <span className="muted small">Valör / Vade</span>
        <button className="btn-ghost-sm" onClick={() => setOpen((o) => !o)}>
          {open ? 'Kapat' : 'Düzenle'}
        </button>
      </div>

      {detail?.settlement_if_sold_today ? (
        <div className="settle">
          Bugün satarsan paran ≈ <b>{detail.settlement_if_sold_today}</b>
          {detail.sell_valor_days != null && (
            <span className="muted">
              {' '}
              (T+{detail.sell_valor_days}
              {detail.redemption_notice_days ? ` +${detail.redemption_notice_days} ihbar` : ''} iş
              günü)
            </span>
          )}
        </div>
      ) : (
        <div className="muted small">Satış valörü girilmemiş.</div>
      )}
      {detail?.valor_note && <div className="muted small">{detail.valor_note}</div>}

      {open && (
        <div className="valor-form">
          <label>
            Alış valörü
            <input
              className="input"
              type="number"
              value={num(form.buy_valor_days)}
              onChange={(e) =>
                setForm({ ...form, buy_valor_days: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </label>
          <label>
            Satış valörü
            <input
              className="input"
              type="number"
              value={num(form.sell_valor_days)}
              onChange={(e) =>
                setForm({ ...form, sell_valor_days: e.target.value ? Number(e.target.value) : undefined })
              }
            />
          </label>
          <label>
            İhbar (gün)
            <input
              className="input"
              type="number"
              value={num(form.redemption_notice_days)}
              onChange={(e) =>
                setForm({
                  ...form,
                  redemption_notice_days: e.target.value ? Number(e.target.value) : undefined,
                })
              }
            />
          </label>
          <label className="valor-note">
            Not
            <input
              className="input"
              value={form.valor_note ?? ''}
              onChange={(e) => setForm({ ...form, valor_note: e.target.value })}
            />
          </label>
          <button className="btn" onClick={() => saveM.mutate()} disabled={saveM.isPending}>
            Kaydet
          </button>
        </div>
      )}
    </div>
  )
}
