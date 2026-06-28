import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createAlarm, deleteAlarm, listAlarms, toggleAlarm } from '../api'
import type { AlarmCreate } from '../types'
import { num } from '../format'

const emptyForm = (): AlarmCreate => ({ fund_code: '', kind: 'PRICE_ABOVE', threshold: 0 })

export default function Alarms() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['alarms'], queryFn: listAlarms })
  const [form, setForm] = useState<AlarmCreate>(emptyForm())

  const invalidate = () => qc.invalidateQueries({ queryKey: ['alarms'] })
  const addM = useMutation({
    mutationFn: () => createAlarm({ ...form, fund_code: form.fund_code.trim().toUpperCase() }),
    onSuccess: () => {
      setForm(emptyForm())
      invalidate()
    },
  })
  const togM = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => toggleAlarm(id, active),
    onSuccess: invalidate,
  })
  const delM = useMutation({ mutationFn: (id: number) => deleteAlarm(id), onSuccess: invalidate })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (form.fund_code.trim() && form.threshold > 0) addM.mutate()
  }

  return (
    <div className="card">
      <h2>Fiyat Alarmları</h2>

      <form className="alarm-form" onSubmit={submit}>
        <input
          className="input"
          placeholder="Fon kodu"
          value={form.fund_code}
          onChange={(e) => setForm({ ...form, fund_code: e.target.value })}
        />
        <select
          className="input"
          value={form.kind}
          onChange={(e) => setForm({ ...form, kind: e.target.value })}
        >
          <option value="PRICE_ABOVE">NAV ≥</option>
          <option value="PRICE_BELOW">NAV ≤</option>
        </select>
        <input
          className="input"
          type="number"
          step="any"
          placeholder="Eşik"
          value={form.threshold || ''}
          onChange={(e) => setForm({ ...form, threshold: Number(e.target.value) })}
        />
        <button className="btn" type="submit" disabled={addM.isPending}>
          Ekle
        </button>
      </form>

      {q.data && q.data.length > 0 ? (
        <ul className="alarm-list">
          {q.data.map((a) => {
            const status = !a.active ? 'off' : a.triggered ? 'triggered' : 'waiting'
            const statusText = !a.active ? 'Pasif' : a.triggered ? 'Tetiklendi' : 'Bekliyor'
            return (
              <li key={a.id} className={`alarm ${a.active ? '' : 'inactive'}`}>
                <input
                  type="checkbox"
                  checked={a.active}
                  title="Aktif / Pasif"
                  onChange={(e) => togM.mutate({ id: a.id, active: e.target.checked })}
                />
                <div className="alarm-main">
                  <div>
                    <b className="code">{a.code}</b> NAV {a.kind === 'PRICE_ABOVE' ? '≥' : '≤'}{' '}
                    {num(a.threshold, 4)}
                  </div>
                  <div className="muted small">son NAV: {num(a.last_price, 4)}</div>
                </div>
                <span className={`status ${status}`}>{statusText}</span>
                <button className="btn-icon" title="Sil" onClick={() => delM.mutate(a.id)}>
                  ✕
                </button>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="muted">Alarm yok. Bir fonun NAV eşiğini ekleyin.</p>
      )}
    </div>
  )
}
