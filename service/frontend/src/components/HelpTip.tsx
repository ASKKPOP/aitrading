import { useEffect, useRef, useState } from 'react'
import { useLanguage } from '../appShared'
import { tr } from '../i18n'

// Inline "?" badge → click opens a small explainer bubble for the control it
// sits next to. Fixed positioning (not absolute) so the bubble is never
// clipped by the sidebar's overflow or a modal's stacking context; z-index 700
// outranks the create dialog (600) and the sticky top nav (500). Closes on
// outside click, Escape, scroll or resize.
export function HelpTip({ text, style }: { text: string; style?: any }) {
  const { language } = useLanguage()
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const btnRef = useRef<HTMLButtonElement | null>(null)

  const label = tr(language, { ko: '이게 뭔가요?', en: 'What is this?', ja: 'これは何？', th: 'นี่คืออะไร', vi: 'Đây là gì?', id: 'Apa ini?' })

  const toggle = (e: any) => {
    // Stop the click so a clickable ancestor (card, Link) doesn't also fire.
    e.preventDefault(); e.stopPropagation()
    if (pos) { setPos(null); return }
    const r = btnRef.current!.getBoundingClientRect()
    const width = Math.min(320, window.innerWidth - 24)
    const left = Math.max(12, Math.min(r.left - 8, window.innerWidth - width - 12))
    setPos({ top: r.bottom + 8, left, width })
  }

  useEffect(() => {
    if (!pos) return
    const close = () => setPos(null)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    document.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
      document.removeEventListener('keydown', onKey)
    }
  }, [pos])

  return (
    <>
      <button ref={btnRef} type="button" onClick={toggle} title={label} aria-label={label} aria-expanded={!!pos}
        style={{ width: 18, height: 18, borderRadius: 9, border: '1px solid rgba(138,128,115,0.55)',
          background: 'transparent', color: 'var(--text-secondary,#8a8073)', fontSize: 11, fontWeight: 700,
          lineHeight: 1, cursor: 'pointer', display: 'inline-flex', alignItems: 'center',
          justifyContent: 'center', padding: 0, flexShrink: 0, ...style }}>?</button>
      {pos && (
        <div role="tooltip" onClick={e => e.stopPropagation()}
          style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width, zIndex: 700,
            background: 'var(--bg-card,#fff)', color: 'var(--text-primary,#2b2b2b)',
            border: '1px solid var(--border-color,rgba(0,0,0,0.15))', borderRadius: 10,
            padding: '12px 14px', fontSize: 12.5, fontWeight: 400, lineHeight: 1.6,
            whiteSpace: 'pre-line', textAlign: 'left', boxShadow: '0 8px 28px rgba(0,0,0,0.18)' }}>
          {text}
        </div>
      )}
    </>
  )
}

export default HelpTip
