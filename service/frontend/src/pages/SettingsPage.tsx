import { useEffect, useState } from 'react'

import { Link } from 'react-router-dom'

import { API_BASE, useLanguage } from '../appShared'
import { LANGUAGES, tr } from '../i18n'

type ApiTarget = {
  target: string
  label: string
  description: string
  requires_key: boolean
  fields: string[]
  configured: boolean
  enabled: boolean
  masked_key: string | null
  config: Record<string, string>
  updated_at: string | null
}

const LLM_PROVIDERS = ['openai', 'gemini', 'grok', 'qwen', 'glm', 'openrouter', 'anthropic', 'local']

export default function SettingsPage({ userToken, userInfo, onSignOut }: {
  userToken: string
  userInfo: any
  onSignOut: () => void
}) {
  const { language, setLanguage } = useLanguage()
  const [targets, setTargets] = useState<ApiTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savedMsg, setSavedMsg] = useState('')
  // per-target editable state
  const [drafts, setDrafts] = useState<Record<string, { api_key: string; provider: string; model: string }>>({})
  const [saving, setSaving] = useState<string | null>(null)

  const auth = () => ({ 'Authorization': `Bearer ${userToken}`, 'Content-Type': 'application/json' })

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/users/settings`, { headers: auth() })
      if (!res.ok) throw new Error(`${res.status}`)
      const data = await res.json()
      setTargets(data.targets || [])
      setError('')
    } catch {
      setError(tr(language, { ko: '설정을 불러오지 못했습니다', en: 'Failed to load settings', ja: '設定を読み込めませんでした', th: 'โหลดการตั้งค่าไม่สำเร็จ', vi: 'Không tải được cài đặt' }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [userToken])

  const flash = (msg: string) => {
    setSavedMsg(msg)
    setTimeout(() => setSavedMsg(''), 2500)
  }

  const saveTarget = async (t: ApiTarget) => {
    const draft = drafts[t.target] || { api_key: '', provider: t.config.provider || '', model: t.config.model || '' }
    const body: any = {}
    if (draft.api_key) body.api_key = draft.api_key
    if (t.fields.length > 0) {
      body.config = { provider: draft.provider, model: draft.model }
    }
    setSaving(t.target)
    try {
      const res = await fetch(`${API_BASE}/users/settings/api/${t.target}`, {
        method: 'PUT', headers: auth(), body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      setDrafts(d => ({ ...d, [t.target]: { ...draft, api_key: '' } }))
      flash(tr(language, { ko: '저장되었습니다', en: 'Saved', ja: '保存しました', th: 'บันทึกแล้ว', vi: 'Đã lưu' }))
      await load()
    } catch {
      flash(tr(language, { ko: '저장에 실패했습니다', en: 'Save failed', ja: '保存に失敗', th: 'บันทึกไม่สำเร็จ', vi: 'Lưu thất bại' }))
    } finally {
      setSaving(null)
    }
  }

  const toggleTarget = async (t: ApiTarget) => {
    setSaving(t.target)
    try {
      await fetch(`${API_BASE}/users/settings/api/${t.target}`, {
        method: 'PUT', headers: auth(), body: JSON.stringify({ enabled: !t.enabled }),
      })
      await load()
    } finally {
      setSaving(null)
    }
  }

  const clearTarget = async (t: ApiTarget) => {
    setSaving(t.target)
    try {
      await fetch(`${API_BASE}/users/settings/api/${t.target}`, { method: 'DELETE', headers: auth() })
      flash(tr(language, { ko: '키가 삭제되었습니다', en: 'Key removed', ja: 'キーを削除しました', th: 'ลบคีย์แล้ว', vi: 'Đã xóa khóa' }))
      await load()
    } finally {
      setSaving(null)
    }
  }

  const draftOf = (t: ApiTarget) =>
    drafts[t.target] || { api_key: '', provider: t.config.provider || '', model: t.config.model || '' }

  const setDraft = (target: string, patch: Partial<{ api_key: string; provider: string; model: string }>) => {
    setDrafts(d => {
      const t = targets.find(x => x.target === target)
      const cur = d[target] || { api_key: '', provider: t?.config.provider || '', model: t?.config.model || '' }
      return { ...d, [target]: { ...cur, ...patch } }
    })
  }

  const sectionTitle = (ko: string, en: string) => (
    <h2 style={{ fontSize: '16px', fontWeight: 700, margin: '26px 0 4px' }}>
      {tr(language, { ko, en })}
    </h2>
  )

  return (
    <div style={{ maxWidth: '760px' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 800, marginBottom: '2px' }}>
        {tr(language, { ko: '설정', en: 'Settings', ja: '設定', th: 'ตั้งค่า', vi: 'Cài đặt' })}
      </h1>
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
        {tr(language, {
          ko: '계정 · 환경설정 · 데이터/AI API 구성',
          en: 'Account · preferences · data/AI API configuration',
          ja: 'アカウント · 環境設定 · API構成',
          th: 'บัญชี · การตั้งค่า · การกำหนดค่า API',
          vi: 'Tài khoản · tùy chọn · cấu hình API',
        })}
      </div>

      {savedMsg && (
        <div style={{
          position: 'fixed', top: '18px', right: '18px', zIndex: 50,
          background: 'var(--accent-primary)', color: '#fff', borderRadius: '10px',
          padding: '8px 16px', fontSize: '13px', fontWeight: 600,
        }}>
          {savedMsg}
        </div>
      )}

      {/* ── Account ─────────────────────────────────────── */}
      {sectionTitle('계정', 'Account')}
      <div className="card" style={{ padding: '14px 16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 18px', fontSize: '13.5px' }}>
          <span style={{ color: 'var(--text-muted)' }}>{tr(language, { ko: '이메일', en: 'Email', ja: 'メール', th: 'อีเมล', vi: 'Email' })}</span>
          <span style={{ fontWeight: 600 }}>{userInfo?.email || '—'}</span>
          <span style={{ color: 'var(--text-muted)' }}>{tr(language, { ko: '포인트', en: 'Points', ja: 'ポイント', th: 'พอยต์', vi: 'Điểm' })}</span>
          <span style={{ fontWeight: 600 }}>{userInfo?.points ?? 0}</span>
        </div>
        <div style={{ display: 'flex', gap: '10px', marginTop: '14px', flexWrap: 'wrap' }}>
          <Link to="/my-trading" className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 14px' }}>
            {tr(language, { ko: '내 계정 · 프로필', en: 'My Account · Profile', ja: 'マイアカウント', th: 'บัญชีของฉัน', vi: 'Tài khoản' })}
          </Link>
          <Link to="/auth/mfa/setup" className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 14px' }}>
            {tr(language, { ko: '2단계 인증(MFA) 설정', en: 'Set up MFA', ja: 'MFA設定', th: 'ตั้งค่า MFA', vi: 'Cài đặt MFA' })}
          </Link>
          <button onClick={onSignOut} className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 14px', cursor: 'pointer' }}>
            {tr(language, { ko: '로그아웃', en: 'Sign out', ja: 'ログアウト', th: 'ออกจากระบบ', vi: 'Đăng xuất' })}
          </button>
        </div>
      </div>

      {/* ── Preferences ─────────────────────────────────── */}
      {sectionTitle('환경설정', 'Preferences')}
      <div className="card" style={{ padding: '14px 16px' }}>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>
          {tr(language, { ko: '언어', en: 'Language', ja: '言語', th: 'ภาษา', vi: 'Ngôn ngữ' })}
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {LANGUAGES.map(lang => (
            <button
              key={lang.value}
              onClick={() => setLanguage(lang.value)}
              className={`control-pill ${language === lang.value ? 'active' : ''}`}
              style={{ cursor: 'pointer' }}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── API configuration per target ────────────────── */}
      {sectionTitle('API 구성 — 데이터 · AI 소스별 설정', 'API Configuration — per data / AI target')}
      <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        {tr(language, {
          ko: '키가 없어도 공개 API 소스로 전체 파이프라인이 동작합니다. 키를 등록하면 해당 소스의 데이터가 더 깊어집니다. 키는 마스킹되어 저장되며 전체 값은 다시 표시되지 않습니다.',
          en: 'The whole pipeline runs on public APIs without any key. Adding keys deepens that source. Keys are stored masked and never displayed again in full.',
          ja: 'キーなしでも公開APIで全パイプラインが動作します。キーは保存後マスキングされます。',
          th: 'ไปป์ไลน์ทำงานได้โดยไม่ต้องใช้คีย์ คีย์จะถูกปิดบังหลังบันทึก',
          vi: 'Toàn bộ pipeline chạy được không cần khóa. Khóa được che sau khi lưu.',
        })}
      </div>

      {loading && <div className="card" style={{ padding: '16px' }}>{tr(language, { ko: '불러오는 중...', en: 'Loading...', ja: '読み込み中...', th: 'กำลังโหลด...', vi: 'Đang tải...' })}</div>}
      {error && <div className="card" style={{ padding: '16px', color: 'var(--danger, #d03b3b)' }}>{error}</div>}

      {targets.map(t => {
        const draft = draftOf(t)
        return (
          <div key={t.target} className="card" style={{ padding: '14px 16px', marginBottom: '10px', opacity: t.enabled ? 1 : 0.55 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <div style={{ fontWeight: 700, fontSize: '14px' }}>{t.label}</div>
              <span style={{
                fontSize: '10.5px', fontWeight: 700, borderRadius: '999px', padding: '2px 9px',
                background: t.requires_key
                  ? (t.configured ? 'rgba(12,163,12,0.14)' : 'rgba(237,161,0,0.16)')
                  : 'rgba(42,120,214,0.13)',
                color: t.requires_key ? (t.configured ? 'var(--success, #0ca30c)' : '#a16800') : 'var(--accent-primary)',
              }}>
                {t.requires_key
                  ? (t.configured
                    ? tr(language, { ko: '키 등록됨', en: 'Key set', ja: 'キー設定済み', th: 'ตั้งคีย์แล้ว', vi: 'Đã đặt khóa' })
                    : tr(language, { ko: '키 미등록 (선택)', en: 'No key (optional)', ja: 'キー未設定', th: 'ยังไม่มีคีย์', vi: 'Chưa có khóa' }))
                  : tr(language, { ko: '공개 API — 키 불필요', en: 'Public API — no key needed', ja: '公開API', th: 'API สาธารณะ', vi: 'API công khai' })}
              </span>
              <div style={{ flex: 1 }} />
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                <input type="checkbox" checked={t.enabled} disabled={saving === t.target} onChange={() => toggleTarget(t)} />
                {tr(language, { ko: '사용', en: 'Enabled', ja: '有効', th: 'เปิดใช้', vi: 'Bật' })}
              </label>
            </div>
            <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', margin: '6px 0 0' }}>{t.description}</div>

            {t.requires_key && (
              <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {t.fields.includes('provider') && (
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <select
                      value={draft.provider}
                      onChange={e => setDraft(t.target, { provider: e.target.value })}
                      style={{ padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-color, rgba(0,0,0,0.15))', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '13px' }}
                    >
                      <option value="">{tr(language, { ko: '프로바이더 선택', en: 'Select provider', ja: 'プロバイダー選択', th: 'เลือกผู้ให้บริการ', vi: 'Chọn nhà cung cấp' })}</option>
                      {LLM_PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <input
                      type="text"
                      placeholder={tr(language, { ko: '모델 (예: gpt-4o)', en: 'Model (e.g. gpt-4o)', ja: 'モデル', th: 'โมเดล', vi: 'Mô hình' })}
                      value={draft.model}
                      onChange={e => setDraft(t.target, { model: e.target.value })}
                      style={{ flex: 1, minWidth: '160px', padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-color, rgba(0,0,0,0.15))', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '13px' }}
                    />
                  </div>
                )}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={t.masked_key
                      ? tr(language, { ko: `저장된 키 ${t.masked_key} — 새 키 입력 시 교체`, en: `Saved key ${t.masked_key} — enter new key to replace`, ja: `保存済み ${t.masked_key}`, th: `คีย์ที่บันทึก ${t.masked_key}`, vi: `Khóa đã lưu ${t.masked_key}` })
                      : tr(language, { ko: 'API 키 입력', en: 'Enter API key', ja: 'APIキー入力', th: 'ใส่คีย์ API', vi: 'Nhập khóa API' })}
                    value={draft.api_key}
                    onChange={e => setDraft(t.target, { api_key: e.target.value })}
                    style={{ flex: 1, minWidth: '200px', padding: '7px 10px', borderRadius: '8px', border: '1px solid var(--border-color, rgba(0,0,0,0.15))', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '13px', fontFamily: 'var(--font-mono)' }}
                  />
                  <button
                    onClick={() => saveTarget(t)}
                    disabled={saving === t.target || (!draft.api_key && t.fields.length === 0)}
                    className="btn btn-primary"
                    style={{ fontSize: '12px', padding: '7px 16px', cursor: 'pointer' }}
                  >
                    {saving === t.target
                      ? tr(language, { ko: '저장 중...', en: 'Saving...', ja: '保存中...', th: 'กำลังบันทึก...', vi: 'Đang lưu...' })
                      : tr(language, { ko: '저장', en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu' })}
                  </button>
                  {t.configured && (
                    <button
                      onClick={() => clearTarget(t)}
                      disabled={saving === t.target}
                      className="btn btn-secondary"
                      style={{ fontSize: '12px', padding: '7px 12px', cursor: 'pointer' }}
                    >
                      {tr(language, { ko: '키 삭제', en: 'Remove key', ja: 'キー削除', th: 'ลบคีย์', vi: 'Xóa khóa' })}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })}

      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '14px', lineHeight: 1.6 }}>
        {tr(language, {
          ko: '참고: 자동매매 규칙별 상세 설정(주기·최소 신뢰도·자동체결)은 자동매매 페이지에서, 리스크 한도(일일 손실·심볼 노출·SL/TP)는 에이전트 API(/api/risk/limits)에서 관리합니다.',
          en: 'Note: per-rule automation settings (interval, min confidence, auto-execute) live on the Automation page; risk limits (daily loss, exposure, SL/TP) via the agent API (/api/risk/limits).',
          ja: '自動売買ルール別設定は自動売買ページで管理します。',
          th: 'การตั้งค่ากฎอัตโนมัติอยู่ที่หน้า Automation',
          vi: 'Cài đặt quy tắc tự động ở trang Automation.',
        })}
      </div>
    </div>
  )
}
