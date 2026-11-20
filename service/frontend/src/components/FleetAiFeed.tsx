import { useEffect, useState } from 'react'
import { API_BASE, marketLabel } from '../appShared'
import { tr, type Language } from '../i18n'

// Owner ask (2026-11-20): the Full Auto box shows the AI's analysis every
// 30 minutes — how it found its targets and its buy/sell decisions — always
// the latest 3 messages. Server: GET /api/fleets/{id}/ai-feed (read-side
// composition of fleet_events × run_events on the UTC :00/:30 grid).

type Msg = {
  start: string; end: string; partial?: boolean
  targets: {
    ranked: { symbol: string; market?: string; score?: number | null }[]
    kept: { symbol: string; count?: number }[]
    dropped: { symbol: string; reason: string }[]
    skipped: { symbol: string; reason: string; count?: number }[]
    opened: { symbol: string; market?: string; budget?: number | null }[]
    research_empty: number
    status: { to: string; reason?: string | null }[]
    research?: { market: string; long: number; short: number }[]
  }
  decisions: {
    counts: Record<string, number>
    runs: { run_id: number; symbol: string; action?: string; confidence?: number | null; report?: string | null; decided_by?: string | null }[]
    fills: { symbol: string; side?: string; quantity?: number | null; price?: number | null }[]
    runs_more?: number; fills_more?: number
  }
}

const POLL_MS = 60_000

const LOCALE: Record<Language, string> = { ko: 'ko-KR', en: 'en-US', ja: 'ja-JP', th: 'th-TH', vi: 'vi-VN', id: 'id-ID' }
const REPORT_MAX = 220

