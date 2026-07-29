import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { SymbolSelect } from '../components/SymbolSelect'
import { tr } from '../i18n'

// Consultation chat (Plan 06 C3) — Personalized mode's advisory loop.
// Stateful conversation with the decision-tier model, which sees the same live
// context as the automated pipeline plus the user's guidelines. It never
// executes: the only handoff is a rule DRAFT the user confirms on /automation.

interface Props { token?: string | null }

export function ConsultPage({ token }: Props) {
  const { language } = useLanguage()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<any[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [input, setInput] = useState('')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<any | null>(null)
  const [err, setErr] = useState('')
  const endRef = useRef<HTMLDivElement | null>(null)

  const auth: any = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const T = {
    title: tr(language, { ko: 'AI 상담', en: 'AI Consultation', ja: 'AI相談', th: 'ปรึกษา AI', vi: 'Tư vấn AI', id: 'Konsultasi AI' }),
    subtitle: tr(language, { ko: '시장을 함께 논의하고, 합의된 계획을 자동화 규칙 초안으로 만듭니다 — 이 대화는 절대 주문을 내지 않습니다', en: 'Talk through the market and turn the plan into an automation-rule draft — this chat never places orders', ja: 'market を相談し、計画を自動化ルール草案に — このチャットは発注しません', th: 'ปรึกษาตลาดและแปลงแผนเป็นร่างกฎอัตโนมัติ — แชทนี้ไม่ส่งคำสั่งซื้อขาย', vi: 'Thảo luận thị trường và biến kế hoạch thành bản nháp quy tắc — chat này không bao giờ đặt lệnh', id: 'Bahas kondisi pasar dan ubah rencananya menjadi draf aturan otomatisasi — obrolan ini tidak pernah memasang order' }),
    newChat: tr(language, { ko: '새 상담', en: 'New chat', ja: '新しい相談', th: 'แชทใหม่', vi: 'Chat mới', id: 'Obrolan baru' }),
    send: tr(language, { ko: '보내기', en: 'Send', ja: '送信', th: 'ส่ง', vi: 'Gửi', id: 'Kirim' }),
    placeholder: tr(language, { ko: '예: 지금 BTC 진입해도 될까요? 지금 국면에서 뭘 봐야 하죠?', en: 'e.g. Should I enter BTC now? What should I watch in this regime?', ja: '例: 今BTCに入るべき？この局面で何を見る？', th: 'เช่น ตอนนี้ควรเข้า BTC ไหม?', vi: 'VD: Có nên vào BTC bây giờ?', id: 'mis. Apakah saya harus masuk BTC sekarang? Apa yang perlu diperhatikan pada kondisi ini?' }),
    proposeRule: tr(language, { ko: '이 대화를 규칙으로', en: 'Turn into a rule', ja: 'ルール草案にする', th: 'แปลงเป็นกฎ', vi: 'Biến thành quy tắc', id: 'Jadikan aturan' }),
    draftTitle: tr(language, { ko: '규칙 초안 (확인 필요)', en: 'Rule draft (needs your confirmation)', ja: 'ルール草案（要確認）', th: 'ร่างกฎ (ต้องยืนยัน)', vi: 'Bản nháp quy tắc (cần xác nhận)', id: 'Draf aturan (perlu konfirmasi Anda)' }),
    createRule: tr(language, { ko: '이 규칙 만들기', en: 'Create this rule', ja: 'このルールを作成', th: 'สร้างกฎนี้', vi: 'Tạo quy tắc này', id: 'Buat aturan ini' }),
    discard: tr(language, { ko: '취소', en: 'Discard', ja: '破棄', th: 'ยกเลิก', vi: 'Hủy', id: 'Buang' }),
    empty: tr(language, { ko: '질문을 입력해 상담을 시작하세요. AI는 실시간 정량·심리·국면·이벤트·고래 데이터와 회원님의 지침을 함께 봅니다.', en: 'Ask a question to start. The AI sees live quant, psychology, regime, event and whale data — plus your guidelines.', ja: '質問を入力して開始。AIはライブの定量・心理・局面・イベント・クジラデータとあなたの指針を参照します。', th: 'พิมพ์คำถามเพื่อเริ่ม AI เห็นข้อมูลสดและแนวทางของคุณ', vi: 'Đặt câu hỏi để bắt đầu. AI thấy dữ liệu trực tiếp và chỉ dẫn của bạn.', id: 'Ajukan pertanyaan untuk memulai. AI melihat data kuantitatif, psikologi, kondisi pasar, peristiwa, dan pergerakan whale secara langsung — beserta panduan Anda.' }),
    thinking: tr(language, { ko: '생각 중…', en: 'thinking…', ja: '考え中…', th: 'กำลังคิด…', vi: 'đang nghĩ…', id: 'berpikir…' }),
    noOrders: tr(language, { ko: '⚠ 이 상담은 주문을 실행하지 않습니다. 규칙을 만들어도 모든 주문은 리스크 게이트를 통과해야 하며 시뮬레이터에서만 체결됩니다.', en: '⚠ This consultation never executes orders. Even after creating a rule, every order passes the risk gate and fills only on the simulator.', ja: '⚠ この相談は発注しません。ルール作成後も全注文はリスクゲートを通り、シミュレーターのみで約定します。', th: '⚠ การปรึกษานี้ไม่ส่งคำสั่ง ทุกคำสั่งต้องผ่านประตูความเสี่ยงและเทรดในโหมดจำลองเท่านั้น', vi: '⚠ Tư vấn này không đặt lệnh. Mọi lệnh đều qua cổng rủi ro và chỉ khớp trên mô phỏng.', id: '⚠ Konsultasi ini tidak pernah mengeksekusi order. Bahkan setelah membuat aturan, setiap order melewati gerbang risiko dan hanya tereksekusi di simulator.' }),
    login: tr(language, { ko: '로그인하세요.', en: 'Please log in.', ja: 'ログインしてください。', th: 'กรุณาเข้าสู่ระบบ', vi: 'Vui lòng đăng nhập.', id: 'Silakan masuk.' }),
  }

  const loadSessions = useCallback(async () => {
    if (!token) return
    try {
      const r = await fetch(`${API_BASE}/analysis/chat/sessions`, { headers: auth })
      if (r.ok) setSessions((await r.json()).sessions || [])
    } catch { /* transient */ }
  }, [token])

  useEffect(() => { loadSessions() }, [loadSessions])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  async function openSession(id: number) {
    setSessionId(id); setDraft(null); setErr('')
    try {
      const r = await fetch(`${API_BASE}/analysis/chat/sessions/${id}`, { headers: auth })
      if (r.ok) {
        const d = await r.json()
        setMessages(d.messages || [])
        setSymbol(d.session?.symbol || 'BTCUSDT')
      }
    } catch { /* transient */ }
  }

  async function newSession() {
    setErr('')
    try {
      const r = await fetch(`${API_BASE}/analysis/chat/sessions`, {
        method: 'POST', headers: auth,
        body: JSON.stringify({ symbol: symbol || null, market: 'crypto' }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Could not start a session')
      setSessionId(d.id); setMessages([]); setDraft(null)
      await loadSessions()
    } catch (e: any) { setErr(e.message) }
  }

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    let sid = sessionId
    if (!sid) {
      await newSession()
      sid = sessionId
      if (!sid) {
        // newSession set state async; fetch the freshest session id
        const r = await fetch(`${API_BASE}/analysis/chat/sessions`, { headers: auth })
        const d = await r.json()
        sid = d.sessions?.[0]?.id ?? null
        setSessionId(sid)
      }
    }
    if (!sid) return
    setInput(''); setBusy(true); setErr('')
    setMessages(m => [...m, { id: `tmp-${Date.now()}`, role: 'user', content: text }])
    try {
      const r = await fetch(`${API_BASE}/analysis/chat/sessions/${sid}/messages`, {
        method: 'POST', headers: auth, body: JSON.stringify({ message: text }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Chat failed')
      setMessages(m => [...m, { id: `tmp-a-${Date.now()}`, role: 'assistant', content: d.reply, llm_model: d.llm_model }])
      await loadSessions()
    } catch (e: any) { setErr(e.message) }
    setBusy(false)
  }

  async function askDraft() {
    if (!sessionId) return
    setBusy(true); setErr('')
    try {
      const r = await fetch(`${API_BASE}/analysis/chat/sessions/${sessionId}/propose-rule`, {
        method: 'POST', headers: auth,
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Could not draft a rule')
      setDraft(d.draft)
    } catch (e: any) { setErr(e.message) }
    setBusy(false)
  }

  async function createRule() {
    if (!draft) return
    setBusy(true); setErr('')
    try {
      const r = await fetch(`${API_BASE}/automation/configs`, {
        method: 'POST', headers: auth,
        body: JSON.stringify({ ...draft, lang: language }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Could not create rule')
      setDraft(null)
      navigate('/automation')
    } catch (e: any) { setErr(e.message) }
    setBusy(false)
  }

  if (!token) {
    return <div className="page-container"><h1 style={{ fontSize: 22, fontWeight: 800 }}>{T.title}</h1>
      <div className="empty-state"><div className="empty-title">{T.login}</div></div></div>
  }

  const inp: any = { padding: '9px 11px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }

  return (
    <div className="page-container">
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 2 }}>{T.title}</h1>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14 }}>{T.subtitle}</div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <SymbolSelect variant="pair" value={symbol} onChange={setSymbol} style={{ ...inp, width: 140 }} />
        <button onClick={newSession} style={{ ...inp, cursor: 'pointer', fontWeight: 600 }}>+ {T.newChat}</button>
        {sessions.slice(0, 6).map(s => (
          <button key={s.id} onClick={() => openSession(s.id)}
            style={{ padding: '6px 12px', borderRadius: 999, fontSize: 12, cursor: 'pointer',
              border: sessionId === s.id ? '1.5px solid var(--accent-primary)' : '1px solid var(--border-color)',
              background: sessionId === s.id ? 'rgba(57,135,229,0.14)' : 'transparent',
              color: sessionId === s.id ? 'var(--accent-primary)' : 'inherit' }}>
            {s.symbol || 'chat'} · {s.n_messages}
          </button>
        ))}
      </div>

      {/* transcript */}
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 12, padding: 16, minHeight: 280, maxHeight: 460, overflowY: 'auto', marginBottom: 12 }}>
        {messages.length === 0 && !busy && (
          <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{T.empty}</div>
        )}
        {messages.map(m => (
          <div key={m.id} style={{ marginBottom: 14, display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '78%', padding: '10px 13px', borderRadius: 12, fontSize: 13.5, lineHeight: 1.55,
              whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? 'var(--accent-primary)' : 'var(--bg-secondary)',
              color: m.role === 'user' ? '#fff' : 'var(--text-primary)',
            }}>
              {m.content}
              {m.role === 'assistant' && m.llm_model && (
                <div style={{ fontSize: 10.5, color: 'var(--text-muted)', marginTop: 6 }}>{m.llm_model}</div>
              )}
            </div>
          </div>
        ))}
        {busy && <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{T.thinking}</div>}
        <div ref={endRef} />
      </div>

      {/* rule draft */}
      {draft && (
        <div style={{ background: 'var(--bg-card)', border: '1.5px solid var(--accent-primary)', borderRadius: 12, padding: 14, marginBottom: 12 }}>
          <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--accent-primary)', fontWeight: 700, marginBottom: 8 }}>{T.draftTitle}</div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 13, fontVariantNumeric: 'tabular-nums', marginBottom: 8 }}>
            <b>{draft.symbol}</b><span>{draft.market}</span><span>{draft.interval_minutes}m</span>
            <span>≥{draft.min_confidence}</span><span>${draft.size_usd}</span><span>{draft.risk_level}</span>
          </div>
          {draft.rationale && <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginBottom: 10 }}>{draft.rationale}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={createRule} disabled={busy} style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: 'var(--accent-primary)', color: '#fff', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' }}>{T.createRule}</button>
            <button onClick={() => setDraft(null)} style={{ ...inp, cursor: 'pointer', fontSize: 12.5 }}>{T.discard}</button>
          </div>
        </div>
      )}

      {/* composer */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder={T.placeholder} style={{ ...inp, flex: 1, minWidth: 240 }} />
        <button onClick={send} disabled={busy || !input.trim()} style={{ padding: '9px 20px', borderRadius: 8, border: 'none', background: 'var(--accent-primary)', color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer', opacity: busy || !input.trim() ? 0.6 : 1 }}>{T.send}</button>
        {messages.length > 1 && (
          <button onClick={askDraft} disabled={busy} style={{ ...inp, cursor: 'pointer', fontWeight: 600 }}>📋 {T.proposeRule}</button>
        )}
      </div>
      {err && <div style={{ color: 'var(--error,#d03b3b)', fontSize: 12.5, marginTop: 8 }}>⚠️ {err}</div>}
      <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 10, lineHeight: 1.5 }}>{T.noOrders}</div>
    </div>
  )
}

export default ConsultPage
