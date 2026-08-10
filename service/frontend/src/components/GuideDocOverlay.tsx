import { useEffect, useRef, useState } from 'react'

import { API_BASE, useLanguage } from '../appShared'
import { tr } from '../i18n'
import { injectSiteTheme, siteIsDark } from './docTheme'

// Full-screen reader for a page's long-form guide document, opened from the
// GuidePanel drawer ("Read the full illustrated guide"). Fetches
// /api/guide/doc/{slug}-{lang} — falling back to English when that language
// is not published — and renders it the way DocsPage does: a same-origin
// srcdoc iframe with the site palette injected (docTheme.ts).
//
// Why this exists (owner ask 2026-08-10): the /docs rail is an Enterprise
// perk, but a page's own manual should be readable ON that page by every
// member. The doc endpoint exempts page-manual groups from the enterprise
// gate, and this overlay keeps the reader on the page instead of navigating.
const T = {
  title: { ko: '전체 가이드', en: 'Full guide', ja: '完全ガイド', th: 'คู่มือฉบับเต็ม', vi: 'Hướng dẫn đầy đủ', id: 'Panduan lengkap' },
  close: { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng', id: 'Tutup' },
  loading: { ko: '가이드를 불러오는 중…', en: 'Loading the guide…', ja: 'ガイドを読み込み中…', th: 'กำลังโหลดคู่มือ…', vi: 'Đang tải hướng dẫn…', id: 'Memuat panduan…' },
  failed: {
    ko: '가이드를 불러오지 못했습니다. 닫았다가 다시 열어 주세요.',
    en: 'Could not load the guide. Close and reopen to retry.',
    ja: 'ガイドを読み込めませんでした。閉じて開き直してください。',
    th: 'โหลดคู่มือไม่สำเร็จ ปิดแล้วเปิดใหม่เพื่อลองอีกครั้ง',
    vi: 'Không tải được hướng dẫn. Đóng rồi mở lại để thử lại.',
    id: 'Tidak dapat memuat panduan. Tutup lalu buka lagi untuk mencoba ulang.',
  },
}

export function GuideDocOverlay({ slug, auth, onClose }: {
  slug: string
  auth: string
  onClose: () => void
}) {
  const { language } = useLanguage()
  const [html, setHtml] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const frameRef = useRef<HTMLIFrameElement | null>(null)
  const [frameH, setFrameH] = useState(900)
  const [dark, setDark] = useState(siteIsDark)

  useEffect(() => {
    let alive = true
    const load = async () => {
      for (const lang of language === 'en' ? ['en'] : [language, 'en']) {
        try {
          const r = await fetch(`${API_BASE}/guide/doc/${slug}-${lang}`,
            { headers: { Authorization: `Bearer ${auth}` } })
          if (r.ok) {
            const t = await r.text()
            if (alive) setHtml(t)
            return
          }
        } catch { /* try the fallback */ }
      }
      if (alive) setFailed(true)
    }
    load()
    return () => { alive = false }
  }, [slug, language, auth])

  const applyTheme = () => {
    const doc = frameRef.current?.contentDocument
    setDark(injectSiteTheme(doc))
    if (doc?.body) setFrameH(Math.max(600, doc.body.scrollHeight + 40))
  }

  // Paint a freshly loaded document, and re-paint on a site theme switch —
  // a MutationObserver on data-theme, because the palette lands after the
  // theme value changes and rAF is dead in a background tab.
  useEffect(() => { applyTheme() }, [html])
  useEffect(() => {
    const obs = new MutationObserver(applyTheme)
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => obs.disconnect()
  }, [html])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={tr(language, T.title)}
      onClick={onClose}
      // z 600 matches the app's dialog convention (DeskCyclesPanel) — dialogs
      // outrank the nav. At 80 the fixed topbar painted over the overlay's own
      // header, hiding its close button.
      style={{ position: 'fixed', inset: 0, zIndex: 600, background: 'rgba(0,0,0,0.55)', display: 'flex', justifyContent: 'center' }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 'min(980px, 100vw)', height: '100%', display: 'flex', flexDirection: 'column',
          background: 'var(--bg-primary)', borderLeft: '1px solid var(--border-color)',
          borderRight: '1px solid var(--border-color)',
        }}
      >
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 17 }} aria-hidden="true">📖</span>
          <div style={{ flex: 1, fontWeight: 700, fontSize: 14 }}>{tr(language, T.title)}</div>
          <button
            onClick={onClose}
            title={tr(language, T.close)}
            aria-label={tr(language, T.close)}
            style={{ border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 13, padding: '4px 9px', cursor: 'pointer' }}
          >✕</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {!html && (
            <div style={{ padding: '18px 20px', fontSize: 13, color: 'var(--text-secondary)' }}>
              {failed ? tr(language, T.failed) : tr(language, T.loading)}
            </div>
          )}
          {html && (
            <iframe
              ref={frameRef}
              title={tr(language, T.title)}
              srcDoc={html}
              onLoad={applyTheme}
              style={{
                width: '100%', height: frameH, border: 'none', display: 'block',
                colorScheme: dark ? 'dark' : 'light',
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default GuideDocOverlay
