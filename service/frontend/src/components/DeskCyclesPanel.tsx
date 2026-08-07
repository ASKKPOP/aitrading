import { useCallback, useEffect, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { fmtUsd, pnlColor } from '../pages/tradeShared'

// AI Analysis — the desk's 30-minute cycles, opened from under the account
// tiles on the automation page.
//
// Nothing here is newly generated. Sooppiy AI already analyses every RUN on
// its interval and journals the result; /automation/ai-analysis folds that
// journal onto a fixed 30-minute grid. What this panel adds is the desk's
// WRITTEN report, which the runs grid only ever rendered as "buy conf 0.72".

type RunCell = {
  run_id: number; symbol: string; market: string
  action: string | null; confidence: number | null; conviction: number | null
  report: string | null
  skips: { stage: string; reason: string; count: number }[]
  transitions: { from: string | null; to: string | null; reason: string | null }[]
  decisions: number
  realized: number | null; realized_delta: number; unrealized: number | null
  peak: number | null; preservation: number | null
  status: string | null; status_reason: string | null
}

type Cycle = {
  start: string; end: string; quiet: boolean
  realized: number | null; unrealized: number | null; realized_delta: number
  decisions: number; skips: number; opened: number; closed: number
  runs_active: number; runs: RunCell[]
}

const CYCLES = 12   // 6 hours of grid — one screen's worth of scrollback

// Cycle stamps are UTC; render them in the reader's own clock and in the
// app's chosen language, not the browser's.
const hhmm = (iso: string, lang: string) =>
  new Date(iso).toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit', hour12: false })

const dayLabel = (iso: string, lang: string) =>
  new Date(iso).toLocaleDateString(lang, { month: 'short', day: 'numeric' })

export function DeskCyclesPanel({ token, onClose }: { token: string | null; onClose: () => void }) {
  const { language } = useLanguage()
  const [cycles, setCycles] = useState<Cycle[] | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const T = {
    title: tr(language, { ko: 'AI 분석 (30분 주기)', en: 'AI Analysis (30-min cycles)', ja: 'AI分析（30分サイクル）', th: 'การวิเคราะห์ AI (รอบ 30 นาที)', vi: 'Phân tích AI (chu kỳ 30 phút)', id: 'Analisis AI (siklus 30 menit)' }),
    subtitle: tr(language, {
      ko: 'Sooppiy AI가 각 RUN을 분석하며 남긴 기록을 30분 단위로 묶어 보여줍니다 — 로그인하지 않은 시간도 그대로 남습니다.',
      en: "What Sooppiy AI recorded while analysing each RUN, folded into 30-minute cycles — including the hours you were not signed in.",
      ja: 'Sooppiy AI が各 RUN を分析した記録を30分単位でまとめたものです — ログインしていない時間帯も残ります。',
      th: 'บันทึกที่ Sooppiy AI ทำไว้ขณะวิเคราะห์แต่ละ RUN จัดกลุ่มเป็นรอบละ 30 นาที — รวมช่วงที่คุณไม่ได้ล็อกอินด้วย',
      vi: 'Những gì Sooppiy AI ghi lại khi phân tích từng RUN, gộp theo chu kỳ 30 phút — kể cả lúc bạn không đăng nhập.',
      id: 'Catatan Sooppiy AI saat menganalisis setiap RUN, dikelompokkan per siklus 30 menit — termasuk saat Anda tidak masuk.',
    }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    loading: tr(language, { ko: '불러오는 중…', en: 'Loading…', ja: '読み込み中…', th: 'กำลังโหลด…', vi: 'Đang tải…', id: 'Memuat…' }),
    empty: tr(language, {
      ko: '아직 분석 기록이 없습니다. RUN이 시작되면 30분마다 이 목록이 채워집니다.',
      en: 'No analysis yet. Once a RUN is live this list fills in every 30 minutes.',
      ja: 'まだ分析記録がありません。RUN が動き出すと30分ごとにこの一覧が埋まります。',
      th: 'ยังไม่มีบันทึกการวิเคราะห์ เมื่อ RUN เริ่มทำงาน รายการนี้จะถูกเติมทุก 30 นาที',
      vi: 'Chưa có phân tích. Khi một RUN chạy, danh sách này sẽ được điền mỗi 30 phút.',
      id: 'Belum ada analisis. Setelah RUN berjalan, daftar ini terisi setiap 30 menit.',
    }),
    quiet: tr(language, { ko: '변화 없음', en: 'nothing moved', ja: '動きなし', th: 'ไม่มีความเคลื่อนไหว', vi: 'không có thay đổi', id: 'tidak ada perubahan' }),
    realized: tr(language, { ko: '실현', en: 'realized', ja: '実現', th: 'รับรู้แล้ว', vi: 'đã chốt', id: 'direalisasi' }),
    unrealized: tr(language, { ko: '미실현', en: 'unrealized', ja: '含み', th: 'ยังไม่รับรู้', vi: 'chưa chốt', id: 'belum direalisasi' }),
    peak: tr(language, { ko: '고점', en: 'peak', ja: '高値', th: 'จุดสูงสุด', vi: 'đỉnh', id: 'puncak' }),
    preservation: tr(language, { ko: '보존율', en: 'preservation', ja: '保存率', th: 'อัตราคงเหลือ', vi: 'tỷ lệ giữ', id: 'rasio dipertahankan' }),
    decisions: tr(language, { ko: '판단', en: 'decisions', ja: '判断', th: 'การตัดสินใจ', vi: 'quyết định', id: 'keputusan' }),
    skipped: tr(language, { ko: '보류', en: 'skipped', ja: '見送り', th: 'ข้าม', vi: 'bỏ qua', id: 'dilewati' }),
    opened: tr(language, { ko: '시작', en: 'opened', ja: '開始', th: 'เปิด', vi: 'mở', id: 'dibuka' }),
    closed: tr(language, { ko: '종료', en: 'closed', ja: '終了', th: 'ปิด', vi: 'đóng', id: 'ditutup' }),
    reason: tr(language, { ko: '사유', en: 'reason', ja: '理由', th: 'เหตุผล', vi: 'lý do', id: 'alasan' }),
    failed: tr(language, { ko: '분석을 불러오지 못했습니다', en: 'Could not load the analysis', ja: '分析を読み込めませんでした', th: 'โหลดการวิเคราะห์ไม่สำเร็จ', vi: 'Không tải được phân tích', id: 'Gagal memuat analisis' }),
  }

  const load = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API_BASE}/automation/ai-analysis?cycles=${CYCLES}`,
        { headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d = await r.json()
      setCycles(d.cycles || [])
      setError('')
    } catch { setError(T.failed) }
  }, [token])

  useEffect(() => {
    load()
    // A cycle closes every 30 min; refreshing on the minute keeps the
    // in-progress entry at the top current without hammering the endpoint.
    const iv = setInterval(load, 60000)
    return () => clearInterval(iv)
  }, [load])

  const card: any = { border: '1px solid var(--border-color,rgba(0,0,0,0.12))', borderRadius: 10, marginBottom: 10, overflow: 'hidden' }
  const meta: any = { fontSize: 11.5, color: 'var(--text-secondary,#8a8073)' }
  const num: any = { fontVariantNumeric: 'tabular-nums' }

  return (
    // z 600 + 32px top padding: the sticky top nav is z-index 500 and covers
    // a z-60 modal's first rows (the Close button) — same as the analyst and
    // create modals.
    <div role="dialog" aria-modal="true" aria-label={T.title} onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '32px 24px 24px', overflowY: 'auto' }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 860, margin: 'auto', background: 'var(--bg-card,#fff)', border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 12, padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>🧠 {T.title}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.subtitle}</div>
          </div>
          <button onClick={onClose}
            style={{ padding: '6px 12px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12 }}>
            {T.close}
          </button>
        </div>

        {error && <div style={{ color: '#f0663f', fontSize: 13 }}>⚠️ {error}</div>}
        {!error && cycles === null && <div style={meta}>{T.loading}</div>}
        {!error && cycles !== null && cycles.length === 0 && <div style={meta}>{T.empty}</div>}

        {(cycles || []).map(c => {
          const expandable = c.runs.length > 0
          const isOpen = !!open[c.start]
          return (
            <div key={c.start} style={card}>
              <button onClick={() => expandable && setOpen(o => ({ ...o, [c.start]: !o[c.start] }))}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', textAlign: 'left', font: 'inherit', color: 'inherit', padding: '10px 13px', border: 'none', background: c.quiet ? 'transparent' : 'rgba(194,106,69,0.06)', cursor: expandable ? 'pointer' : 'default' }}>
                <span style={{ fontWeight: 700, fontSize: 13.5, ...num }}>
                  {hhmm(c.start, language)}–{hhmm(c.end, language)}
                </span>
                <span style={meta}>{dayLabel(c.start, language)}</span>
                {c.quiet ? (
                  <span style={meta}>· {T.quiet}</span>
                ) : (
                  <>
                    <span style={{ fontSize: 13, fontWeight: 700, color: pnlColor(c.realized_delta), ...num }}>
                      {c.realized_delta >= 0 ? '+' : ''}{fmtUsd(c.realized_delta)}
                    </span>
                    {/* "label: n", not "n labels" — English is the only one of
                        the six that would need pluralising, and "1 decisions"
                        is not worth six singular strings to avoid. */}
                    <span style={meta}>
                      {T.decisions}: {c.decisions}
                      {c.skips > 0 && <> · {T.skipped}: {c.skips}</>}
                      {c.opened > 0 && <> · {T.opened}: {c.opened}</>}
                      {c.closed > 0 && <> · {T.closed}: {c.closed}</>}
                    </span>
                  </>
                )}
                <span style={{ marginLeft: 'auto', ...meta, ...num }}>
                  {T.realized} {c.realized === null ? '—' : `${c.realized >= 0 ? '+' : ''}${fmtUsd(c.realized)}`}
                  {' · '}
                  {T.unrealized} {c.unrealized === null ? '—' : `${c.unrealized >= 0 ? '+' : ''}${fmtUsd(c.unrealized)}`}
                  {expandable && <> {isOpen ? '▾' : '▸'}</>}
                </span>
              </button>

              {isOpen && (
                <div style={{ borderTop: '1px solid var(--border-color,rgba(0,0,0,0.1))' }}>
                  {c.runs.map(r => (
                    <div key={r.run_id} style={{ padding: '11px 13px', borderBottom: '1px solid var(--border-color,rgba(0,0,0,0.06))' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, fontSize: 13 }}>#{r.run_id} {r.symbol}</span>
                        {r.action && (
                          <span style={{ fontSize: 11.5, fontWeight: 700, padding: '2px 8px', borderRadius: 5, textTransform: 'uppercase',
                            background: r.action === 'buy' ? 'rgba(63,185,80,0.16)' : r.action === 'sell' ? 'rgba(240,102,63,0.16)' : 'rgba(227,160,8,0.16)',
                            color: r.action === 'buy' ? '#3fb950' : r.action === 'sell' ? '#f0663f' : '#e3a008' }}>
                            {r.action}{r.confidence !== null && ` ${Math.round(r.confidence * 100)}%`}
                          </span>
                        )}
                        <span style={{ ...meta, ...num, marginLeft: 'auto' }}>
                          {T.realized} <b style={{ color: pnlColor(r.realized) }}>
                            {r.realized === null ? '—' : `${r.realized >= 0 ? '+' : ''}${fmtUsd(r.realized)}`}
                          </b>
                          {r.peak !== null && <> · {T.peak} {fmtUsd(r.peak)}</>}
                          {r.preservation !== null && <> · {T.preservation} {Math.round(r.preservation * 100)}%</>}
                        </span>
                      </div>

                      {/* The desk's own words — journaled every cycle, never
                          shown until now. */}
                      {r.report && (
                        <p style={{ margin: '7px 0 0', fontSize: 13, lineHeight: 1.55, color: 'var(--text-secondary,#5f574c)', whiteSpace: 'pre-wrap' }}>
                          {r.report}
                        </p>
                      )}

                      {r.transitions.map((t, i) => (
                        <div key={i} style={{ ...meta, marginTop: 5 }}>
                          → <b>{t.to}</b>{t.reason && <> · {T.reason}: {t.reason}</>}
                        </div>
                      ))}

                      {r.skips.length > 0 && (
                        <div style={{ ...meta, marginTop: 5 }}>
                          {T.skipped}: {r.skips.map(s => `${s.reason}${s.count > 1 ? ` ×${s.count}` : ''}`).join(' · ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
