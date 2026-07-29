import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Live AI-spend pill for the top bar.
//
// The bar is already crowded (nav, theme, language, assistant, support,
// notifications, profile) and gets tighter on mobile, so the bar itself
// carries ONE number — this month's AI cost — and everything else lives in a
// panel behind a click: the per-service and per-model split, the model
// currently configured, and, for owners only, the system-wide totals.
//
// Data: GET /api/users/settings/llm-usage, polled on an interval and on tab
// focus. The endpoint gates the system-wide block on DOCS_OWNER_EMAILS, so the
// client never has to be trusted with that decision.

type Model = {
  provider: string; model: string; calls: number
  prompt_tokens: number; completion_tokens: number; cost_usd: number
}
type Service = { service: string; calls: number; cost_usd: number }
type Summary = {
  models: Model[]; services?: Service[]
  total_cost_usd: number; total_calls: number
  projected_cost_usd?: number; month_start?: string
}
type Payload = {
  user: Summary
  system?: Summary
  active?: { provider: string; model: string; key_source?: 'user' | 'system' } | null
}

const POLL_MS = 30000

function money(n: number | undefined): string {
  const v = Number(n || 0)
  // Sub-cent spend reads as "$0.00" and looks broken — show more precision
  // only where it carries information.
  if (v > 0 && v < 0.01) return `$${v.toFixed(4)}`
  return `$${v.toFixed(2)}`
}

