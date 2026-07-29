import { useEffect, useState } from 'react'

import { Link } from 'react-router-dom'

import { API_BASE, useLanguage } from '../appShared'
import { tr, type TrMap } from '../i18n'

// The member notification centre — everything notifications.py journaled for
// this account, newest first. Categories mirror the switches on the Settings
// page; a category switched off never lands here.

type Notification = {
  id: number
  category: string
  title: string
  body: string | null
  link: string | null
  read_at: string | null
  created_at: string
}

const CATEGORY_META: Record<string, { icon: string; color: string; label: TrMap }> = {
  trade: { icon: '◈', color: '#2a78d6', label: { ko: '거래', en: 'Trade', ja: '取引', th: 'เทรด', vi: 'Giao dịch', id: 'Transaksi' } },
  risk: { icon: '⚠', color: '#eab308', label: { ko: '리스크', en: 'Risk', ja: 'リスク', th: 'ความเสี่ยง', vi: 'Rủi ro', id: 'Risiko' } },
  watch: { icon: '◉', color: '#8b5cf6', label: { ko: '워치', en: 'Watch', ja: 'ウォッチ', th: 'เฝ้าดู', vi: 'Theo dõi', id: 'Pantauan' } },
  support: { icon: '💬', color: '#22c55e', label: { ko: '고객지원', en: 'Support', ja: 'サポート', th: 'สนับสนุน', vi: 'Hỗ trợ', id: 'Dukungan' } },
  announcement: { icon: '📣', color: '#c26a45', label: { ko: '공지', en: 'Announcement', ja: 'お知らせ', th: 'ประกาศ', vi: 'Thông báo', id: 'Pengumuman' } },
}

const fmtTime = (v: string) => String(v || '').replace('T', ' ').replace('Z', '').slice(0, 16)

// Only in-app paths may become a react-router <Link to>. A raw 'javascript:' or
// '//host' string renders as a real <a href> (React only warns), so a hostile
// link must never reach <Link>. The backend already sanitizes on write; this is
// defence-in-depth for any row that predates that or arrives another way.
const safeLink = (link: string | null): string | null =>
  link && link.startsWith('/') && !link.startsWith('//') ? link : null

