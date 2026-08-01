import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { API_BASE, useLanguage } from '../appShared'
import { tr, type PartialTrMap } from '../i18n'

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

/** Is the SITE currently dark? 'signal' and 'claude' are dark, 'light' is not;
 *  before the theme is applied fall back to the OS. */
function siteIsDark(): boolean {
  const t = document.documentElement.getAttribute('data-theme')
  return t ? t !== 'light' : matchMedia('(prefers-color-scheme: dark)').matches
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
      .catch(() => { if (alive) setError('manifest') })
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
      .catch(() => { if (alive) setError('doc') })
    return () => { alive = false }
  }, [manifest, group, docLang, auth])

  // srcdoc iframes are same-origin: size the frame to the document, and hand
  // the document the SITE's palette.
  //
  // Documents ship their own light/dark palette keyed on prefers-color-scheme,
  // which follows the OS — not this app's theme. On the 'claude' theme (always
  // dark) with a light OS that produced dark text on a dark surface. So push
  // the resolved theme variables in and let the document paint with them.
  //
  // The page background is PAINTED, not left transparent: a transparent page
  // under color-scheme:dark makes the browser fall back to its own black
  // canvas, which on the warm-charcoal 'claude' surface reads as a black box
  // around the document. Two of the documents (hybrid, top10) set no body
  // background at all, so they hit the same canvas. Painting html/body with
  // the site's page colour removes the box everywhere, whatever the document
  // happens to call its own variables.
  //
  // Documents disagree on variable names — --page/--bg/--ground for the page,
  // --card/--panel/--surface for a raised surface, --ink-2/--ink2/--ink-3 for
  // secondary text — so every alias in guide_content/ is mapped here. A name
  // no document uses simply goes unread.
  //
  // hybrid and top10 scope their palette to .viz-root rather than :root, and a
  // variable set on that element beats one inherited from :root — so those two
  // kept painting their own #0d0d0d page inside ours, a black box with the
  // wrong accent. Both selectors carry the palette, and .viz-root's own
  // background is overridden alongside html/body. Their dark/light choice is
  // separate again: it is hardcoded behind prefers-color-scheme, which inside
  // a nested browsing context resolves against color-scheme on the IFRAME
  // ELEMENT — see the `dark` state and the iframe style below.
  //
  // Every document also brought its OWN measure (860 / 880 / 980 / 1020 /
  // 1040 / 1120 px, each self-centred with its own gutter), so no two guide
  // pages lined up and none of them lined up with the page heading above the
  // frame. The page container is already the measure; the documents' is
  // removed so all of them share one column and one left edge.
  const applySiteTheme = () => {
    const doc = frameRef.current?.contentDocument
    if (!doc?.body) return
    try {
      const root = getComputedStyle(document.documentElement)
      const v = (name: string) => root.getPropertyValue(name).trim()
      const dark = siteIsDark()
      setDark(dark)
      const page = v('--bg-primary')
      const card = v('--bg-card')
      const surface = v('--bg-secondary')
      const line = v('--bg-tertiary')
      const ink = v('--text-primary')
      const ink2 = v('--text-secondary')
      const muted = v('--text-muted')
      const accent = v('--accent-primary')
      let style = doc.getElementById('site-theme') as HTMLStyleElement | null
      if (!style) {
        style = doc.createElement('style')
        style.id = 'site-theme'
        doc.head.appendChild(style)
      }
      style.textContent = `
        :root,.viz-root{color-scheme:${dark ? 'dark' : 'light'};
          --page:${page}; --bg:${page}; --ground:${page}; --surface-0:${page};
          --card:${card}; --panel:${card}; --surface-1:${card};
          --surface:${surface}; --surf:${surface}; --panel-2:${surface}; --surface-2:${surface};
          --grid:${line}; --border:${line}; --bd:${line}; --hair:${line};
          --border-strong:${line}; --baseline:${line};
          --ink:${ink}; --text-primary:${ink};
          --ink2:${ink2}; --ink-2:${ink2}; --ink-3:${muted}; --text-secondary:${ink2};
          --muted:${muted}; --text-muted:${muted};
          --accent:${accent}; --ai:${accent};}
        html,body,.viz-root{background:${page}}
        .wrap,main,.viz-root{max-width:none; padding-left:0; padding-right:0}
        main,.viz-root{padding-top:0}`
    } catch {
      /* styling is a nicety — never let it stop the document rendering */
    }
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
        {tr(language, { ko: '회원 전용 문서입니다.', en: 'Members-only documents.', ja: '会員限定の文書です。', th: 'เอกสารสำหรับสมาชิกเท่านั้น', vi: 'Tài liệu chỉ dành cho thành viên.', id: 'Dokumen khusus anggota.' })}
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

      {error && (
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
