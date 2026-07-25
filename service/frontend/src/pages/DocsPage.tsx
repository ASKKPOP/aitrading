import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'

// Login-gated guide & research documents (backend: routes_guide.py).
// URL slugs are stable product names; manifest groups are the build keys.
const SLUG_TO_GROUP: Record<string, string> = {
  'guide': 'guide',
  'gateway': 'gateway',
  'smart-features': 'smart',
  'strategy': 'hybrid',
  'ai-trading-parameters': 'top10',
  'chart-vs-human-psychology': 'psych-report',
  'framework': 'framework',
  'backtest-report': 'backtest-report',
  'architecture': 'architecture',
}
const GROUP_TO_SLUG: Record<string, string> = Object.fromEntries(
  Object.entries(SLUG_TO_GROUP).map(([s, g]) => [g, s]))

interface ManifestDoc { key: string; lang: string; group: string; title: string }
interface Manifest { groups: Array<{ group: string; ko: string; en: string }>; docs: ManifestDoc[] }

interface Props {
  token?: string | null
  userToken?: string | null
}

export function DocsPage({ token, userToken }: Props) {
  const { language } = useLanguage()
  const { slug } = useParams()
  const navigate = useNavigate()
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [html, setHtml] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const cache = useRef<Record<string, string>>({})
  const frameRef = useRef<HTMLIFrameElement | null>(null)
  const [frameH, setFrameH] = useState(900)

  const auth = userToken || token || ''
  // documents exist in ko/en; other UI languages read the English document
  const docLang = language === 'ko' ? 'ko' : 'en'
  const group = SLUG_TO_GROUP[slug || 'guide'] || 'guide'

  useEffect(() => {
    let alive = true
    fetch(`${API_BASE}/guide/docs`, { headers: { Authorization: `Bearer ${auth}` } })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then(m => { if (alive) setManifest(m) })
      .catch(() => { if (alive) setError('manifest') })
    return () => { alive = false }
  }, [auth])

  useEffect(() => {
    if (!manifest) return
    const docs = manifest.docs.filter(d => d.group === group)
    const doc = docs.find(d => d.lang === docLang) || docs[0]
    if (!doc) { setError('doc'); return }
    setError(null)
    if (cache.current[doc.key]) { setHtml(cache.current[doc.key]); return }
    setHtml(null)
    let alive = true
    fetch(`${API_BASE}/guide/doc/${encodeURIComponent(doc.key)}`, { headers: { Authorization: `Bearer ${auth}` } })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.text() })
      .then(t => { if (alive) { cache.current[doc.key] = t; setHtml(t) } })
      .catch(() => { if (alive) setError('doc') })
    return () => { alive = false }
  }, [manifest, group, docLang, auth])

  // srcdoc iframes are same-origin: size the frame to the document
  const onFrameLoad = () => {
    const doc = frameRef.current?.contentDocument
    if (doc?.body) setFrameH(Math.max(600, doc.body.scrollHeight + 40))
  }

  const activeDocs = manifest?.docs.filter(d => d.group === group) ?? []
  const langNote = docLang === 'en' && language !== 'en' && activeDocs.some(d => d.lang === 'en')

  return (
    <div className="page-container" style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 4px' }}>
        {tr(language, { ko: '가이드 · 리서치 문서', en: 'Guide & Research Docs', ja: 'ガイド・リサーチ文書', th: 'คู่มือและเอกสารวิจัย', vi: 'Hướng dẫn & tài liệu nghiên cứu' })}
      </h1>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 16px' }}>
        {tr(language, { ko: '회원 전용 문서입니다.', en: 'Members-only documents.', ja: '会員限定の文書です。', th: 'เอกสารสำหรับสมาชิกเท่านั้น', vi: 'Tài liệu chỉ dành cho thành viên.' })}
      </p>

      {/* doc nav */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {(manifest?.groups ?? []).filter(g => GROUP_TO_SLUG[g.group]).map(g => (
          <button key={g.group}
            onClick={() => navigate(`/docs/${GROUP_TO_SLUG[g.group]}`)}
            style={{
              border: `1px solid ${group === g.group ? 'var(--accent-primary)' : 'var(--border-color)'}`,
              background: group === g.group ? 'var(--accent-primary)' : 'var(--bg-card)',
              color: group === g.group ? '#fff' : 'var(--text-secondary)',
              fontSize: 12.5, fontWeight: 600, borderRadius: 999, padding: '5px 13px', cursor: 'pointer',
            }}>
            {language === 'ko' ? g.ko : g.en}
          </button>
        ))}
      </div>

      {langNote && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 10px' }}>
          {tr(language, { ko: '', en: '', ja: 'この文書は現在、韓国語と英語で提供されています（英語版を表示中）。', th: 'เอกสารนี้มีให้ในภาษาเกาหลีและอังกฤษ (กำลังแสดงฉบับภาษาอังกฤษ)', vi: 'Tài liệu hiện có bằng tiếng Hàn và tiếng Anh (đang hiển thị bản tiếng Anh).' })}
        </p>
      )}

      {error && (
        <div style={{ padding: '14px 16px', border: '1px solid var(--error)', borderRadius: 10, color: 'var(--error)', fontSize: 13.5 }}>
          {tr(language, { ko: '문서를 불러오지 못했습니다. 다시 로그인 후 시도해 주세요.', en: 'Could not load the document. Please sign in again and retry.', ja: '文書を読み込めませんでした。再ログインしてお試しください。', th: 'โหลดเอกสารไม่สำเร็จ กรุณาเข้าสู่ระบบใหม่แล้วลองอีกครั้ง', vi: 'Không tải được tài liệu. Vui lòng đăng nhập lại và thử lại.' })}
        </div>
      )}
      {!error && !html && (
        <div className="loading"><div className="spinner"></div></div>
      )}
      {!error && html && (
        <iframe
          ref={frameRef}
          title="document"
          srcDoc={html}
          onLoad={onFrameLoad}
          style={{ width: '100%', height: frameH, border: '1px solid var(--border-color)', borderRadius: 12, background: 'var(--bg-primary)' }}
        />
      )}
    </div>
  )
}

export default DocsPage
