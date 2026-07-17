import { useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// AI Assistant dock — mounted once inside the authenticated shell so it is
// reachable from EVERY page (that is what makes "anytime" literal: no
// navigation, no losing your place). Collapsed it is a small floating button;
// expanded it is a right-side panel that keeps its conversation across route
// changes because the component never unmounts.
//
// The assistant sees the user's whole account (positions, rules, runs,
// guidelines, watches, alerts, settings — never API keys) and is advisory
// only: it cannot place orders or change settings.

interface Props { token?: string | null }

const OPEN_KEY = 'sooppiy_assistant_open'

export function AssistantDock({ token }: Props) {
  const { language } = useLanguage()
  const [open, setOpen] = useState(() => localStorage.getItem(OPEN_KEY) === '1')
  const [messages, setMessages] = useState<any[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [loaded, setLoaded] = useState(false)
  const endRef = useRef<HTMLDivElement | null>(null)

  const auth: any = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const T = {
    title: tr(language, { ko: 'AI 어시스턴트', en: 'AI Assistant', ja: 'AIアシスタント', th: 'ผู้ช่วย AI', vi: 'Trợ lý AI' }),
    subtitle: tr(language, { ko: '내 계정 전체를 아는 상담역', en: 'Knows your whole account', ja: 'アカウント全体を把握', th: 'รู้ทั้งบัญชีของคุณ', vi: 'Biết toàn bộ tài khoản của bạn' }),
    placeholder: tr(language, { ko: '무엇이든 물어보세요 — 내 포지션, 규칙, 성과, 설정…', en: 'Ask anything — your positions, rules, performance, settings…', ja: '何でも聞いてください — ポジション・ルール・成績・設定…', th: 'ถามอะไรก็ได้ — สถานะ กฎ ผลงาน การตั้งค่า…', vi: 'Hỏi bất cứ điều gì — vị thế, quy tắc, hiệu suất, cài đặt…' }),
    empty: tr(language, { ko: '안녕하세요! 저는 회원님의 포지션·자동화 규칙·실행 기록·리스크 한도·지침·감시 조건·알림·설정을 모두 보고 있습니다. 무엇이든 물어보세요.\n\n예시:\n· 내 포지션 상태 어때요?\n· 왜 어제 규칙이 체결을 건너뛰었죠?\n· 내 리스크 설정 검토해 주세요', en: "Hi! I can see your positions, automation rules, run history, risk limits, guidelines, watches, alerts and settings. Ask me anything.\n\nTry:\n· How is my portfolio doing?\n· Why did my rule skip execution yesterday?\n· Review my risk settings", ja: 'こんにちは！ポジション・ルール・実行履歴・リスク設定・指針・監視・通知をすべて把握しています。何でもどうぞ。', th: 'สวัสดี! ฉันเห็นสถานะ กฎ ประวัติ ลิมิตความเสี่ยง แนวทาง และการแจ้งเตือนของคุณทั้งหมด', vi: 'Xin chào! Tôi thấy toàn bộ vị thế, quy tắc, lịch sử, giới hạn rủi ro và cài đặt của bạn.' }),
    send: tr(language, { ko: '보내기', en: 'Send', ja: '送信', th: 'ส่ง', vi: 'Gửi' }),
    thinking: tr(language, { ko: '생각 중…', en: 'thinking…', ja: '考え中…', th: 'กำลังคิด…', vi: 'đang nghĩ…' }),
    clear: tr(language, { ko: '대화 비우기', en: 'Clear chat', ja: '会話を消去', th: 'ล้างแชท', vi: 'Xóa hội thoại' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng' }),
    advisory: tr(language, { ko: '자문 전용 — 어시스턴트는 주문을 내거나 설정을 바꾸지 않습니다.', en: 'Advisory only — the assistant never places orders or changes settings.', ja: '助言専用 — 発注や設定変更はしません。', th: 'ให้คำแนะนำเท่านั้น — ไม่ส่งคำสั่งและไม่เปลี่ยนการตั้งค่า', vi: 'Chỉ tư vấn — không đặt lệnh, không đổi cài đặt.' }),
  }

  useEffect(() => { localStorage.setItem(OPEN_KEY, open ? '1' : '0') }, [open])
  useEffect(() => { if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy, open])

  // load the persistent conversation the first time the dock is opened
  useEffect(() => {
    if (!open || loaded || !token) return
    setLoaded(true)
    fetch(`${API_BASE}/assistant`, { headers: auth })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setMessages(d.messages || []) })
      .catch(() => { /* transient */ })
  }, [open, loaded, token])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput(''); setBusy(true); setErr('')
    setMessages(m => [...m, { id: `u-${Date.now()}`, role: 'user', content: text }])
    try {
      const r = await fetch(`${API_BASE}/assistant/messages`, {
        method: 'POST', headers: auth, body: JSON.stringify({ message: text, lang: language }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Assistant failed')
      setMessages(m => [...m, { id: `a-${Date.now()}`, role: 'assistant', content: d.reply, llm_model: d.llm_model }])
    } catch (e: any) { setErr(e.message) }
    setBusy(false)
  }

  async function clear() {
    try {
      await fetch(`${API_BASE}/assistant`, { method: 'DELETE', headers: auth })
      setMessages([])
    } catch { /* ignore */ }
  }

  if (!token) return null

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} aria-label={T.title} title={T.title}
        style={{
          position: 'fixed', right: 20, bottom: 20, zIndex: 60,
          width: 54, height: 54, borderRadius: '50%', border: 'none', cursor: 'pointer',
          background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
          color: '#fff', fontSize: 22, boxShadow: '0 6px 22px rgba(0,0,0,0.35)',
        }}>✨</button>
    )
  }

  return (
    <div style={{
      position: 'fixed', right: 0, top: 0, bottom: 0, zIndex: 60,
      width: 'min(420px, 100vw)', display: 'flex', flexDirection: 'column',
      background: 'var(--bg-card)', borderLeft: '1px solid var(--border-color)',
      boxShadow: '-8px 0 30px rgba(0,0,0,0.28)',
    }}>
      {/* header */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 18 }}>✨</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{T.title}</div>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{T.subtitle}</div>
        </div>
        <button onClick={clear} title={T.clear} style={{ border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 11, padding: '4px 8px', cursor: 'pointer' }}>⟲</button>
        <button onClick={() => setOpen(false)} title={T.close} aria-label={T.close} style={{ border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 13, padding: '4px 9px', cursor: 'pointer' }}>✕</button>
      </div>

      {/* transcript */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
        {messages.length === 0 && !busy && (
          <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{T.empty}</div>
        )}
        {messages.map(m => (
          <div key={m.id} style={{ marginBottom: 12, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '86%', padding: '9px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.55,
              whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? 'var(--accent-primary)' : 'var(--bg-secondary)',
              color: m.role === 'user' ? '#fff' : 'var(--text-primary)',
            }}>
              {m.content}
              {m.role === 'assistant' && m.llm_model && (
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 5 }}>{m.llm_model}</div>
              )}
            </div>
          </div>
        ))}
        {busy && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{T.thinking}</div>}
        {err && <div style={{ fontSize: 12, color: 'var(--error,#d03b3b)' }}>⚠️ {err}</div>}
        <div ref={endRef} />
      </div>

      {/* composer */}
      <div style={{ padding: 12, borderTop: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder={T.placeholder}
            style={{ flex: 1, minWidth: 0, padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 12.5 }} />
          <button onClick={send} disabled={busy || !input.trim()}
            style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary)', color: '#fff', fontWeight: 700, fontSize: 12.5, cursor: 'pointer', opacity: busy || !input.trim() ? 0.6 : 1 }}>{T.send}</button>
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--text-muted)', marginTop: 7 }}>{T.advisory}</div>
      </div>
    </div>
  )
}

export default AssistantDock
