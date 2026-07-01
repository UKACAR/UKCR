import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAiReport, refreshAiReport } from '../api'
import type { Sentiment } from '../types'

const META: Record<Sentiment, { cls: string; icon: string; label: string }> = {
  pozitif: { cls: 'sent-pos', icon: '▲', label: 'Pozitif' },
  negatif: { cls: 'sent-neg', icon: '▼', label: 'Negatif' },
  karışık: { cls: 'sent-mix', icon: '◆', label: 'Karışık' },
  nötr: { cls: 'sent-neu', icon: '●', label: 'Nötr' },
}
const meta = (s: Sentiment) => META[s] ?? META['nötr']

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('tr-TR', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function AiAnalysis() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['aiReport'], queryFn: getAiReport })
  const refresh = useMutation({
    mutationFn: refreshAiReport,
    onSuccess: (data) => qc.setQueryData(['aiReport'], data),
  })

  const d = q.data
  const r = d?.report

  return (
    <div className="stack">
      <div className="card ac-purple">
        <div className="ai-head">
          <div>
            <h2 className="ai-title">🤖 AI Piyasa Analizi</h2>
            {d && (
              <div className="muted small">
                {fmtTime(d.generated_at)} ·{' '}
                {r?.mode === 'ai' ? (
                  <span className="ai-badge ai-badge-ai">AI · {r?.model ?? 'Claude'}</span>
                ) : (
                  <span className="ai-badge ai-badge-rule">Kural bazlı (veri temelli)</span>
                )}
              </div>
            )}
          </div>
          <button
            className="btn btn-ghost"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            {refresh.isPending ? 'Üretiliyor…' : '↻ Yenile'}
          </button>
        </div>

        {q.isLoading && <p className="muted">Rapor yükleniyor…</p>}
        {d?.note && <p className="ai-note">⚠ {d.note}</p>}

        {r && (
          <>
            <div className={`ai-summary ${meta(r.genel_hava).cls}`}>
              <span className="ai-sent-chip">
                {meta(r.genel_hava).icon} Genel hava: {meta(r.genel_hava).label}
              </span>
              <p>{r.ozet}</p>
            </div>

            <div className="ai-grid">
              {r.bolumler.map((b, i) => (
                <div key={i} className={`ai-section ${meta(b.hava).cls}`}>
                  <div className="ai-section-head">
                    <b>{b.baslik}</b>
                    <span className="ai-sent-tag">{meta(b.hava).icon}</span>
                  </div>
                  <p>{b.yorum}</p>
                </div>
              ))}
            </div>

            <div className="overview-cols">
              <div className="card ac-blue">
                <h3>📰 Öne Çıkan Haberler</h3>
                {r.one_cikan_haberler.length === 0 ? (
                  <p className="muted small">—</p>
                ) : (
                  <ul className="ai-list">
                    {r.one_cikan_haberler.map((h, i) => (
                      <li key={i}>{h}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="card ac-red">
                <h3>⚠ Dikkat / Riskler</h3>
                {r.riskler.length === 0 ? (
                  <p className="muted small">—</p>
                ) : (
                  <ul className="ai-list">
                    {r.riskler.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div className="ai-close">
              <b>Değerlendirme.</b> {r.kapanis}
            </div>

            <p className="muted small">
              Bu içerik piyasa verilerinin bir sentezidir, <b>yatırım tavsiyesi değildir</b>.
              {r.mode === 'kural' &&
                ' AI yorumu için backend/.env içine ANTHROPIC_API_KEY ekleyin.'}{' '}
              Her gün otomatik yenilenir.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
