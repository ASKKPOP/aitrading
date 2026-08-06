import { useEffect, useState } from 'react'

import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Phone verification control, extracted from SettingsPage so /welcome and
// /settings share ONE implementation of the send-code/verify state machine.
//
// Two modes:
//  * `phone` prop given (Settings): verifies THAT number; renders nothing
//    until a number exists — the surrounding card owns the input.
//  * no `phone` prop (Welcome): renders its own phone input, prefilled from
//    the member's stored number.

// Normalize a FastAPI error body to a renderable string (see authV2.tsx
// errMessage — validation errors arrive as detail: [{loc,msg,type}, …]).
function errMessage(data: any, fallback: string): string {
  const d = data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((e: any) => e?.msg || e?.message || JSON.stringify(e)).join('; ')
  }
  if (d && typeof d === 'object') return d.msg || d.message || JSON.stringify(d)
  return fallback
}

export default function PhoneVerifyCard({ userToken, phone, onVerified }: {
  userToken: string
  phone?: string
  onVerified?: () => void
}) {
  const { language } = useLanguage()
  const [me, setMe] = useState<{ phone: string | null; phone_verified: boolean } | null>(null)
  const [ownPhone, setOwnPhone] = useState('')
  const [verifyCode, setVerifyCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [phoneError, setPhoneError] = useState('')
  const [phoneBusy, setPhoneBusy] = useState(false)

  const ownInputMode = phone === undefined
  const targetPhone = ownInputMode ? ownPhone : phone

  const auth = () => ({ 'Authorization': `Bearer ${userToken}`, 'Content-Type': 'application/json' })

  const fetchMe = async () => {
    try {
      const res = await fetch(`${API_BASE}/users/me`, { headers: auth() })
      if (!res.ok) throw new Error(`${res.status}`)
      const data = await res.json()
      setMe({ phone: data.phone ?? null, phone_verified: !!data.phone_verified })
      if (ownInputMode) setOwnPhone(prev => prev || data.phone || '')
    } catch {
      // non-fatal — verification badges just don't render
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchMe() }, [userToken])

  const sendVerificationCode = async () => {
    setPhoneBusy(true)
    setPhoneError('')
    try {
      const res = await fetch(`${API_BASE}/users/phone/send-code`, {
        method: 'POST', headers: auth(), body: JSON.stringify({ phone: targetPhone }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) { setPhoneError(errMessage(data, `${res.status}`)); return }
      setCodeSent(true)
    } catch {
      setPhoneError(tr(language, { ko: '저장 실패', en: 'Save failed', ja: '保存失敗', th: 'บันทึกล้มเหลว', vi: 'Lưu thất bại', id: 'Gagal menyimpan' }))
    } finally {
      setPhoneBusy(false)
    }
  }

  const verifyPhoneCode = async () => {
    setPhoneBusy(true)
    setPhoneError('')
    try {
      const res = await fetch(`${API_BASE}/users/phone/verify`, {
        method: 'POST', headers: auth(), body: JSON.stringify({ code: verifyCode }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) { setPhoneError(errMessage(data, `${res.status}`)); return }
      setCodeSent(false)
      setVerifyCode('')
      await fetchMe()
      onVerified?.()
    } catch {
      setPhoneError(tr(language, { ko: '저장 실패', en: 'Save failed', ja: '保存失敗', th: 'บันทึกล้มเหลว', vi: 'Lưu thất bại', id: 'Gagal menyimpan' }))
    } finally {
      setPhoneBusy(false)
    }
  }

  const verified = !!(me?.phone_verified && me?.phone === targetPhone && targetPhone)
  if (verified) {
    return (
      <div style={{ marginTop: 12, fontSize: '12px', color: 'var(--text-secondary)' }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#22c55e' }}>
          ✓ {tr(language, { ko: '인증됨', en: 'Verified', ja: '確認済み', th: 'ยืนยันแล้ว', vi: 'Đã xác minh', id: 'Terverifikasi' })}
        </span>
        {' '}{targetPhone}
        <div style={{ marginTop: 4, color: 'var(--text-muted)' }}>
          {tr(language, { ko: '인증된 번호로 휴대폰 비밀번호 재설정을 사용할 수 있습니다.', en: 'A verified number lets you reset your password by SMS.', ja: '認証済みの番号でSMSによるパスワード再設定が使えます。', th: 'เบอร์ที่ยืนยันแล้วใช้รีเซ็ตรหัสผ่านทาง SMS ได้', vi: 'Số đã xác minh cho phép đặt lại mật khẩu qua SMS.', id: 'Nomor terverifikasi memungkinkan reset kata sandi lewat SMS.' })}
        </div>
      </div>
    )
  }
  if (!ownInputMode && !targetPhone) return null
  return (
    <div style={{ marginTop: 12, fontSize: '12px' }}>
      {ownInputMode && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
          <input type="tel" value={ownPhone} placeholder="+821012345678"
            onChange={e => setOwnPhone(e.target.value.trim())}
            style={{ padding: '8px 11px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13, width: 190 }} />
        </div>
      )}
      <span style={{ fontWeight: 700, color: 'var(--text-muted)' }}>
        {tr(language, { ko: '미인증', en: 'Not verified', ja: '未認証', th: 'ยังไม่ยืนยัน', vi: 'Chưa xác minh', id: 'Belum diverifikasi' })}
      </span>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
        {!codeSent && (
          <button onClick={sendVerificationCode} disabled={phoneBusy || !targetPhone}
            className="btn btn-secondary" style={{ fontSize: '12px', padding: '7px 14px', cursor: (phoneBusy || !targetPhone) ? 'not-allowed' : 'pointer' }}>
            {tr(language, { ko: '인증 코드 보내기', en: 'Send verification code', ja: '認証コードを送信', th: 'ส่งรหัสยืนยัน', vi: 'Gửi mã xác minh', id: 'Kirim kode verifikasi' })}
          </button>
        )}
        {codeSent && (
          <>
            <input type="text" inputMode="numeric" maxLength={6} value={verifyCode}
              onChange={e => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder={tr(language, { ko: '6자리 코드', en: '6-digit code', ja: '6桁のコード', th: 'รหัส 6 หลัก', vi: 'Mã 6 chữ số', id: 'Kode 6 digit' })}
              style={{ padding: '8px 11px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13, width: 120 }} />
            <button onClick={verifyPhoneCode} disabled={phoneBusy || verifyCode.length !== 6}
              className="btn btn-primary" style={{ fontSize: '12px', padding: '7px 16px', cursor: (phoneBusy || verifyCode.length !== 6) ? 'not-allowed' : 'pointer' }}>
              {tr(language, { ko: '인증하기', en: 'Verify', ja: '認証する', th: 'ยืนยัน', vi: 'Xác minh', id: 'Verifikasi' })}
            </button>
          </>
        )}
      </div>
      {phoneError && <div style={{ marginTop: 8, color: 'var(--error, #d03b3b)', fontSize: 12 }}>{phoneError}</div>}
    </div>
  )
}
