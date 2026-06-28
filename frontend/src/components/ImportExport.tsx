import { useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { exportPositionsUrl, exportTransactionsUrl, importTransactions } from '../api'
import type { ImportResult } from '../types'

export default function ImportExport({ portfolioId }: { portfolioId: number }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<ImportResult | null>(null)

  const importM = useMutation({
    mutationFn: (file: File) => importTransactions(portfolioId, file),
    onSuccess: (r) => {
      setResult(r)
      qc.invalidateQueries({ queryKey: ['summary', portfolioId] })
      qc.invalidateQueries({ queryKey: ['transactions', portfolioId] })
    },
  })

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) importM.mutate(f)
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div className="card">
      <h2>İçe / Dışa Aktar</h2>
      <div className="ie-row">
        <a className="btn btn-ghost" href={exportTransactionsUrl(portfolioId)}>
          İşlemler CSV ⬇
        </a>
        <a className="btn btn-ghost" href={exportPositionsUrl(portfolioId)}>
          Pozisyonlar CSV ⬇
        </a>
        <label className="btn">
          İşlem CSV içe aktar
          <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={onFile} />
        </label>
      </div>
      <div className="muted small ie-hint">
        Sütunlar: tarih, tip (Alış/Satış), fon, adet, fiyat (ops.), komisyon (ops.), not (ops.)
      </div>

      {importM.isPending && <p className="muted">İçe aktarılıyor…</p>}
      {result && (
        <div className="ie-result">
          <span className="pos">
            <b>{result.imported}</b> işlem eklendi.
          </span>
          {result.errors.length > 0 && (
            <details>
              <summary className="neg">{result.errors.length} satır atlandı</summary>
              <ul>
                {result.errors.slice(0, 20).map((err, i) => (
                  <li key={i} className="small muted">
                    {err}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