export function AiUsagePill({ userToken }: { userToken?: string | null }) {
  const { language } = useLanguage()
  const [data, setData] = useState<Payload | null>(null)
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    if (!userToken) return
    try {
      const r = await fetch(`${API_BASE}/users/settings/llm-usage`, {
        headers: { Authorization: `Bearer ${userToken}` },
      })
      if (r.ok) setData(await r.json())
    } catch { /* transient — keep the last good figure on screen */ }
  }, [userToken])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!userToken) return
    const id = setInterval(load, POLL_MS)
    const onFocus = () => load()
    window.addEventListener('focus', onFocus)
    return () => { clearInterval(id); window.removeEventListener('focus', onFocus) }
  }, [load, userToken])

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const T = {
    label: tr(language, { ko: 'AI 사용량', en: 'AI usage', ja: 'AI 使用量',
      th: 'การใช้ AI', vi: 'Mức dùng AI', id: 'Penggunaan AI' }),
    thisMonth: tr(language, { ko: '이번 달 사용액', en: 'Spent this month',
      ja: '今月の利用額', th: 'ใช้ไปเดือนนี้', vi: 'Đã dùng tháng này', id: 'Terpakai bulan ini' }),
    projected: tr(language, { ko: '이번 달 예상 비용', en: 'Projected this month',
      ja: '今月の予想額', th: 'คาดการณ์เดือนนี้', vi: 'Dự kiến tháng này', id: 'Proyeksi bulan ini' }),
    projectedNote: tr(language, {
      ko: '지금까지의 사용 속도를 그대로 이어간다고 가정한 추정치입니다.',
      en: 'An estimate — it assumes the rest of the month keeps the pace set so far.',
      ja: 'これまでの利用ペースが続くと仮定した推定値です。',
      th: 'เป็นค่าประมาณ โดยถือว่าอัตราการใช้คงเดิมตลอดเดือน',
      vi: 'Ước tính — giả định phần còn lại của tháng giữ nguyên nhịp hiện tại.',
      id: 'Perkiraan — mengasumsikan sisa bulan ini berjalan dengan laju yang sama seperti sejauh ini.' }),
    byService: tr(language, { ko: '서비스별', en: 'By service', ja: 'サービス別',
      th: 'ตามบริการ', vi: 'Theo dịch vụ', id: 'Per layanan' }),
    byModel: tr(language, { ko: '모델별', en: 'By model', ja: 'モデル別',
      th: 'ตามโมเดล', vi: 'Theo mô hình', id: 'Per model' }),
    activeModel: tr(language, { ko: '현재 설정된 모델', en: 'Model in use',
      ja: '使用中のモデル', th: 'โมเดลที่ใช้อยู่', vi: 'Mô hình đang dùng', id: 'Model yang dipakai' }),
    ownKey: tr(language, { ko: '내 API 키', en: 'your API key', ja: '自分のAPIキー',
      th: 'คีย์ API ของคุณ', vi: 'khóa API của bạn', id: 'kunci API Anda' }),
    systemKey: tr(language, { ko: '서비스 제공 키', en: 'service key',
      ja: 'サービス提供キー', th: 'คีย์ของบริการ', vi: 'khóa của dịch vụ', id: 'kunci layanan' }),
    systemWide: tr(language, { ko: '시스템 전체 (관리자 전용)',
      en: 'System-wide (owner only)', ja: 'システム全体（オーナーのみ）',
      th: 'ทั้งระบบ (เจ้าของเท่านั้น)', vi: 'Toàn hệ thống (chỉ chủ sở hữu)', id: 'Seluruh sistem (khusus pemilik)' }),
    calls: tr(language, { ko: '호출', en: 'calls', ja: '呼び出し', th: 'ครั้ง', vi: 'lượt', id: 'panggilan' }),
    none: tr(language, { ko: '이번 달 사용 기록이 없습니다.', en: 'No AI usage yet this month.',
      ja: '今月の利用はまだありません。', th: 'ยังไม่มีการใช้ AI เดือนนี้',
      vi: 'Chưa có mức dùng AI trong tháng này.',
      id: 'Belum ada penggunaan AI bulan ini.' }),
    estimate: tr(language, { ko: '공개 가격표 기준 추정치입니다.',
      en: 'Estimated from public list prices.', ja: '公開価格表に基づく推定値です。',
      th: 'ประมาณจากราคาสาธารณะ', vi: 'Ước tính theo bảng giá công khai.', id: 'Diperkirakan dari harga daftar publik.' }),
  }

  if (!userToken || !data) return null

  const spent = data.user?.total_cost_usd ?? 0
  const projected = data.user?.projected_cost_usd ?? spent

  const section = (title: string, s: Summary | undefined) => {
    if (!s) return null
    return (
      <div style={{ marginTop: 12 }}>
        <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.06em',
          color: 'var(--text-muted,#8a8073)', marginBottom: 6 }}>{title}</div>
        <Row label={T.thisMonth} value={money(s.total_cost_usd)} strong />
        <Row label={T.projected} value={money(s.projected_cost_usd)} />
        {(s.services || []).length > 0 && (
          <>
            <div style={subhead}>{T.byService}</div>
            {(s.services || []).map(x => (
              <Row key={x.service} label={x.service}
                value={`${money(x.cost_usd)} · ${x.calls} ${T.calls}`} />
            ))}
          </>
        )}
        {s.models.length > 0 && (
          <>
            <div style={subhead}>{T.byModel}</div>
            {s.models.map(m => (
              <Row key={`${m.provider}/${m.model}`} label={m.model}
                value={`${money(m.cost_usd)} · ${m.calls} ${T.calls}`} />
            ))}
          </>
        )}
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="topnav-ai-pill">
      <button
        className="topnav-icon-btn"
        onClick={() => setOpen(v => !v)}
        title={`${T.label} · ${T.thisMonth} ${money(spent)} · ${T.projected} ${money(projected)}`}
        aria-label={T.label}
        aria-expanded={open}
        style={{ width: 'auto', padding: '0 8px', gap: 4, fontSize: 12.5,
          fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}
      >
        <span aria-hidden>🧠</span>{money(spent)}
      </button>

      {open && (
        <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', zIndex: 70,
          width: 300, maxHeight: '70vh', overflowY: 'auto',
          background: 'var(--bg-card,#161615)', color: 'var(--text-primary,#fff)',
          border: '1px solid var(--border-color,#2a2a28)', borderRadius: 12,
          padding: 14, boxShadow: '0 12px 32px rgba(0,0,0,.32)' }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>🧠 {T.label}</div>

          {data.active?.model && (
            <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--text-muted,#8a8073)' }}>
              {T.activeModel}: <strong style={{ color: 'var(--text-primary,#fff)' }}>
                {data.active.model}</strong>
              {data.active.provider ? ` (${data.active.provider})` : ''}
              {data.active.key_source
                && ` · ${data.active.key_source === 'user' ? T.ownKey : T.systemKey}`}
            </div>
          )}

          {data.user.total_calls === 0
            ? <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted,#8a8073)' }}>
                {T.none}</div>
            : section(T.label, data.user)}

          <p style={{ fontSize: 10.5, lineHeight: 1.5, color: 'var(--text-muted,#8a8073)',
            margin: '10px 0 0' }}>{T.projectedNote} {T.estimate}</p>

          {/* Present only when the server decided the caller is an owner. */}
          {data.system && (
            <div style={{ marginTop: 12, borderTop: '1px solid var(--border-color,#2a2a28)',
              paddingTop: 6 }}>
              {section(T.systemWide, data.system)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const subhead: React.CSSProperties = {
  fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '.06em',
  color: 'var(--text-muted,#8a8073)', margin: '10px 0 4px',
}

function Row({ label, value, strong = false }: {
  label: string; value: string; strong?: boolean
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10,
      fontSize: 12, padding: '2px 0' }}>
      <span style={{ color: 'var(--text-muted,#8a8073)', overflow: 'hidden',
        textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{ fontWeight: strong ? 700 : 500, fontVariantNumeric: 'tabular-nums',
        whiteSpace: 'nowrap' }}>{value}</span>
    </div>
  )
}

export default AiUsagePill
