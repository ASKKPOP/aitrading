import { useEffect, useRef, useState } from 'react'
import { API_BASE, useLanguage } from '../appShared'
import { ASSISTANT_OPEN_EVENT } from '../appChrome'
import { tr } from '../i18n'

// AI Assistant dock — mounted once inside the authenticated shell so it is
// reachable from EVERY page (that is what makes "anytime" literal: no
// navigation, no losing your place). Collapsed it is a small floating button;
// expanded it is a right-side panel that keeps its conversation across route
// changes because the component never unmounts.
//
// The assistant is also the member's customer-support agent: it sees the whole
// account (membership, points, positions, trades, rules, runs, guidelines,
// watches, alerts, settings — never API keys) and is advisory only: it cannot
// place orders or change settings.
//
// History is never deleted. "New chat" starts a fresh conversation; every past
// conversation stays browsable from the history panel.

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
  // history panel: null = live chat; otherwise the list / a past conversation
  const [view, setView] = useState<'chat' | 'history'>('chat')
  const [sessions, setSessions] = useState<any[]>([])
  const [pastMessages, setPastMessages] = useState<any[] | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)

  const auth: any = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const T = {
    title: tr(language, { ko: 'AI 어시스턴트', en: 'AI Assistant', ja: 'AIアシスタント', th: 'ผู้ช่วย AI', vi: 'Trợ lý AI', id: 'Asisten AI' }),
    subtitle: tr(language, { ko: '내 계정 전체를 아는 상담역 · 고객 지원', en: 'Knows your whole account · Support', ja: 'アカウント全体を把握 · サポート', th: 'รู้ทั้งบัญชีของคุณ · ฝ่ายสนับสนุน', vi: 'Biết toàn bộ tài khoản · Hỗ trợ', id: 'Mengetahui seluruh akun Anda · Dukungan' }),
    placeholder: tr(language, { ko: '무엇이든 물어보세요 — 내 포지션, 멤버십, 규칙, 성과…', en: 'Ask anything — your positions, membership, rules, performance…', ja: '何でも聞いてください — ポジション・会員・ルール・成績…', th: 'ถามอะไรก็ได้ — สถานะ สมาชิก กฎ ผลงาน…', vi: 'Hỏi bất cứ điều gì — vị thế, thành viên, quy tắc, hiệu suất…', id: 'Tanyakan apa saja — posisi, keanggotaan, aturan, performa Anda…' }),
    empty: tr(language, { ko: '안녕하세요! 저는 회원님의 멤버십·포인트·포지션·거래 내역·자동화 규칙·리스크 한도·지침·감시 조건·알림·설정을 모두 보고 있는 고객 지원 어시스턴트입니다. 아래 질문을 누르거나 직접 입력해 보세요.', en: 'Hi! I am your support assistant — I can see your membership, points, positions, trade history, automation rules, risk limits, guidelines, watches, alerts and settings. Tap a question below or type your own.', ja: 'こんにちは！会員情報・ポイント・ポジション・取引履歴・ルール・リスク設定・通知をすべて把握するサポートアシスタントです。下の質問をタップするか、自由に入力してください。', th: 'สวัสดี! ฉันคือผู้ช่วยฝ่ายสนับสนุน — เห็นข้อมูลสมาชิก คะแนน สถานะ ประวัติการเทรด กฎ และการตั้งค่าทั้งหมดของคุณ แตะคำถามด้านล่างหรือพิมพ์เอง', vi: 'Xin chào! Tôi là trợ lý hỗ trợ — thấy toàn bộ thành viên, điểm, vị thế, lịch sử giao dịch, quy tắc và cài đặt của bạn. Chạm câu hỏi bên dưới hoặc tự nhập.', id: 'Halo! Saya asisten dukungan Anda — saya dapat melihat keanggotaan, poin, posisi, riwayat transaksi, aturan otomatisasi, batas risiko, panduan, pantauan, peringatan, dan pengaturan Anda. Pilih pertanyaan di bawah atau tulis sendiri.' }),
    send: tr(language, { ko: '보내기', en: 'Send', ja: '送信', th: 'ส่ง', vi: 'Gửi', id: 'Kirim' }),
    thinking: tr(language, { ko: '생각 중…', en: 'thinking…', ja: '考え中…', th: 'กำลังคิด…', vi: 'đang nghĩ…', id: 'berpikir…' }),
    newChat: tr(language, { ko: '새 대화', en: 'New chat', ja: '新しい会話', th: 'แชทใหม่', vi: 'Trò chuyện mới', id: 'Obrolan baru' }),
    history: tr(language, { ko: '대화 기록', en: 'History', ja: '履歴', th: 'ประวัติ', vi: 'Lịch sử', id: 'Riwayat' }),
    back: tr(language, { ko: '← 돌아가기', en: '← Back', ja: '← 戻る', th: '← กลับ', vi: '← Quay lại', id: '← Kembali' }),
    historyEmpty: tr(language, { ko: '아직 대화 기록이 없습니다.', en: 'No conversations yet.', ja: 'まだ履歴がありません。', th: 'ยังไม่มีประวัติ', vi: 'Chưa có lịch sử.', id: 'Belum ada percakapan.' }),
    historyNote: tr(language, { ko: '모든 대화가 보관됩니다 — 삭제되지 않습니다.', en: 'Every conversation is kept — nothing is deleted.', ja: 'すべての会話が保存されます。', th: 'ทุกบทสนทนาถูกเก็บไว้ — ไม่มีการลบ', vi: 'Mọi hội thoại được lưu — không bị xóa.', id: 'Setiap percakapan disimpan — tidak ada yang dihapus.' }),
    messages: tr(language, { ko: '메시지', en: 'messages', ja: '件', th: 'ข้อความ', vi: 'tin nhắn', id: 'pesan' }),
    close: tr(language, { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' }),
    advisory: tr(language, { ko: '자문 전용 — 어시스턴트는 주문을 내거나 설정을 바꾸지 않습니다.', en: 'Advisory only — the assistant never places orders or changes settings.', ja: '助言専用 — 発注や設定変更はしません。', th: 'ให้คำแนะนำเท่านั้น — ไม่ส่งคำสั่งและไม่เปลี่ยนการตั้งค่า', vi: 'Chỉ tư vấn — không đặt lệnh, không đổi cài đặt.', id: 'Hanya bersifat saran — asisten tidak pernah memasang order atau mengubah pengaturan.' }),
  }

  // customer-care starter questions, shown when the conversation is empty
  const STARTERS: string[] = [
    tr(language, { ko: '내 포트폴리오 상태 어때요?', en: 'How is my portfolio doing?', ja: 'ポートフォリオの状態は？', th: 'พอร์ตของฉันเป็นอย่างไร?', vi: 'Danh mục của tôi thế nào?', id: 'Bagaimana kondisi portofolio saya?' }),
    tr(language, { ko: '내 멤버십(구독) 상태를 알려주세요', en: "What's my membership status?", ja: '会員プランの状態を教えて', th: 'สถานะสมาชิกของฉันเป็นอย่างไร?', vi: 'Trạng thái thành viên của tôi?', id: 'Bagaimana status keanggotaan saya?' }),
    tr(language, { ko: '내 포인트 내역을 설명해 주세요', en: 'Explain my recent points history', ja: 'ポイント履歴を説明して', th: 'อธิบายประวัติคะแนนของฉัน', vi: 'Giải thích lịch sử điểm của tôi', id: 'Jelaskan riwayat poin saya belakangan ini' }),
    tr(language, { ko: '왜 자동화 규칙이 실행을 건너뛰었나요?', en: 'Why did my automation rule skip execution?', ja: 'なぜルールが実行をスキップした？', th: 'ทำไมกฎอัตโนมัติจึงข้ามการทำงาน?', vi: 'Vì sao quy tắc tự động bỏ qua thực thi?', id: 'Mengapa aturan otomatisasi saya melewatkan eksekusi?' }),
    tr(language, { ko: '내 리스크 설정을 검토해 주세요', en: 'Review my risk settings', ja: 'リスク設定をレビューして', th: 'ตรวจสอบการตั้งค่าความเสี่ยงของฉัน', vi: 'Xem lại cài đặt rủi ro của tôi', id: 'Tinjau pengaturan risiko saya' }),
    tr(language, { ko: '카피 트레이딩은 어떻게 시작하나요?', en: 'How do I start copy trading?', ja: 'コピー取引はどう始める？', th: 'เริ่มคัดลอกเทรดอย่างไร?', vi: 'Làm sao bắt đầu sao chép giao dịch?', id: 'Bagaimana cara memulai copy trading?' }),
  ]

  useEffect(() => { localStorage.setItem(OPEN_KEY, open ? '1' : '0') }, [open])

  // The desktop top bar's ✨ button opens the dock from anywhere.
  useEffect(() => {
    const openDock = () => setOpen(true)
    window.addEventListener(ASSISTANT_OPEN_EVENT, openDock)
    return () => window.removeEventListener(ASSISTANT_OPEN_EVENT, openDock)
  }, [])
  useEffect(() => { if (open && view === 'chat') endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy, open, view])

  // load the persistent conversation the first time the dock is opened
  useEffect(() => {
    if (!open || loaded || !token) return
    setLoaded(true)
    fetch(`${API_BASE}/assistant`, { headers: auth })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setMessages(d.messages || []) })
      .catch(() => { /* transient */ })
  }, [open, loaded, token])

  async function send(textArg?: string) {
    const text = (textArg ?? input).trim()
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

  // start a fresh conversation — every previous one is preserved server-side
  async function newChat() {
    setBusy(true)
    try {
      const r = await fetch(`${API_BASE}/assistant/sessions`, { method: 'POST', headers: auth })
      if (!r.ok) return
      setMessages([]); setView('chat'); setPastMessages(null)
    } catch { /* ignore */ }
    finally { setBusy(false) }
  }

  async function openHistory() {
    setView('history'); setPastMessages(null)
    try {
      const r = await fetch(`${API_BASE}/assistant/sessions`, { headers: auth })
      if (r.ok) setSessions((await r.json()).sessions || [])
    } catch { /* transient */ }
  }

  async function openPast(sessionId: number) {
    try {
      const r = await fetch(`${API_BASE}/assistant/sessions/${sessionId}`, { headers: auth })
      if (r.ok) setPastMessages((await r.json()).messages || [])
    } catch { /* transient */ }
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

  const bubble = (m: any) => (
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
  )

  return (
    <div className="app-drawer" style={{
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
        <button onClick={() => view === 'history' ? setView('chat') : openHistory()} title={T.history}
          style={{ border: '1px solid var(--border-color)', background: view === 'history' ? 'var(--bg-secondary)' : 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 11, padding: '4px 8px', cursor: 'pointer' }}>🕘</button>
        <button onClick={newChat} title={T.newChat} disabled={busy}
          style={{ border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 11, padding: '4px 8px', cursor: 'pointer', opacity: busy ? 0.5 : 1 }}>✚</button>
        <button onClick={() => setOpen(false)} title={T.close} aria-label={T.close} style={{ border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 13, padding: '4px 9px', cursor: 'pointer' }}>✕</button>
      </div>

      {view === 'history' ? (
        /* ── history panel: every past conversation, read-only ── */
        <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
          {pastMessages ? (
            <>
              <button onClick={() => setPastMessages(null)}
                style={{ border: 'none', background: 'transparent', color: 'var(--accent-primary)', fontSize: 12, cursor: 'pointer', padding: 0, marginBottom: 12 }}>{T.back}</button>
              {pastMessages.map(bubble)}
            </>
          ) : (
            <>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>{T.historyNote}</div>
              {sessions.length === 0 && (
                <div style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>{T.historyEmpty}</div>
              )}
              {sessions.map(s => (
                <button key={s.id} onClick={() => openPast(s.id)}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left', marginBottom: 8,
                    padding: '10px 12px', borderRadius: 10, border: '1px solid var(--border-color)',
                    background: 'var(--bg-secondary)', color: 'var(--text-primary)', cursor: 'pointer',
                  }}>
                  <div style={{ fontSize: 12.5, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.title || s.preview || T.title}
                  </div>
                  <div style={{ fontSize: 10.5, color: 'var(--text-muted)', marginTop: 3 }}>
                    {(s.updated_at || s.created_at || '').slice(0, 10)} · {s.message_count} {T.messages}
                  </div>
                </button>
              ))}
            </>
          )}
        </div>
      ) : (
        /* ── live chat ── */
        <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
          {messages.length === 0 && !busy && (
            <div>
              <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.6, marginBottom: 12 }}>{T.empty}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {STARTERS.map((q, i) => (
                  <button key={i} onClick={() => send(q)}
                    style={{
                      textAlign: 'left', padding: '8px 11px', borderRadius: 10, fontSize: 12.5,
                      border: '1px solid var(--border-color)', background: 'var(--bg-secondary)',
                      color: 'var(--text-primary)', cursor: 'pointer',
                    }}>{q}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map(bubble)}
          {busy && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{T.thinking}</div>}
          {err && <div style={{ fontSize: 12, color: 'var(--error,#d03b3b)' }}>⚠️ {err}</div>}
          <div ref={endRef} />
        </div>
      )}

      {/* composer (hidden while browsing history) */}
      {view === 'chat' && (
        <div style={{ padding: 12, borderTop: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder={T.placeholder}
              style={{ flex: 1, minWidth: 0, padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 12.5 }} />
            <button onClick={() => send()} disabled={busy || !input.trim()}
              style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary)', color: '#fff', fontWeight: 700, fontSize: 12.5, cursor: 'pointer', opacity: busy || !input.trim() ? 0.6 : 1 }}>{T.send}</button>
          </div>
          <div style={{ fontSize: 10.5, color: 'var(--text-muted)', marginTop: 7 }}>{T.advisory}</div>
        </div>
      )}
    </div>
  )
}

export default AssistantDock
