import { useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Enterprise plan → contract request form. Lands in the manager console
// (Subscriptions tab → contract requests) for follow-up.
const card: any = { background: 'var(--bg-secondary,#161615)', border: '1px solid var(--border-color,#2a2a28)', borderRadius: 14, padding: '22px 20px' }
const inputStyle: any = { padding: '10px 12px', borderRadius: 8, border: '1px solid var(--border-color,#2a2a28)', background: 'var(--bg-primary,#0e0e0d)', color: 'var(--text-primary,#fff)', fontSize: 14, width: '100%', marginBottom: 10 }
const primaryBtn: any = { padding: '10px 18px', borderRadius: 8, border: 'none', background: 'var(--accent-primary,#c26a45)', color: '#fff', fontWeight: 600, cursor: 'pointer', fontSize: 14, width: '100%' }

export function ContractPage({ userToken }: { userToken?: string | null }) {
  const { language } = useLanguage()
  const [form, setForm] = useState({ name: '', email: '', company: '', phone: '', message: '' })
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const T = {
    title: tr(language, { ko: '엔터프라이즈 문의', en: 'Enterprise — contact us', ja: 'Enterprise — お問い合わせ', th: 'Enterprise — ติดต่อเรา', vi: 'Enterprise — Liên hệ với chúng tôi', id: 'Enterprise — hubungi kami' }),
    subtitle: tr(language, { ko: '팀 규모와 요구사항을 알려주시면 맞춤 계약을 제안드립니다.', en: 'Tell us about your team and requirements — we\'ll propose a custom contract.', ja: 'チーム規模とご要件をお知らせいただければ、最適な契約をご提案します。', th: 'แจ้งขนาดทีมและความต้องการของคุณ แล้วเราจะเสนอสัญญาที่เหมาะกับคุณ', vi: 'Cho chúng tôi biết quy mô nhóm và yêu cầu của bạn — chúng tôi sẽ đề xuất hợp đồng phù hợp.', id: 'Ceritakan tentang tim dan kebutuhan Anda — kami akan mengajukan kontrak khusus.' }),
    name: tr(language, { ko: '이름', en: 'Name', ja: '氏名', th: 'ชื่อ', vi: 'Họ tên', id: 'Nama' }),
    email: tr(language, { ko: '이메일', en: 'Email', ja: 'メールアドレス', th: 'อีเมล', vi: 'Email', id: 'Email' }),
    company: tr(language, { ko: '회사명', en: 'Company', ja: '会社名', th: 'ชื่อบริษัท', vi: 'Tên công ty', id: 'Perusahaan' }),
    phone: tr(language, { ko: '전화번호 (선택)', en: 'Phone (optional)', ja: '電話番号（任意）', th: 'เบอร์โทรศัพท์ (ไม่บังคับ)', vi: 'Số điện thoại (tùy chọn)', id: 'Telepon (opsional)' }),
    message: tr(language, { ko: '요구사항', en: 'Requirements', ja: 'ご要件', th: 'ความต้องการ', vi: 'Yêu cầu', id: 'Kebutuhan' }),
    submit: tr(language, { ko: '문의 보내기', en: 'Send request', ja: '問い合わせを送信', th: 'ส่งคำขอ', vi: 'Gửi yêu cầu', id: 'Kirim permintaan' }),
    thanksTitle: tr(language, { ko: '접수되었습니다', en: 'Request received', ja: '受け付けました', th: 'รับคำขอแล้ว', vi: 'Đã nhận yêu cầu', id: 'Permintaan diterima' }),
    thanksBody: tr(language, { ko: '영업일 기준 1–2일 내에 연락드리겠습니다.', en: 'We\'ll get back to you within 1–2 business days.', ja: '1〜2営業日以内にご連絡いたします。', th: 'เราจะติดต่อกลับภายใน 1–2 วันทำการ', vi: 'Chúng tôi sẽ liên hệ lại trong vòng 1–2 ngày làm việc.', id: 'Kami akan menghubungi Anda dalam 1–2 hari kerja.' }),
    back: tr(language, { ko: '플랜 보기로 돌아가기', en: 'Back to plans', ja: 'プラン一覧に戻る', th: 'กลับไปที่แผนบริการ', vi: 'Quay lại danh sách gói', id: 'Kembali ke daftar paket' }),
  }

  async function submit() {
    if (!form.email.trim() || !form.name.trim()) return
    setBusy(true); setError('')
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (userToken) headers['Authorization'] = `Bearer ${userToken}`
      const r = await fetch(`${API_BASE}/subscriptions/contract`, {
        method: 'POST', headers, body: JSON.stringify(form),
      })
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || String(r.status))
      setSent(true)
    } catch (e: any) { setError(String(e?.message || e)) }
    setBusy(false)
  }

  return (
    <div style={{ maxWidth: 520, margin: '0 auto', padding: '48px 16px' }}>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, margin: 0 }}>🏢 {T.title}</h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary,#8a8073)', marginTop: 8 }}>{T.subtitle}</p>
      </div>
      {sent ? (
        <div style={{ ...card, textAlign: 'center' }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#22c55e' }}>✓ {T.thanksTitle}</div>
          <div style={{ fontSize: 14, marginTop: 8 }}>{T.thanksBody}</div>
          <div style={{ marginTop: 16 }}><Link to="/subscribe">{T.back}</Link></div>
        </div>
      ) : (
        <div style={card}>
          <input placeholder={T.name} value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} style={inputStyle} />
          <input placeholder={T.email} type="email" value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} style={inputStyle} />
          <input placeholder={T.company} value={form.company} onChange={e => setForm(p => ({ ...p, company: e.target.value }))} style={inputStyle} />
          <input placeholder={T.phone} value={form.phone} onChange={e => setForm(p => ({ ...p, phone: e.target.value }))} style={inputStyle} />
          <textarea placeholder={T.message} value={form.message} rows={5}
            onChange={e => setForm(p => ({ ...p, message: e.target.value }))} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }} />
          {error && <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 10 }}>⚠️ {error}</div>}
          <button style={primaryBtn} disabled={busy || !form.email.trim() || !form.name.trim()} onClick={submit}>{T.submit}</button>
          <div style={{ textAlign: 'center', marginTop: 12 }}><Link to="/subscribe" style={{ fontSize: 13 }}>{T.back}</Link></div>
        </div>
      )}
    </div>
  )
}

export default ContractPage
