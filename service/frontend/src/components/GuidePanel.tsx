import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import { useLanguage } from '../appShared'
import { tr } from '../i18n'
import { resolveGuide } from '../guides'

// Per-page user guide.
//
// Mounted once in the authenticated shell next to the topbar controls, so the
// button sits top-right on every page. The content is looked up from the route
// registry in ../guides, which means adding a guide for a new page is a data
// change, not a component change.

const T = {
  guide: { ko: '가이드', en: 'Guide', ja: 'ガイド', th: 'คู่มือ', vi: 'Hướng dẫn' },
  close: { ko: '닫기', en: 'Close', ja: '閉じる', th: 'ปิด', vi: 'Đóng' },
  faq: { ko: '자주 묻는 질문', en: 'FAQ', ja: 'よくある質問', th: 'คำถามที่พบบ่อย', vi: 'Câu hỏi thường gặp' },
  none: {
    ko: '이 페이지에는 아직 가이드가 준비되지 않았습니다.',
    en: 'No guide is available for this page yet.',
    ja: 'このページのガイドはまだありません。',
    th: 'ยังไม่มีคู่มือสำหรับหน้านี้',
    vi: 'Chưa có hướng dẫn cho trang này.',
  },
}

export function GuidePanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { language } = useLanguage()
  const { pathname } = useLocation()
  const guide = resolveGuide(pathname)

  // Escape closes the panel, matching the drawer convention elsewhere.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 69, background: 'rgba(0,0,0,0.35)' }}
      />
      <aside
        role="complementary"
        aria-label={tr(language, T.guide)}
        style={{
          position: 'fixed', right: 0, top: 0, bottom: 0, zIndex: 70,
          width: 'min(460px, 100vw)', display: 'flex', flexDirection: 'column',
          background: 'var(--bg-card)', borderLeft: '1px solid var(--border-color)',
          boxShadow: '-8px 0 30px rgba(0,0,0,0.28)',
        }}
      >
        <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }} aria-hidden="true">📖</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>
              {guide ? tr(language, guide.title) : tr(language, T.guide)}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{tr(language, T.guide)}</div>
          </div>
          <button
            onClick={onClose}
            title={tr(language, T.close)}
            aria-label={tr(language, T.close)}
            style={{ border: '1px solid var(--border-color)', background: 'transparent', color: 'var(--text-muted)', borderRadius: 6, fontSize: 13, padding: '4px 9px', cursor: 'pointer' }}
          >✕</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 18px' }}>
          {!guide && (
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {tr(language, T.none)}
            </div>
          )}

          {guide && (
            <>
              <p style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--text-secondary)', margin: '0 0 20px' }}>
                {tr(language, guide.summary)}
              </p>

              {guide.sections.map((section, i) => (
                <section key={i} style={{ marginBottom: 20 }}>
                  <h3 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 8px', color: 'var(--text-primary)' }}>
                    {tr(language, section.heading)}
                  </h3>
                  <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {(section.bullets[language] ?? section.bullets.en).map((line, j) => (
                      <li key={j} style={{ fontSize: 12.5, lineHeight: 1.6, color: 'var(--text-secondary)' }}>{line}</li>
                    ))}
                  </ul>
                </section>
              ))}

              {guide.faq && guide.faq.length > 0 && (
                <section style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--border-color)' }}>
                  <h3 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 10px', color: 'var(--text-primary)' }}>
                    {tr(language, T.faq)}
                  </h3>
                  {guide.faq.map((item, i) => (
                    <div key={i} style={{ marginBottom: 14 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                        {tr(language, item.q)}
                      </div>
                      <div style={{ fontSize: 12.5, lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                        {tr(language, item.a)}
                      </div>
                    </div>
                  ))}
                </section>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  )
}

export default GuidePanel
