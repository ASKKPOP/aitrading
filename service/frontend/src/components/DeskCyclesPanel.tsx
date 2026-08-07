import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { Language, tr } from '../i18n'
import { reasonLabel, statusLabel } from '../pages/RunsLivePage'
import { fmtUsd, pnlColor } from '../pages/tradeShared'

// AI Analysis — the desk's 30-minute cycles, opened from under the account
// tiles on the automation page.
//
// Nothing here is newly generated. Sooppiy AI already analyses every RUN on
// its interval and journals the result; /automation/ai-analysis folds that
// journal onto a fixed 30-minute grid. What this panel adds is the desk's
// WRITTEN report, which the runs grid only ever rendered as "buy conf 0.72".
//
// EVERY string in this panel localizes, including the ones that arrive from
// the server. The split is by kind, not by convenience:
//   * the verb (buy/sell/hold) and the status a run moved to are enums, so
//     they map here — ACTION_TEXT below, STATUS_TEXT/REASON_TEXT on the runs
//     page, which is where those maps already lived;
//   * the gate-skip reasons and the desk's written report are prose, so they
//     arrive already localized from /automation/ai-analysis (catalogue for
//     ours, cached translation for the model's — see market_i18n.py).
// The journal itself stays English on purpose: it is the corpus desk_memory
// retrieves from, and a corpus that changes language with the reader is one
// that no longer matches its own past.

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

const BUCKET_MS = 30 * 60 * 1000
const MAX_CYCLES = 48      // desk_cycles.MAX_CYCLES — one whole day of grid
const PER_PAGE = 8         // cycles per page, ~4 hours at a glance

// The desk's verb. Rendered as a chip next to the run, so it has to read as a
// word in the reader's language — "HOLD 55%" is not a Korean sentence.
const ACTION_TEXT: Record<string, Record<Language, string>> = {
  buy: { ko: '매수', en: 'BUY', ja: '買い', th: 'ซื้อ', vi: 'MUA', id: 'BELI' },
  sell: { ko: '매도', en: 'SELL', ja: '売り', th: 'ขาย', vi: 'BÁN', id: 'JUAL' },
  hold: { ko: '보류', en: 'HOLD', ja: 'ホールド', th: 'ถือไว้', vi: 'GIỮ', id: 'TAHAN' },
  retire: { ko: '슬롯 반납', en: 'RETIRE', ja: 'スロット返却', th: 'คืนสล็อต', vi: 'TRẢ SUẤT', id: 'LEPAS SLOT' },
}

const actionLabel = (action: string, lang: Language): string =>
  ACTION_TEXT[action] ? tr(lang, ACTION_TEXT[action]) : action

// Cycle stamps are UTC; render them in the reader's own clock and in the
// app's chosen language, not the browser's.
const hhmm = (iso: string, lang: string) =>
  new Date(iso).toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit', hour12: false })

const dayLabel = (iso: string, lang: string) =>
  new Date(iso).toLocaleDateString(lang, { month: 'short', day: 'numeric' })

// Local calendar day <-> the YYYY-MM-DD a <input type="date"> speaks. Built
// by hand rather than via toISOString(), which would shift the day for every
// reader east or west of UTC — the exact bug a date filter must not have.
const dayKeyOf = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// The window a day key asks the server for. The grid is UTC and the reader's
// day is not, so the browser is the only place that can compute this: it ends
// the window at `end_ms` and counts back the buckets the day covers.
function dayWindow(key: string): { start: number; endMs: number; cycles: number } | null {
  const [y, m, d] = key.split('-').map(Number)
  if (!y || !m || !d) return null
  const start = new Date(y, m - 1, d, 0, 0, 0, 0).getTime()
  const nextDay = new Date(y, m - 1, d + 1, 0, 0, 0, 0).getTime()
  // A day still running ends at now; one already over ends a millisecond
  // before midnight, so the bucket that opens the NEXT day is not counted in.
  const endMs = Math.min(Date.now(), nextDay - 1)
  if (endMs < start) return null   // a day that has not happened yet
  const first = Math.floor(start / BUCKET_MS) * BUCKET_MS
  const last = Math.floor(endMs / BUCKET_MS) * BUCKET_MS
  const cycles = Math.min(MAX_CYCLES, Math.max(1, (last - first) / BUCKET_MS + 1))
  return { start, endMs, cycles }
}