export default function NotificationsPage({ userToken }: { userToken: string }) {
  const { language } = useLanguage()
  const [items, setItems] = useState<Notification[]>([])
  const [unread, setUnread] = useState(0)
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const auth = () => ({ 'Authorization': `Bearer ${userToken}`, 'Content-Type': 'application/json' })

  const load = async (mode: 'all' | 'unread' = filter) => {
    try {
      const res = await fetch(`${API_BASE}/notifications?limit=100&unread_only=${mode === 'unread'}`,
        { headers: auth() })
      if (!res.ok) throw new Error(String(res.status))
      const data = await res.json()
      setItems(data.notifications || [])
      setUnread(data.unread || 0)
      setError('')
    } catch {
      setError(tr(language, { ko: '알림을 불러오지 못했습니다', en: 'Failed to load notifications', ja: '通知を読み込めませんでした', th: 'โหลดการแจ้งเตือนไม่สำเร็จ', vi: 'Không tải được thông báo', id: 'Gagal memuat notifikasi' }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(filter) }, [userToken, filter])

  const markRead = async (body: { all: true } | { ids: number[] }) => {
    try {
      const res = await fetch(`${API_BASE}/notifications/read`, {
        method: 'POST', headers: auth(), body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(String(res.status))
      setError('')
      await load(filter)
    } catch {
      setError(tr(language, { ko: '읽음 표시에 실패했습니다', en: 'Failed to mark read', ja: '既読にできませんでした', th: 'ทำเครื่องหมายอ่านไม่สำเร็จ', vi: 'Không đánh dấu đã đọc được', id: 'Gagal menandai sudah dibaca' }))
    }
  }

  const markAll = () => markRead({ all: true })
  const markOne = (id: number) => markRead({ ids: [id] })

  const meta = (category: string) =>
    CATEGORY_META[category] || { icon: '•', color: 'var(--text-muted)', label: { ko: category, en: category, ja: category, th: category, vi: category, id: category } }

  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>
          {tr(language, { ko: '알림', en: 'Notifications', ja: '通知', th: 'การแจ้งเตือน', vi: 'Thông báo', id: 'Notifikasi' })}
        </h1>
        {unread > 0 && (
          <span style={{
            background: 'var(--accent-primary)', color: '#fff', borderRadius: 999,
            padding: '2px 10px', fontSize: 12, fontWeight: 700,
          }}>{unread}</span>
        )}
        <div style={{ flex: 1 }} />
        <Link to="/settings" className="btn btn-secondary" style={{ fontSize: 12, padding: '6px 14px' }}>
          ⚙ {tr(language, { ko: '알림 설정', en: 'Notification settings', ja: '通知設定', th: 'ตั้งค่าแจ้งเตือน', vi: 'Cài đặt thông báo', id: 'Pengaturan notifikasi' })}
        </Link>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '14px 0' }}>
        {(['all', 'unread'] as const).map(mode => (
          <button key={mode} onClick={() => setFilter(mode)}
            className={`control-pill ${filter === mode ? 'active' : ''}`} style={{ cursor: 'pointer' }}>
            {mode === 'all'
              ? tr(language, { ko: '전체', en: 'All', ja: 'すべて', th: 'ทั้งหมด', vi: 'Tất cả', id: 'Semua' })
              : tr(language, { ko: '읽지 않음', en: 'Unread', ja: '未読', th: 'ยังไม่อ่าน', vi: 'Chưa đọc', id: 'Belum dibaca' })}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        {unread > 0 && (
          <button onClick={markAll} className="btn btn-secondary" style={{ fontSize: 12, padding: '6px 14px', cursor: 'pointer' }}>
            {tr(language, { ko: '모두 읽음 표시', en: 'Mark all read', ja: 'すべて既読', th: 'ทำเครื่องหมายอ่านทั้งหมด', vi: 'Đánh dấu đã đọc', id: 'Tandai semua sudah dibaca' })}
          </button>
        )}
      </div>

      {error && <div className="card" style={{ padding: 16, color: 'var(--error, #d03b3b)' }}>{error}</div>}
      {loading && <div className="card" style={{ padding: 16 }}>{tr(language, { ko: '불러오는 중...', en: 'Loading...', ja: '読み込み中...', th: 'กำลังโหลด...', vi: 'Đang tải...', id: 'Memuat...' })}</div>}

      {!loading && !error && items.length === 0 && (
        <div className="card" style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13.5 }}>
          {filter === 'unread'
            ? tr(language, { ko: '읽지 않은 알림이 없습니다.', en: 'No unread notifications.', ja: '未読の通知はありません。', th: 'ไม่มีการแจ้งเตือนที่ยังไม่อ่าน', vi: 'Không có thông báo chưa đọc.', id: 'Tidak ada notifikasi yang belum dibaca.' })
            : tr(language, { ko: '아직 알림이 없습니다. 거래·리스크·공지 알림이 여기에 표시됩니다.', en: 'No notifications yet. Trade, risk and announcement alerts appear here.', ja: 'まだ通知はありません。取引・リスク・お知らせがここに表示されます。', th: 'ยังไม่มีการแจ้งเตือน การเทรด ความเสี่ยง และประกาศจะแสดงที่นี่', vi: 'Chưa có thông báo. Cảnh báo giao dịch, rủi ro và thông báo sẽ hiện ở đây.', id: 'Belum ada notifikasi. Peringatan transaksi, risiko, dan pengumuman akan muncul di sini.' })}
        </div>
      )}

      {items.map(n => {
        const m = meta(n.category)
        const unreadItem = !n.read_at
        return (
          <div key={n.id} className="card" style={{
            padding: '13px 16px', marginBottom: 8, display: 'flex', gap: 12,
            borderLeft: `3px solid ${unreadItem ? m.color : 'transparent'}`,
          }}>
            <div style={{ fontSize: 17, lineHeight: 1.3, color: m.color }}>{m.icon}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 14, fontWeight: unreadItem ? 700 : 500 }}>{n.title}</span>
                <span style={{
                  fontSize: 10, fontWeight: 700, borderRadius: 999, padding: '2px 8px',
                  background: 'var(--bg-secondary, rgba(0,0,0,0.05))', color: m.color,
                }}>{tr(language, m.label)}</span>
              </div>
              {n.body && (
                <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 4, lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>
                  {n.body}
                </div>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 6 }}>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {fmtTime(n.created_at)}
                </span>
                {safeLink(n.link) && (
                  <Link to={safeLink(n.link)!} style={{ fontSize: 11.5, color: 'var(--accent-primary)' }}>
                    {tr(language, { ko: '열기', en: 'Open', ja: '開く', th: 'เปิด', vi: 'Mở', id: 'Buka' })} →
                  </Link>
                )}
                {unreadItem && (
                  <button onClick={() => markOne(n.id)} style={{
                    background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                    fontSize: 11.5, color: 'var(--text-muted)',
                  }}>
                    {tr(language, { ko: '읽음 표시', en: 'Mark read', ja: '既読にする', th: 'ทำเครื่องหมายอ่าน', vi: 'Đánh dấu đã đọc', id: 'Tandai sudah dibaca' })}
                  </button>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
