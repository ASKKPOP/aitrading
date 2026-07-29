import { useEffect, useRef, useState } from 'react'

import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Member ⇄ administrator chat. One conversation per member (the backend keys
// support_threads on user_id), so this reads like a single thread with
// support. Polls while open; admin replies also raise a 'support'
// notification in the notification centre.

type Message = {
  id: number
  sender: 'user' | 'admin'
  admin_email: string | null
  body: string
  created_at: string
}

const POLL_MS = 20000
const fmtTime = (v: string) => String(v || '').replace('T', ' ').replace('Z', '').slice(0, 16)

export default function SupportPage({ userToken }: { userToken: string }) {
  const { language } = useLanguage()
  const [messages, setMessages] = useState<Message[]>([])
  const [thread, setThread] = useState<any>(null)
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef<HTMLDivElement | null>(null)

  const auth = () => ({ 'Authorization': `Bearer ${userToken}`, 'Content-Type': 'application/json' })

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/support/thread`, { headers: auth() })
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      setMessages(data.messages || [])
      setThread(data.thread || null)
      setError('')
    } catch {
      setError(tr(language, { ko: '대화를 불러오지 못했습니다', en: 'Failed to load the conversation', ja: '会話を読み込めませんでした', th: 'โหลดการสนทนาไม่สำเร็จ', vi: 'Không tải được cuộc trò chuyện', id: 'Gagal memuat percakapan' }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, POLL_MS)
    return () => clearInterval(timer)
  }, [userToken])

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'nearest' }) }, [messages.length])

  const send = async () => {
    const body = draft.trim()
    if (!body || sending) return
    setSending(true)
    try {
      const res = await fetch(`${API_BASE}/support/messages`, {
        method: 'POST', headers: auth(), body: JSON.stringify({ body }),
      })
      if (!res.ok) throw new Error(String(res.status))
      setMessages((await res.json()).messages || [])
      setDraft('')
      setError('')
    } catch {
      setError(tr(language, { ko: '전송에 실패했습니다', en: 'Failed to send', ja: '送信に失敗しました', th: 'ส่งไม่สำเร็จ', vi: 'Gửi thất bại', id: 'Gagal mengirim' }))
    } finally {
      setSending(false)
    }
  }

  const bubble = (m: Message) => {
    const mine = m.sender === 'user'
    return (
      <div key={m.id} style={{ display: 'flex', justifyContent: mine ? 'flex-end' : 'flex-start', marginBottom: 10 }}>
        <div style={{ maxWidth: '78%' }}>
          {!mine && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 3, paddingLeft: 4 }}>
              {tr(language, { ko: '운영팀', en: 'Sooppiy team', ja: '運営チーム', th: 'ทีม Sooppiy', vi: 'Đội ngũ Sooppiy', id: 'Tim Sooppiy' })}
              {m.admin_email ? ` · ${m.admin_email}` : ''}
            </div>
          )}
          <div style={{
            padding: '9px 13px', borderRadius: 16,
            borderBottomRightRadius: mine ? 4 : 16,
            borderBottomLeftRadius: mine ? 16 : 4,
            background: mine ? 'var(--accent-primary)' : 'var(--bg-secondary, rgba(0,0,0,0.05))',
            color: mine ? '#fff' : 'var(--text-primary)',
            fontSize: 13.5, lineHeight: 1.55, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {m.body}
          </div>
          <div style={{
            fontSize: 10.5, color: 'var(--text-muted)', marginTop: 3,
            textAlign: mine ? 'right' : 'left', fontFamily: 'var(--font-mono)',
          }}>
            {fmtTime(m.created_at)}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>
          {tr(language, { ko: '고객지원 문의', en: 'Support', ja: 'サポート', th: 'ฝ่ายสนับสนุน', vi: 'Hỗ trợ', id: 'Dukungan' })}
        </h1>
        {thread?.status === 'closed' && (
          <span style={{
            fontSize: 11, fontWeight: 700, borderRadius: 999, padding: '2px 9px',
            background: 'var(--bg-secondary, rgba(0,0,0,0.05))', color: 'var(--text-muted)',
          }}>
            {tr(language, { ko: '종료됨', en: 'Closed', ja: '終了', th: 'ปิดแล้ว', vi: 'Đã đóng', id: 'Ditutup' })}
          </span>
        )}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 3 }}>
        {tr(language, {
          ko: '운영팀과 직접 대화합니다. 답변이 오면 알림으로 알려드립니다.',
          en: 'Talk directly with the Sooppiy team. You get a notification when they reply.',
          ja: '運営チームと直接やり取りできます。返信があると通知されます。',
          th: 'พูดคุยกับทีม Sooppiy โดยตรง คุณจะได้รับการแจ้งเตือนเมื่อมีการตอบกลับ',
          vi: 'Trò chuyện trực tiếp với đội ngũ Sooppiy. Bạn sẽ nhận thông báo khi có phản hồi.',
          id: 'Bicara langsung dengan tim Sooppiy. Anda akan menerima notifikasi saat mereka membalas.',
        })}
      </div>

      {error && <div style={{ color: 'var(--error, #d03b3b)', fontSize: 12.5, marginTop: 10 }}>{error}</div>}

      <div className="card" style={{ padding: '16px', marginTop: 14, minHeight: 260, maxHeight: 460, overflowY: 'auto' }}>
        {loading && <div style={{ fontSize: 13 }}>{tr(language, { ko: '불러오는 중...', en: 'Loading...', ja: '読み込み中...', th: 'กำลังโหลด...', vi: 'Đang tải...', id: 'Memuat...' })}</div>}
        {!loading && messages.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13.5, padding: '40px 12px' }}>
            {tr(language, {
              ko: '아직 대화가 없습니다. 궁금한 점을 남겨 주세요.',
              en: 'No messages yet — send us your question below.',
              ja: 'まだメッセージはありません。下からご質問ください。',
              th: 'ยังไม่มีข้อความ — ส่งคำถามของคุณด้านล่าง',
              vi: 'Chưa có tin nhắn — gửi câu hỏi của bạn bên dưới.',
              id: 'Belum ada pesan — kirimkan pertanyaan Anda di bawah ini.',
            })}
          </div>
        )}
        {messages.map(bubble)}
        <div ref={endRef} />
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'flex-end' }}>
        <textarea
          value={draft}
          onChange={e => setDraft(e.target.value.slice(0, 4000))}
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send() } }}
          rows={3}
          placeholder={tr(language, { ko: '메시지를 입력하세요… (⌘/Ctrl + Enter 로 전송)', en: 'Write a message… (⌘/Ctrl + Enter to send)', ja: 'メッセージを入力… (⌘/Ctrl + Enter で送信)', th: 'พิมพ์ข้อความ… (⌘/Ctrl + Enter เพื่อส่ง)', vi: 'Nhập tin nhắn… (⌘/Ctrl + Enter để gửi)', id: 'Tulis pesan… (⌘/Ctrl + Enter untuk mengirim)' })}
          style={{
            flex: 1, padding: '10px 12px', borderRadius: 10, resize: 'vertical',
            border: '1px solid var(--border-color)', background: 'var(--bg-secondary)',
            color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit',
          }}
        />
        <button onClick={send} disabled={sending || !draft.trim()} className="btn btn-primary"
          style={{ fontSize: 13, padding: '10px 20px', cursor: 'pointer' }}>
          {sending
            ? tr(language, { ko: '전송 중...', en: 'Sending...', ja: '送信中...', th: 'กำลังส่ง...', vi: 'Đang gửi...', id: 'Mengirim...' })
            : tr(language, { ko: '보내기', en: 'Send', ja: '送信', th: 'ส่ง', vi: 'Gửi', id: 'Kirim' })}
        </button>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{draft.length}/4000</div>
    </div>
  )
}