// live=false: a fleet that already stopped — one fetch, no polling.
export function FleetAiFeed({ token, fleetId, language, reasonLabel, live = true }: {
  token: string; fleetId: number; language: Language
  reasonLabel: (r: string | null) => string | null
  live?: boolean
}) {
  const [msgs, setMsgs] = useState<Msg[] | null>(null)

  useEffect(() => {
    let dead = false
    const load = async () => {
      try {
        const r = await fetch(`${API_BASE}/fleets/${fleetId}/ai-feed?limit=3&lang=${encodeURIComponent(language)}`,
          { headers: { Authorization: `Bearer ${token}` } })
        if (!r.ok) return
        const body = await r.json()
        if (!dead) setMsgs(body.messages || [])
      } catch { /* transient — keep the last good list */ }
    }
    load()
    if (!live) return () => { dead = true }
    const iv = setInterval(load, POLL_MS)
    return () => { dead = true; clearInterval(iv) }
  }, [token, fleetId, language, live])

  const L = (m: Record<string, string>) => tr(language, m as any)
  const T = {
    title: L({ ko: 'AI 분석 — 30분마다 (최근 3개)', en: 'AI analysis — every 30 min (latest 3)', ja: 'AI分析 — 30分ごと（最新3件）', th: 'การวิเคราะห์ AI — ทุก 30 นาที (ล่าสุด 3 รายการ)', vi: 'Phân tích AI — mỗi 30 phút (3 mục mới nhất)', id: 'Analisis AI — tiap 30 menit (3 terbaru)' }),
    empty: live
      ? L({ ko: '최근 24시간 동안 이 플릿의 AI 분석 기록이 아직 없습니다', en: 'No AI analysis for this fleet in the last 24 hours yet', ja: '直近24時間、このフリートのAI分析はまだありません', th: 'ยังไม่มีการวิเคราะห์ AI ของฟลีตนี้ใน 24 ชั่วโมงที่ผ่านมา', vi: 'Chưa có phân tích AI cho fleet này trong 24 giờ qua', id: 'Belum ada analisis AI untuk fleet ini dalam 24 jam terakhir' })
      : L({ ko: '이 플릿은 종료되었고, 최근 24시간 동안 AI 분석 기록이 없습니다', en: 'This fleet has ended; no AI analysis in its last 24 hours', ja: 'このフリートは終了しました。直近24時間のAI分析はありません', th: 'ฟลีตนี้จบแล้ว ไม่มีการวิเคราะห์ AI ใน 24 ชั่วโมงล่าสุด', vi: 'Fleet này đã kết thúc; không có phân tích AI trong 24 giờ cuối', id: 'Fleet ini sudah berakhir; tidak ada analisis AI dalam 24 jam terakhirnya' }),
    more: L({ ko: '개 더', en: 'more', ja: '件 他', th: 'รายการเพิ่มเติม', vi: 'mục khác', id: 'lainnya' }),
    partial: L({ ko: '기록이 많아 이 30분의 일부 TRADING 기록은 생략되었습니다', en: 'Some TRADING records in this 30 min were left out (too many to read)', ja: '記録が多いため、この30分の一部 TRADING 記録は省略されています', th: 'บางบันทึก TRADING ใน 30 นาทีนี้ถูกละไว้ (มากเกินไป)', vi: 'Một số bản ghi TRADING trong 30 phút này bị lược bớt (quá nhiều)', id: 'Sebagian catatan TRADING dalam 30 menit ini dihilangkan (terlalu banyak)' }),
    rule: L({ ko: '규칙 판단', en: 'rule fallback', ja: 'ルール判断', th: 'ตามกฎ', vi: 'theo quy tắc', id: 'aturan' }),
    targets: L({ ko: '🎯 종목 찾기', en: '🎯 Finding targets', ja: '🎯 銘柄探し', th: '🎯 หาเป้าหมาย', vi: '🎯 Tìm mục tiêu', id: '🎯 Mencari target' }),
    decisions: L({ ko: '💹 매수·매도 결정', en: '💹 Buy / sell decisions', ja: '💹 売買の判断', th: '💹 การตัดสินใจซื้อ/ขาย', vi: '💹 Quyết định mua / bán', id: '💹 Keputusan beli / jual' }),
    ranked: L({ ko: '후보 순위', en: 'Shortlist', ja: '候補順位', th: 'รายชื่อผู้สมัคร', vi: 'Danh sách ứng viên', id: 'Daftar kandidat' }),
    kept: L({ ko: '백테스트 통과', en: 'Passed backtest', ja: 'バックテスト通過', th: 'ผ่านแบ็กเทสต์', vi: 'Qua backtest', id: 'Lolos backtest' }),
    dropped: L({ ko: '백테스트 탈락', en: 'Failed backtest', ja: 'バックテスト不合格', th: 'ไม่ผ่านแบ็กเทสต์', vi: 'Trượt backtest', id: 'Gagal backtest' }),
    skipped: L({ ko: '제외', en: 'Skipped', ja: '除外', th: 'ข้าม', vi: 'Bỏ qua', id: 'Dilewati' }),
    opened: L({ ko: '새 TRADING 시작', en: 'New TRADING started', ja: '新しい TRADING 開始', th: 'เริ่ม TRADING ใหม่', vi: 'Bắt đầu TRADING mới', id: 'TRADING baru dimulai' }),
    researchEmpty: L({ ko: '조건에 맞는 후보 없음 — 리서치', en: 'No eligible candidates — research tries', ja: '条件に合う候補なし — リサーチ', th: 'ไม่มีผู้สมัครที่เข้าเกณฑ์ — รีเสิร์ช', vi: 'Không có ứng viên phù hợp — lượt nghiên cứu', id: 'Tidak ada kandidat yang memenuhi syarat — percobaan riset' }),
    research: L({ ko: '리서치 결과', en: 'Research found', ja: 'リサーチ結果', th: 'ผลรีเสิร์ช', vi: 'Kết quả nghiên cứu', id: 'Hasil riset' }),
    long: L({ ko: '롱', en: 'long', ja: 'ロング', th: 'ลอง', vi: 'mua', id: 'long' }),
    short: L({ ko: '숏', en: 'short', ja: 'ショート', th: 'ชอร์ต', vi: 'bán khống', id: 'short' }),
    times: L({ ko: '회', en: '×', ja: '回', th: 'ครั้ง', vi: 'lần', id: 'kali' }),
    status: L({ ko: '플릿 상태', en: 'Fleet status', ja: 'フリート状態', th: 'สถานะฟลีต', vi: 'Trạng thái fleet', id: 'Status fleet' }),
    noTargets: L({ ko: '이 30분 동안 새 종목 탐색 없음', en: 'No new target search in this 30 min', ja: 'この30分は新しい銘柄探索なし', th: 'ไม่มีการหาเป้าหมายใหม่ใน 30 นาทีนี้', vi: 'Không tìm mục tiêu mới trong 30 phút này', id: 'Tidak ada pencarian target baru dalam 30 menit ini' }),
    noDecisions: L({ ko: '이 30분 동안 매수·매도 결정 없음', en: 'No buy/sell decision in this 30 min', ja: 'この30分は売買判断なし', th: 'ไม่มีการตัดสินใจซื้อ/ขายใน 30 นาทีนี้', vi: 'Không có quyết định mua/bán trong 30 phút này', id: 'Tidak ada keputusan beli/jual dalam 30 menit ini' }),
    fill: L({ ko: '체결', en: 'Filled', ja: '約定', th: 'จับคู่แล้ว', vi: 'Khớp lệnh', id: 'Terisi' }),
    conf: L({ ko: '신뢰도', en: 'confidence', ja: '確信度', th: 'ความมั่นใจ', vi: 'độ tin cậy', id: 'keyakinan' }),
  }
  const act = (a?: string): string => {
    const map: Record<string, Record<string, string>> = {
      buy: { ko: '매수', en: 'buy', ja: '買い', th: 'ซื้อ', vi: 'mua', id: 'beli' },
      sell: { ko: '매도', en: 'sell', ja: '売り', th: 'ขาย', vi: 'bán', id: 'jual' },
      short: { ko: '숏 진입', en: 'short', ja: 'ショート', th: 'ชอร์ต', vi: 'bán khống', id: 'short' },
      cover: { ko: '숏 청산', en: 'cover', ja: '買い戻し', th: 'ปิดชอร์ต', vi: 'mua lại', id: 'cover' },
      close: { ko: '청산', en: 'close', ja: '決済', th: 'ปิด', vi: 'đóng', id: 'tutup' },
      hold: { ko: '보유/관망', en: 'hold', ja: '様子見', th: 'ถือ/รอ', vi: 'giữ', id: 'tahan' },
      none: { ko: '판단 없음', en: 'no verdict', ja: '判断なし', th: 'ไม่มีคำตัดสิน', vi: 'không có kết luận', id: 'tanpa keputusan' },
    }
    const k = (a || '').toLowerCase()
    return map[k] ? L(map[k]) : (a || '—')
  }
  const loc = LOCALE[language] || 'en-US'
  const hhmm = (iso: string) => {
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })
  }
  const day = (iso: string) => {
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(loc, { month: '2-digit', day: '2-digit' })
  }
  const statusText = (st: string): string => {
    const map: Record<string, Record<string, string>> = {
      draft: { ko: '준비', en: 'draft', ja: '下書き', th: 'ร่าง', vi: 'nháp', id: 'draf' },
      researching: { ko: '리서치 중', en: 'researching', ja: 'リサーチ中', th: 'กำลังรีเสิร์ช', vi: 'đang nghiên cứu', id: 'meriset' },
      building: { ko: '구성 중', en: 'building', ja: '構成中', th: 'กำลังสร้าง', vi: 'đang tạo', id: 'menyusun' },
      active: { ko: '운용 중', en: 'active', ja: '稼働中', th: 'ทำงาน', vi: 'đang chạy', id: 'aktif' },
      paused: { ko: '일시정지', en: 'paused', ja: '一時停止', th: 'พัก', vi: 'tạm dừng', id: 'dijeda' },
      stopping: { ko: '정지 중', en: 'stopping', ja: '停止中', th: 'กำลังหยุด', vi: 'đang dừng', id: 'menghentikan' },
      stopped: { ko: '정지됨', en: 'stopped', ja: '停止', th: 'หยุดแล้ว', vi: 'đã dừng', id: 'berhenti' },
    }
    return map[st] ? L(map[st]) : st
  }
  const clip = (txt: string) => txt.length > REPORT_MAX ? txt.slice(0, REPORT_MAX - 1) + '…' : txt
  const line: any = { fontSize: 12.5, lineHeight: 1.5, margin: '2px 0' }
  const muted: any = { color: 'var(--text-muted,#a89f92)' }

  return (
    <div style={{ margin: '4px 0 14px' }}>
      <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 8 }}>🧠 {T.title}</div>
      {msgs === null ? null : msgs.length === 0 ? (
        <div style={{ ...line, ...muted }}>{T.empty}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {msgs.map(m => {
            const t = m.targets, d = m.decisions
            const anyTarget = t.ranked.length || t.kept.length || t.dropped.length || t.skipped.length
              || t.opened.length || t.research_empty || t.status.length
            const counts = Object.entries(d.counts || {})
            return (
              <div key={m.start} style={{ border: '1px solid var(--border-color,rgba(0,0,0,0.1))', borderRadius: 9, padding: '9px 12px' }}>
                <div style={{ fontSize: 11.5, fontWeight: 700, ...muted, marginBottom: 4, fontVariantNumeric: 'tabular-nums' }}>
                  {day(m.start)} {hhmm(m.start)}–{hhmm(m.end)}
                </div>
                {m.partial && <div style={{ ...line, ...muted }}>⚠️ {T.partial}</div>}
                <div style={{ ...line, fontWeight: 700 }}>{T.targets}</div>
                {!anyTarget && <div style={{ ...line, ...muted }}>{T.noTargets}</div>}
                {t.ranked.length > 0 && (
                  <div style={line}>{T.ranked}: {t.ranked.map(r => `${r.symbol}${r.score != null ? ` (${r.score.toFixed(2)})` : ''}`).join(', ')}</div>
                )}
                {t.kept.length > 0 && <div style={line}>✅ {T.kept}: {t.kept.map(k => k.symbol).join(', ')}</div>}
                {t.dropped.map((x, i) => <div key={`d-${i}`} style={line}>❌ {T.dropped}: <b>{x.symbol}</b> <span style={muted}>— {x.reason}</span></div>)}
                {t.skipped.map((x, i) => (
                  <div key={`s-${i}`} style={line}>⏭ {T.skipped}: <b>{x.symbol}</b> <span style={muted}>— {x.reason}{(x.count || 1) > 1 ? ` (${x.count}${T.times})` : ''}</span></div>
                ))}
                {t.opened.map((x, i) => (
                  <div key={`o-${i}`} style={line}>🚀 {T.opened}: <b>{x.symbol}</b>{x.budget != null ? ` ($${x.budget.toFixed(0)})` : ''}</div>
                ))}
                {t.research_empty > 0 && <div style={line}>🔍 {T.researchEmpty} {t.research_empty}{T.times}</div>}
                {(t.research || []).length > 0 && (
                  <div style={line}>📊 {T.research}: {(t.research || []).map(r =>
                    `${marketLabel(r.market, language)} ${T.long} ${r.long} · ${T.short} ${r.short}`).join(' / ')}</div>
                )}
                {t.status.map((s, i) => (
                  <div key={`st-${i}`} style={line}>ℹ️ {T.status} → {statusText(s.to)}{s.reason ? ` · ${reasonLabel(s.reason)}` : ''}</div>
                ))}

                <div style={{ ...line, fontWeight: 700, marginTop: 6 }}>{T.decisions}</div>
                {counts.length === 0 && d.fills.length === 0 && <div style={{ ...line, ...muted }}>{T.noDecisions}</div>}
                {counts.length > 0 && (
                  <div style={line}>{counts.map(([k, v]) => `${act(k)} ${v}`).join(' · ')}</div>
                )}
                {d.runs.map(r => (
                  <div key={`r-${r.run_id}`} style={line}>
                    <b>{r.symbol}</b> — {act(r.action)}{r.confidence != null ? ` (${T.conf} ${r.confidence.toFixed(2)})` : ''}
                    {r.decided_by === 'rule' || r.decided_by === 'scaffold' ? <span style={muted}> · {T.rule}</span> : null}
                    {r.report ? <span style={muted} title={r.report}>: {clip(r.report)}</span> : null}
                  </div>
                ))}
                {(d.runs_more || 0) > 0 && <div style={{ ...line, ...muted }}>+{d.runs_more} {T.more}</div>}
                {d.fills.map((f, i) => (
                  <div key={`f-${i}`} style={line}>
                    🧾 {T.fill}: <b>{f.symbol}</b> {act(f.side)}{f.quantity != null ? ` ${f.quantity}` : ''}{f.price != null ? ` @ ${f.price}` : ''}
                  </div>
                ))}
                {(d.fills_more || 0) > 0 && <div style={{ ...line, ...muted }}>+{d.fills_more} {T.more}</div>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
