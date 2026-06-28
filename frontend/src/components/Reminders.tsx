import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createReminder, deleteReminder, listReminders, setReminderDone } from '../api'
import type { ReminderCreate } from '../types'

const today = () => new Date().toISOString().slice(0, 10)

function daysLeft(dateStr: string): number {
  const d = new Date(dateStr + 'T00:00:00').getTime()
  const t = new Date(today() + 'T00:00:00').getTime()
  return Math.round((d - t) / 86_400_000)
}

const emptyForm = (): ReminderCreate => ({ title: '', date: today(), fund_code: '' })

export default function Reminders() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['reminders'], queryFn: listReminders })
  const [form, setForm] = useState<ReminderCreate>(emptyForm())

  const invalidate = () => qc.invalidateQueries({ queryKey: ['reminders'] })
  const addM = useMutation({
    mutationFn: () =>
      createReminder({ ...form, fund_code: form.fund_code?.trim().toUpperCase() || undefined }),
    onSuccess: () => {
      setForm(emptyForm())
      invalidate()
    },
  })
  const doneM = useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) => setReminderDone(id, done),
    onSuccess: invalidate,
  })
  const delM = useMutation({ mutationFn: (id: number) => deleteReminder(id), onSuccess: invalidate })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (form.title.trim()) addM.mutate()
  }

  return (
    <div className="card">
      <h2>Vade &amp; Hatırlatmalar</h2>

      <form className="reminder-form" onSubmit={submit}>
        <input
          className="input"
          placeholder="Başlık (örn. AAS ihbarlı çıkış)"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <div className="row">
          <input
            className="input"
            type="date"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
          <input
            className="input"
            placeholder="Fon (ops.)"
            value={form.fund_code ?? ''}
            onChange={(e) => setForm({ ...form, fund_code: e.target.value })}
          />
          <button className="btn" type="submit" disabled={addM.isPending}>
            Ekle
          </button>
        </div>
      </form>

      {q.data && q.data.length > 0 ? (
        <ul className="reminder-list">
          {q.data.map((r) => {
            const dl = daysLeft(r.date)
            const overdue = !r.done && dl < 0
            const urgent = !r.done && dl >= 0 && dl <= 7
            return (
              <li key={r.id} className={`reminder ${r.done ? 'done' : ''}`}>
                <input
                  type="checkbox"
                  checked={r.done}
                  onChange={(e) => doneM.mutate({ id: r.id, done: e.target.checked })}
                />
                <div className="reminder-main">
                  <div className="reminder-title">
                    {r.code && <b className="code">{r.code}</b>} {r.title}
                  </div>
                  <div className="muted small">{r.date}</div>
                </div>
                <span className={`days ${overdue ? 'neg' : urgent ? 'warn' : ''}`}>
                  {r.done
                    ? '✓'
                    : overdue
                      ? `${-dl}g geçti`
                      : dl === 0
                        ? 'bugün'
                        : `${dl}g kaldı`}
                </span>
                <button className="btn-icon" title="Sil" onClick={() => delM.mutate(r.id)}>
                  ✕
                </button>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="muted">Hatırlatma yok. Vade/çıkış tarihlerini buraya ekleyin.</p>
      )}
    </div>
  )
}
