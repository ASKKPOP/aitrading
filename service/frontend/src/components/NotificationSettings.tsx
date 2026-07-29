import { useEffect, useState } from 'react'

import { API_BASE, useLanguage } from '../appShared'
import { tr, type TrMap } from '../i18n'

// Per-category notification switches, laid out like iOS Settings →
// Notifications: one grouped list, one switch per category. Email and SMS are
// not split — a member is one person, so a category that is on reaches every
// channel they have registered. Keys come from the backend (notifications.py).

type Category = {
  key: string
  label: string
  description: string
  enabled: boolean
}

export function Switch({ checked, onChange, disabled, label }: {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      style={{
        width: 46, height: 28, flexShrink: 0, borderRadius: 999, border: 'none', padding: 2,
        cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1,
        background: checked ? 'var(--success, #22c55e)' : 'var(--border-color, rgba(120,120,128,0.32))',
        transition: 'background 0.2s ease',
        display: 'flex', alignItems: 'center',
      }}
    >
      <span style={{
        width: 24, height: 24, borderRadius: '50%', background: '#fff',
        boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
        transform: `translateX(${checked ? 18 : 0}px)`,
        transition: 'transform 0.2s ease',
      }} />
    </button>
  )
}

const LABELS: Record<string, TrMap> = {
  trade: { ko: '거래 활동', en: 'Trade activity', ja: '取引アクティビティ', th: 'กิจกรรมการเทรด', vi: 'Hoạt động giao dịch', id: 'Aktivitas transaksi' },
  risk: { ko: '리스크 · 안전', en: 'Risk & safety', ja: 'リスク・安全', th: 'ความเสี่ยงและความปลอดภัย', vi: 'Rủi ro & an toàn', id: 'Risiko & keamanan' },
  watch: { ko: '워치 알림', en: 'Watches', ja: 'ウォッチ', th: 'การเฝ้าดู', vi: 'Theo dõi', id: 'Pantauan' },
  auto_trading_reports: { ko: '자동매매 리포트', en: 'Auto-trading reports', ja: '自動売買レポート', th: 'รายงานการเทรดอัตโนมัติ', vi: 'Báo cáo giao dịch tự động', id: 'Laporan trading otomatis' },
  auto_trading_safety: { ko: '자동매매 안전', en: 'Auto-trading safety', ja: '自動売買の安全', th: 'ความปลอดภัยการเทรดอัตโนมัติ', vi: 'An toàn giao dịch tự động', id: 'Keamanan trading otomatis' },
  support: { ko: '고객지원 답변', en: 'Support replies', ja: 'サポート返信', th: 'การตอบกลับจากฝ่ายสนับสนุน', vi: 'Phản hồi hỗ trợ', id: 'Balasan dukungan' },
  announcement: { ko: '공지사항', en: 'Announcements', ja: 'お知らせ', th: 'ประกาศ', vi: 'Thông báo', id: 'Pengumuman' },
}

const DESCRIPTIONS: Record<string, TrMap> = {
  trade: { ko: '자동매매 규칙의 체결과 포지션 종료.', en: 'Order fills and position closes from your automation rules.', ja: '自動売買ルールの約定とポジション決済。', th: 'การจับคู่คำสั่งและการปิดสถานะจากกฎอัตโนมัติ', vi: 'Khớp lệnh và đóng vị thế từ quy tắc tự động.', id: 'Eksekusi order dan penutupan posisi dari aturan otomatisasi Anda.' },
  risk: { ko: '서킷 브레이커 정지와 사전 검증 거부.', en: 'Circuit-breaker halts and rejected pre-trade verifications.', ja: 'サーキットブレーカー停止と事前検証の却下。', th: 'การหยุดเซอร์กิตเบรกเกอร์และการปฏิเสธการตรวจสอบ', vi: 'Dừng ngắt mạch và từ chối kiểm chứng trước lệnh.', id: 'Penghentian oleh pemutus sirkuit dan verifikasi pra-transaksi yang ditolak.' },
  watch: { ko: '설정한 가격·지표 워치가 발동할 때.', en: 'Price and indicator watches you configured firing.', ja: '設定した価格・指標ウォッチの発動。', th: 'การเฝ้าดูราคาและตัวชี้วัดที่คุณตั้งไว้ทำงาน', vi: 'Theo dõi giá và chỉ báo bạn đã cấu hình kích hoạt.', id: 'Pantauan harga dan indikator yang Anda atur ketika terpicu.' },
  auto_trading_reports: { ko: '트레이딩 런의 정기 손익 리포트.', en: 'Scheduled P&L digests from your trading runs.', ja: 'トレーディングランの定期損益レポート。', th: 'สรุปกำไรขาดทุนตามกำหนดเวลาจากรันการเทรด', vi: 'Báo cáo lãi/lỗ định kỳ từ các phiên giao dịch.', id: 'Ringkasan laba rugi terjadwal dari run trading Anda.' },
  auto_trading_safety: { ko: '런 중단, 손익 임계값 발동, 안전 일시정지.', en: 'Run stop events, profit/loss threshold triggers, and safety pauses.', ja: 'ラン停止、損益しきい値の発動、安全一時停止。', th: 'การหยุดรัน การแตะเกณฑ์กำไรขาดทุน และการหยุดเพื่อความปลอดภัย', vi: 'Sự kiện dừng phiên, ngưỡng lãi/lỗ và tạm dừng an toàn.', id: 'Peristiwa stop pada run, pemicu ambang laba/rugi, dan jeda keamanan.' },
  support: { ko: '고객지원 대화에 운영팀이 답장할 때.', en: 'Replies from the Sooppiy team in your support conversation.', ja: 'サポート会話での運営チームの返信。', th: 'การตอบกลับจากทีม Sooppiy ในการสนทนาสนับสนุน', vi: 'Phản hồi từ đội ngũ Sooppiy trong cuộc trò chuyện hỗ trợ.', id: 'Balasan dari tim Sooppiy dalam percakapan dukungan Anda.' },
  announcement: { ko: '플랫폼 공지와 서비스 안내.', en: 'Platform announcements and service notices from Sooppiy.', ja: 'プラットフォームのお知らせとサービス通知。', th: 'ประกาศแพลตฟอร์มและการแจ้งบริการ', vi: 'Thông báo nền tảng và thông báo dịch vụ.', id: 'Pengumuman platform dan pemberitahuan layanan dari Sooppiy.' },
}

