/**
 * Region + language, asked once on first sign-in and editable forever after.
 *
 * Region is a COUNTRY and is deliberately not derived from language: English
 * alone serves the USA, Canada, Australia and Singapore — four countries and
 * four clocks. It decides which markets a member may hold and, just as
 * visibly, what time their markets open.
 *
 * The server pre-selects from the signup-time IP guess and applies nothing
 * until the member answers, so an unplaceable member stays `region = null`
 * rather than being dropped into a jurisdiction.
 */
import { useEffect, useState } from 'react'
import { API_BASE } from '../appShared'
import { LANGUAGES, tr, type Language } from '../i18n'

type RegionOption = {
  region: string
  name: string
  timezone: string
  suggested_lang: Language
}

type LocaleOptions = {
  regions: RegionOption[]
  region: string | null
  timezone: string | null
  lang: Language
  locale_confirmed: boolean
  suggested_region: string | null
}

const T = {
  title: { ko: '지역과 언어를 선택하세요', en: 'Choose your region and language',
    ja: '地域と言語を選択してください', th: 'เลือกภูมิภาคและภาษาของคุณ',
    vi: 'Chọn khu vực và ngôn ngữ của bạn',
    id: 'Pilih wilayah dan bahasa Anda' },
  why: {
    ko: '지역에 따라 거래 가능한 시장과 시장이 열리는 시각이 달라집니다. 언제든지 설정에서 바꿀 수 있습니다.',
    en: 'Your region decides which markets you can trade and when they open in your own clock. You can change it any time in Settings.',
    ja: '地域によって取引できる市場と、市場が開く時刻が変わります。設定からいつでも変更できます。',
    th: 'ภูมิภาคของคุณกำหนดว่าคุณเทรดตลาดใดได้ และตลาดเปิดกี่โมงตามเวลาของคุณ เปลี่ยนได้ทุกเมื่อในการตั้งค่า',
    vi: 'Khu vực quyết định bạn giao dịch được thị trường nào và thị trường mở lúc mấy giờ theo giờ của bạn. Bạn có thể đổi bất cứ lúc nào trong Cài đặt.',
    id: 'Wilayah Anda menentukan pasar mana yang bisa Anda perdagangkan dan kapan pasar itu buka menurut jam Anda sendiri. Anda dapat mengubahnya kapan saja di Pengaturan.' },
  region: { ko: '지역', en: 'Region', ja: '地域', th: 'ภูมิภาค', vi: 'Khu vực', id: 'Wilayah' },
  lang: { ko: '언어', en: 'Language', ja: '言語', th: 'ภาษา', vi: 'Ngôn ngữ', id: 'Bahasa' },
  save: { ko: '저장', en: 'Save', ja: '保存', th: 'บันทึก', vi: 'Lưu', id: 'Simpan' },
  saving: { ko: '저장 중…', en: 'Saving…', ja: '保存中…', th: 'กำลังบันทึก…', vi: 'Đang lưu…', id: 'Menyimpan…' },
  saved: { ko: '저장되었습니다', en: 'Saved', ja: '保存しました', th: 'บันทึกแล้ว', vi: 'Đã lưu', id: 'Tersimpan' },
  failed: { ko: '저장하지 못했습니다. 다시 시도하세요.', en: 'Could not save. Please try again.',
    ja: '保存できませんでした。もう一度お試しください。', th: 'บันทึกไม่สำเร็จ กรุณาลองใหม่',
    vi: 'Không lưu được. Vui lòng thử lại.',
    id: 'Tidak dapat menyimpan. Silakan coba lagi.' },
  pick: { ko: '지역을 선택하세요', en: 'Select a region', ja: '地域を選択してください',
    th: 'กรุณาเลือกภูมิภาค', vi: 'Vui lòng chọn khu vực', id: 'Pilih wilayah' },
  tz: { ko: '표시 시간대', en: 'Times shown in', ja: '表示タイムゾーン',
    th: 'แสดงเวลาตาม', vi: 'Hiển thị giờ theo', id: 'Waktu ditampilkan dalam' },
}

