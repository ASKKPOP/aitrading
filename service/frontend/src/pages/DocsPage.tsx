import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { injectSiteTheme, siteIsDark } from '../components/docTheme'
import { tr, type PartialTrMap } from '../i18n'

// Login-gated guide & research documents (backend: routes_guide.py).
// URL slugs are stable product names; manifest groups are the build keys.
const SLUG_TO_GROUP: Record<string, string> = {
  'guide': 'guide',
  'automation': 'automation',
  'gateway': 'gateway',
  'smart-features': 'smart',
  'strategy': 'hybrid',
  'ai-trading-parameters': 'top10',
  'chart-vs-human-psychology': 'psych-report',
  'framework': 'framework',
  'backtest-report': 'backtest-report',
  'architecture': 'architecture',
  'decisions': 'decisions',
  'extensions': 'extensions',
  // The rail FILTERS on this map (an unmapped group is invisible, not merely
  // unlinkable), so a group registered in build_guide_content.py half-exists
  // until it is listed here too. `market-hours` had been in that state since
  // it shipped; `how-it-works` nearly repeated it.
  'market-hours': 'market-hours',
  'how-it-works': 'how-it-works',
  'liquidation-defense': 'liq-defense',
  'trading-skills': 'trading-skills',
  'desk-rag': 'desk-rag',
  'desk-learning': 'desk-learning',
}
const GROUP_TO_SLUG: Record<string, string> = Object.fromEntries(
  Object.entries(SLUG_TO_GROUP).map(([s, g]) => [g, s]))