export default function NotificationSettings({ userToken }: { userToken: string }) {
  const { language } = useLanguage()
  const [categories, setCategories] = useState<Category[]>([])
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const auth = () => ({ 'Authorization': `Bearer ${userToken}`, 'Content-Type': 'application/json' })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/notifications/settings`, { headers: auth() })
      .then(r => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then(d => {
        if (cancelled) return
        setCategories(d.categories || [])
        setPhone(d.phone || '')
        setEmail(d.email || '')
        setError('')
      })
      .catch(() => {
        if (!cancelled) setError(tr(language, { ko: '알림 설정을 불러오지 못했습니다', en: 'Failed to load notification settings', ja: '通知設定を読み込めませんでした', th: 'โหลดการตั้งค่าแจ้งเตือนไม่สำเร็จ', vi: 'Không tải được cài đặt thông báo', id: 'Gagal memuat pengaturan notifikasi' }))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [userToken])

  // Optimistic: flip locally, persist, roll back on failure.
  const patch = async (key: string, value: boolean) => {
    const previous = categories
    setCategories(cs => cs.map(c => c.key === key ? { ...c, enabled: value } : c))
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/notifications/settings`, {
        method: 'PUT', headers: auth(),
        body: JSON.stringify({ categories: { [key]: { enabled: value } } }),
      })
      if (!res.ok) throw new Error(String(res.status))
      setCategories((await res.json()).categories || [])
      setError('')
    } catch {
      setCategories(previous)
      setError(tr(language, { ko: '저장 실패 — 다시 시도해 주세요', en: 'Save failed — please try again', ja: '保存に失敗しました', th: 'บันทึกไม่สำเร็จ', vi: 'Lưu thất bại', id: 'Gagal menyimpan — silakan coba lagi' }))
    } finally {
      setBusy(false)
    }
  }

  const labelOf = (c: Category) => LABELS[c.key] ? tr(language, LABELS[c.key]) : c.label
  const descOf = (c: Category) => DESCRIPTIONS[c.key] ? tr(language, DESCRIPTIONS[c.key]) : c.description

  if (loading) {
    return <div className="card" style={{ padding: '16px' }}>{tr(language, { ko: '불러오는 중...', en: 'Loading...', ja: '読み込み中...', th: 'กำลังโหลด...', vi: 'Đang tải...', id: 'Memuat...' })}</div>
  }

  const row: any = {
    display: 'flex', alignItems: 'flex-start', gap: 14, padding: '14px 16px',
    borderBottom: '1px solid var(--border-color, rgba(0,0,0,0.08))',
  }
  // Where an enabled category lands. Shown once per row instead of a toggle
  // per channel, so the destinations stay visible without being separable.
  const destinations = [
    email,
    phone || tr(language, { ko: 'SMS — 아래에서 전화번호를 등록하세요', en: 'SMS — add a phone number below', ja: 'SMS — 下で電話番号を登録', th: 'SMS — เพิ่มเบอร์โทรด้านล่าง', vi: 'SMS — thêm số điện thoại bên dưới', id: 'SMS — tambahkan nomor telepon di bawah' }),
  ].filter(Boolean).join(' · ')

  return (
    <div>
      {error && <div style={{ color: 'var(--error, #d03b3b)', fontSize: 12.5, marginBottom: 8 }}>{error}</div>}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {categories.map((c, i) => (
          <div key={c.key} style={{ opacity: busy ? 0.75 : 1, transition: 'opacity 0.15s' }}>
            <div style={{ ...row, borderTop: i === 0 ? 'none' : undefined }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{labelOf(c)}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3, lineHeight: 1.5 }}>
                  {descOf(c)}
                </div>
                {c.enabled && destinations && (
                  <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 5 }}>
                    {destinations}
                  </div>
                )}
              </div>
              <Switch checked={c.enabled} disabled={busy} label={labelOf(c)}
                onChange={v => patch(c.key, v)} />
            </div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 10, lineHeight: 1.6 }}>
        {tr(language, {
          ko: '끈 항목은 알림함에도 기록되지 않습니다. 외부 발송(이메일·SMS)에는 시간당 제한이 적용됩니다.',
          en: 'A category switched off is not even journaled to your notification centre. External sends (email/SMS) are rate-limited hourly.',
          ja: 'オフにしたカテゴリーは通知センターにも記録されません。外部送信は時間あたり制限があります。',
          th: 'หมวดที่ปิดจะไม่ถูกบันทึกในศูนย์แจ้งเตือน การส่งภายนอกมีการจำกัดต่อชั่วโมง',
          vi: 'Danh mục đã tắt sẽ không được ghi vào trung tâm thông báo. Gửi bên ngoài bị giới hạn theo giờ.',
          id: 'Kategori yang dinonaktifkan bahkan tidak dicatat ke pusat notifikasi Anda. Pengiriman eksternal (email/SMS) dibatasi per jam.',
        })}
      </div>
    </div>
  )
}