export function DeskCyclesPanel({ token, onClose }: { token: string | null; onClose: () => void }) {
  const { language } = useLanguage()
  const [cycles, setCycles] = useState<Cycle[] | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const today = dayKeyOf(new Date())
  const [day, setDay] = useState(today)
  const [page, setPage] = useState(0)

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
    date: tr(language, { ko: '날짜', en: 'Date', ja: '日付', th: 'วันที่', vi: 'Ngày', id: 'Tanggal' }),
    today: tr(language, { ko: '오늘', en: 'Today', ja: '今日', th: 'วันนี้', vi: 'Hôm nay', id: 'Hari ini' }),
    prevDay: tr(language, { ko: '이전 날', en: 'Previous day', ja: '前の日', th: 'วันก่อนหน้า', vi: 'Ngày trước', id: 'Hari sebelumnya' }),
    nextDay: tr(language, { ko: '다음 날', en: 'Next day', ja: '次の日', th: 'วันถัดไป', vi: 'Ngày sau', id: 'Hari berikutnya' }),
    prevPage: tr(language, { ko: '이전', en: 'Previous', ja: '前へ', th: 'ก่อนหน้า', vi: 'Trước', id: 'Sebelumnya' }),
    nextPage: tr(language, { ko: '다음', en: 'Next', ja: '次へ', th: 'ถัดไป', vi: 'Tiếp', id: 'Berikutnya' }),
    emptyDay: tr(language, {
      ko: '이 날에는 분석 기록이 없습니다.',
      en: 'No analysis was recorded on this day.',
      ja: 'この日は分析記録がありません。',
      th: 'วันนี้ไม่มีบันทึกการวิเคราะห์',
      vi: 'Ngày này không có bản ghi phân tích nào.',
      id: 'Tidak ada catatan analisis pada hari ini.',
    }),
  }

  const win = useMemo(() => dayWindow(day), [day])
  // Buckets are UTC and the filter is a LOCAL day, so the response can open
  // with the bucket that straddles the reader's midnight. Drop it here rather
  // than show a row stamped with yesterday's clock under today's heading.
  const dayCycles = useMemo(() => (cycles || []).filter(c => {
    if (!win) return false
    const t = new Date(c.start).getTime()
    return t >= win.start && t <= win.endMs
  }), [cycles, win])
  const pages = Math.max(1, Math.ceil(dayCycles.length / PER_PAGE))
  const pageIndex = Math.min(page, pages - 1)
  const visible = dayCycles.slice(pageIndex * PER_PAGE, pageIndex * PER_PAGE + PER_PAGE)
  const shiftDay = (delta: number) => {
    const [y, m, d] = day.split('-').map(Number)
    setDay(dayKeyOf(new Date(y, m - 1, d + delta)))
  }

  const load = useCallback(async () => {
    if (!token) return
    if (!win) { setCycles([]); setError(''); return }   // a future day
    try {
      const r = await fetch(
        `${API_BASE}/automation/ai-analysis?cycles=${win.cycles}&end_ms=${win.endMs}`,
        { headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const d = await r.json()
      setCycles(d.cycles || [])
      setError('')
    } catch { setError(T.failed) }
    // `win.endMs` moves with the clock on today, so it is deliberately not a
    // dependency — refetching every render is not the same as refreshing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, day])

  useEffect(() => { setPage(0) }, [day])

  useEffect(() => {
    load()
    // A cycle closes every 30 min; refreshing on the minute keeps the
    // in-progress entry at the top current without hammering the endpoint.
    // The poll runs on a past day too, even though its numbers are settled:
    // a report the translator has not seen before comes back English and is
    // warmed in the background, so the next poll is what makes it localize.
    const iv = setInterval(load, 60000)
    return () => clearInterval(iv)
  }, [load])

  const card: any = { border: '1px solid var(--border-color,rgba(0,0,0,0.12))', borderRadius: 10, marginBottom: 10, overflow: 'hidden' }
  const meta: any = { fontSize: 11.5, color: 'var(--text-secondary,#8a8073)' }
  const num: any = { fontVariantNumeric: 'tabular-nums' }
  const navBtn: any = { width: 28, height: 28, lineHeight: 1, borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', cursor: 'pointer', fontSize: 12.5 }

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

        {/* Date filter — the day is the reader's local one, defaulting to
            today. `max` stops the picker offering a day the desk cannot have
            journaled yet. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <span style={meta}>{T.date}</span>
          <button onClick={() => shiftDay(-1)} aria-label={T.prevDay} title={T.prevDay}
            style={navBtn}>‹</button>
          <input type="date" value={day} max={today}
            onChange={e => e.target.value && setDay(e.target.value)}
            style={{ padding: '5px 8px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'transparent', color: 'inherit', font: 'inherit', fontSize: 12.5 }} />
          <button onClick={() => shiftDay(1)} aria-label={T.nextDay} title={T.nextDay}
            disabled={day >= today} style={{ ...navBtn, opacity: day >= today ? 0.4 : 1 }}>›</button>
          <button onClick={() => setDay(today)} disabled={day === today}
            style={{ ...navBtn, width: 'auto', padding: '5px 10px', opacity: day === today ? 0.4 : 1 }}>
            {T.today}
          </button>
        </div>

        {error && <div style={{ color: '#f0663f', fontSize: 13 }}>⚠️ {error}</div>}
        {!error && cycles === null && <div style={meta}>{T.loading}</div>}
        {!error && cycles !== null && dayCycles.length === 0 && (
          <div style={meta}>{day === today ? T.empty : T.emptyDay}</div>
        )}

        {visible.map(c => {
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
                            {actionLabel(r.action, language)}{r.confidence !== null && ` ${Math.round(r.confidence * 100)}%`}
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

                      {/* Status and reason are enums, so they render through
                          the runs page's own maps — the server leaves them as
                          codes precisely so this side can. */}
                      {r.transitions.map((t, i) => (
                        <div key={i} style={{ ...meta, marginTop: 5 }}>
                          → <b>{statusLabel(t.to || undefined, language) || t.to}</b>
                          {t.reason && <> · {T.reason}: {reasonLabel(t.reason, language)}</>}
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

        {/* Page through the day at the BOTTOM, where the reader arrives after
            the last cycle on the page — a single day is 48 cycles and the
            modal scrolls, so paging from the top would mean scrolling back up
            to move on. Hidden on a day that fits in one page. */}
        {pages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginTop: 4 }}>
            <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={pageIndex === 0}
              style={{ ...navBtn, width: 'auto', padding: '5px 10px', opacity: pageIndex === 0 ? 0.4 : 1 }}>
              ‹ {T.prevPage}
            </button>
            <span style={{ ...meta, ...num }}>{pageIndex + 1} / {pages}</span>
            <button onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={pageIndex >= pages - 1}
              style={{ ...navBtn, width: 'auto', padding: '5px 10px', opacity: pageIndex >= pages - 1 ? 0.4 : 1 }}>
              {T.nextPage} ›
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