interface ManifestDoc { key: string; lang: string; group: string; title: string }
// The nav label carries every registered language. It was `{ ko, en }` until
// 2026-07-29, and the rail rendered `language === 'ko' ? ko : en` — so a
// ja/th/vi/id member browsed the documentation in English even for the groups
// published in their own language. TrMap + tr() is the same fallback the rest
// of the product uses: a language the manifest omits degrades to English.
type ManifestGroup = { group: string } & PartialTrMap
interface Manifest { groups: ManifestGroup[]; docs: ManifestDoc[] }

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
  const [dark, setDark] = useState(siteIsDark)

  const auth = userToken || token || ''
  // Prefer the reader's own language when that group publishes it; fall back to
  // English otherwise. Older groups ship ko/en only, so ja/th/vi readers still
  // land on English there — but a group that IS fully localised now reaches
  // them, which the previous hard-coded ko-or-en rule made impossible.
  const docLang = language
  const group = SLUG_TO_GROUP[slug || 'guide'] || 'guide'

  useEffect(() => {
    let alive = true
    fetch(`${API_BASE}/guide/docs`, { headers: { Authorization: `Bearer ${auth}` } })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() })
      .then(m => { if (alive) setManifest(m) })
      .catch(e => { if (alive) setError(e.message === '403' ? 'enterprise' : 'manifest') })
    return () => { alive = false }
  }, [auth])

  useEffect(() => {
    if (!manifest) return
    const docs = manifest.docs.filter(d => d.group === group)
    const doc = docs.find(d => d.lang === docLang)
      || docs.find(d => d.lang === 'en') || docs[0]
    if (!doc) { setError('doc'); return }
    setError(null)
    if (cache.current[doc.key]) { setHtml(cache.current[doc.key]); return }
    setHtml(null)
    let alive = true
    fetch(`${API_BASE}/guide/doc/${encodeURIComponent(doc.key)}`, { headers: { Authorization: `Bearer ${auth}` } })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.text() })
      .then(t => { if (alive) { cache.current[doc.key] = t; setHtml(t) } })
      .catch(e => { if (alive) setError(e.message === '403' ? 'enterprise' : 'doc') })
    return () => { alive = false }
  }, [manifest, group, docLang, auth])

  // srcdoc iframes are same-origin: size the frame to the document, and hand
  // the document the SITE's palette. The injection itself — palette aliases,
  // painted background, border tokens, neutralised measures, and the traps
  // that shaped each rule — lives in components/docTheme.ts, shared with the
  // in-page GuideDocOverlay so the two renderers cannot drift.
  const applySiteTheme = () => {
    const doc = frameRef.current?.contentDocument
    if (!doc?.body) return
    setDark(injectSiteTheme(doc))
    setFrameH(Math.max(600, doc.body.scrollHeight + 40))
  }

  const onFrameLoad = () => applySiteTheme()

  // Paint a freshly loaded document.
  useEffect(() => { applySiteTheme() }, [html])

  // Re-paint an already-open document when the reader switches theme.
  //
  // Watching the attribute rather than reacting to the `theme` value: the
  // palette lives in CSS keyed on data-theme, which an ANCESTOR writes in its
  // own effect (App.tsx), and React runs child effects before parent ones — so
  // reading the variables when `theme` changes returns the theme being
  // REPLACED, which is how switching to 'claude' left the document wearing
  // 'signal' blue. A MutationObserver fires once the attribute is actually
  // there, and unlike rAF it still fires in a background tab.
  useEffect(() => {
    const target = document.documentElement
    const obs = new MutationObserver(applySiteTheme)
    obs.observe(target, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [html])

  const activeDocs = manifest?.docs.filter(d => d.group === group) ?? []
  // Only warn when we actually fell back — a fully localised group must not
  // tell the reader they are looking at English when they are not.
  const langNote = language !== 'en' && language !== 'ko'
    && !activeDocs.some(d => d.lang === language)
    && activeDocs.some(d => d.lang === 'en')

  return (
    <div className="page-container" style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 4px' }}>
        {tr(language, { ko: '가이드 · 리서치 문서', en: 'Guide & Research Docs', ja: 'ガイド・リサーチ文書', th: 'คู่มือและเอกสารวิจัย', vi: 'Hướng dẫn & tài liệu nghiên cứu', id: 'Dokumen panduan & riset' })}
      </h1>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '0 0 16px' }}>
        {tr(language, { ko: 'Enterprise 회원 전용 문서입니다.', en: 'Enterprise members-only documents.', ja: 'Enterprise会員限定の文書です。', th: 'เอกสารสำหรับสมาชิก Enterprise เท่านั้น', vi: 'Tài liệu chỉ dành cho thành viên Enterprise.', id: 'Dokumen khusus anggota Enterprise.' })}
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
            {tr(language, g)}
          </button>
        ))}
      </div>

      {langNote && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 10px' }}>
          {tr(language, { ko: '', en: '', ja: 'この文書は現在、韓国語と英語で提供されています（英語版を表示中）。', th: 'เอกสารนี้มีให้ในภาษาเกาหลีและอังกฤษ (กำลังแสดงฉบับภาษาอังกฤษ)', vi: 'Tài liệu hiện có bằng tiếng Hàn và tiếng Anh (đang hiển thị bản tiếng Anh).', id: 'Dokumen ini tersedia dalam bahasa Korea dan Inggris (menampilkan versi bahasa Inggris).' })}
        </p>
      )}

      {error === 'enterprise' && (
        <div style={{ padding: '22px 24px', border: '1px solid var(--border-color)', borderRadius: 12, background: 'var(--bg-card)' }}>
          <div style={{ fontSize: 15.5, fontWeight: 700, marginBottom: 6 }}>
            {tr(language, { ko: '가이드 문서는 Enterprise 플랜 전용입니다.', en: 'The guide library is an Enterprise plan feature.', ja: 'ガイド文書はEnterpriseプラン限定です。', th: 'คลังคู่มือนี้สำหรับแผน Enterprise เท่านั้น', vi: 'Thư viện hướng dẫn chỉ dành cho gói Enterprise.', id: 'Pustaka panduan khusus paket Enterprise.' })}
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14 }}>
            {tr(language, { ko: 'Enterprise로 업그레이드하면 전체 가이드·리서치 문서를 열람할 수 있습니다.', en: 'Upgrade to Enterprise to read the full guide and research documents.', ja: 'Enterpriseにアップグレードすると、すべてのガイド・リサーチ文書を閲覧できます。', th: 'อัปเกรดเป็น Enterprise เพื่ออ่านคู่มือและเอกสารวิจัยทั้งหมด', vi: 'Nâng cấp lên Enterprise để đọc toàn bộ hướng dẫn và tài liệu nghiên cứu.', id: 'Tingkatkan ke Enterprise untuk membaca semua dokumen panduan dan riset.' })}
          </div>
          <button onClick={() => navigate('/subscribe')}
            style={{ padding: '10px 22px', borderRadius: 9, border: 'none', background: 'var(--accent-primary)', color: '#fff', fontWeight: 700, fontSize: 13.5, cursor: 'pointer' }}>
            {tr(language, { ko: '플랜 보기', en: 'View plans', ja: 'プランを見る', th: 'ดูแผน', vi: 'Xem gói', id: 'Lihat paket' })}
          </button>
        </div>
      )}
      {error && error !== 'enterprise' && (
        <div style={{ padding: '14px 16px', border: '1px solid var(--error)', borderRadius: 10, color: 'var(--error)', fontSize: 13.5 }}>
          {tr(language, { ko: '문서를 불러오지 못했습니다. 다시 로그인 후 시도해 주세요.', en: 'Could not load the document. Please sign in again and retry.', ja: '文書を読み込めませんでした。再ログインしてお試しください。', th: 'โหลดเอกสารไม่สำเร็จ กรุณาเข้าสู่ระบบใหม่แล้วลองอีกครั้ง', vi: 'Không tải được tài liệu. Vui lòng đăng nhập lại và thử lại.', id: 'Tidak dapat memuat dokumen. Silakan masuk kembali lalu coba lagi.' })}
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
          // No frame around the document: the border + radius read as a box
          // inside a page that is already a page.
          //
          // colorScheme here is load-bearing, not decoration: inside a nested
          // browsing context prefers-color-scheme resolves against the EMBEDDER
          // element, so this is what makes each document's own light/dark block
          // follow the site theme instead of the reader's OS. Without it, the
          // two documents that hardcode their colours render white headings on
          // the cream 'light' page whenever the OS is dark.
          style={{
            width: '100%', height: frameH, border: 'none', display: 'block',
            colorScheme: dark ? 'dark' : 'light',
          }}
        />
      )}
    </div>
  )
}

export default DocsPage