async function loadOptions(token: string): Promise<LocaleOptions | null> {
  try {
    const r = await fetch(`${API_BASE}/users/locale/options`,
      { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) return null
    return await r.json()
  } catch { return null }
}

/** The picker body, shared by the first-run dialog and the settings card. */
export function RegionPicker({ token, language, onSaved, compact }: {
  token: string
  language: Language
  onSaved?: (region: string, lang: Language, timezone: string) => void
  compact?: boolean
}) {
  const [opts, setOpts] = useState<LocaleOptions | null>(null)
  const [region, setRegion] = useState<string>('')
  const [lang, setLang] = useState<Language>(language)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  useEffect(() => {
    let dead = false
    loadOptions(token).then(o => {
      if (dead || !o) return
      setOpts(o)
      // Already chosen wins; otherwise the geo guess is only a pre-selection.
      setRegion(o.region || o.suggested_region || '')
      setLang(o.lang || language)
    })
    return () => { dead = true }
  }, [token])

  const chosen = opts?.regions.find(r => r.region === region)

  const save = async () => {
    if (!region) return
    setState('saving')
    try {
      const r = await fetch(`${API_BASE}/users/locale`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ region, lang }),
      })
      if (!r.ok) { setState('error'); return }
      const body = await r.json()
      setState('saved')
      onSaved?.(body.region, body.lang, body.timezone)
    } catch { setState('error') }
  }

  if (!opts) return null

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 7 }}>
        {tr(language, T.region)}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
        {opts.regions.map(r => (
          <button key={r.region} onClick={() => {
            setRegion(r.region)
            setState('idle')
          }}
            className={`control-pill ${region === r.region ? 'active' : ''}`}
            style={{ cursor: 'pointer' }}>
            {r.name}
          </button>
        ))}
      </div>
      {chosen && (
        <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 12 }}>
          {tr(language, T.tz)} · {chosen.timezone}
        </div>
      )}

      <div style={{ fontSize: 12, color: 'var(--text-muted)', margin: '10px 0 7px' }}>
        {tr(language, T.lang)}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {LANGUAGES.map(l => (
          <button key={l.value} onClick={() => { setLang(l.value); setState('idle') }}
            className={`control-pill ${lang === l.value ? 'active' : ''}`}
            style={{ cursor: 'pointer' }}>
            {l.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <button onClick={save} disabled={!region || state === 'saving'}
          className="btn btn-primary"
          style={{ cursor: region ? 'pointer' : 'not-allowed', opacity: region ? 1 : 0.5 }}>
          {state === 'saving' ? tr(language, T.saving) : tr(language, T.save)}
        </button>
        {!region && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {tr(language, T.pick)}</span>}
        {state === 'saved' && <span style={{ fontSize: 12, color: 'var(--success, #1baf7a)' }}>
          {tr(language, T.saved)}</span>}
        {state === 'error' && <span style={{ fontSize: 12, color: 'var(--danger, #eb6834)' }}>
          {tr(language, T.failed)}</span>}
      </div>
      {compact ? null : (
        <p style={{ fontSize: 12.3, color: 'var(--text-muted)', margin: '14px 0 0' }}>
          {tr(language, T.why)}
        </p>
      )}
    </div>
  )
}

/**
 * First-run dialog. Shown once, when the account has never answered.
 * Deliberately not dismissable by clicking away: the whole point is that the
 * member chooses rather than the platform guessing.
 */
export function RegionSetupDialog({ token, language, onDone }: {
  token: string
  language: Language
  onDone: (region: string, lang: Language, timezone: string) => void
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 4000, display: 'grid', placeItems: 'center',
      background: 'rgba(0,0,0,.55)', padding: 16,
    }}>
      <div className="card" style={{
        maxWidth: 560, width: '100%', padding: '22px 24px',
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        <h2 style={{ fontSize: 18, margin: '0 0 6px' }}>{tr(language, T.title)}</h2>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 18px' }}>
          {tr(language, T.why)}
        </p>
        <RegionPicker token={token} language={language} compact onSaved={onDone} />
      </div>
    </div>
  )
}
