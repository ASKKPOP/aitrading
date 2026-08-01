// The one language switcher for the whole product — app chrome and the
// marketing header both render this.
//
// The previous inline row of six pills ("한국어 · English · 日本語 · ไทย ·
// Tiếng Việt · Bahasa Indonesia") measured 484px inside a 375px phone
// viewport: the labels wrapped mid-word and the controls sitting after it were
// pushed off-screen. Collapsing to a single trigger + menu makes the control
// a fixed ~64px wide regardless of how many languages the list grows to.
import { useEffect, useRef, useState } from 'react'

import { useLanguage } from '../appShared'
import { LANGUAGES, type Language } from '../i18n'

// Short code for the closed trigger. The full native name still labels each
// menu row — it is only the always-visible part that has to stay narrow.
const SHORT_CODE: Record<Language, string> = {
  ko: 'KO', en: 'EN', ja: 'JA', th: 'TH', vi: 'VI', id: 'ID',
}

export function LanguageSwitcher({ align = 'right' }: { align?: 'left' | 'right' }) {
  const { language, setLanguage } = useLanguage()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const current = LANGUAGES.find((l) => l.value === language) ?? LANGUAGES[0]

  return (
    <div className="lang-switch" ref={rootRef}>
      <button
        type="button"
        className="lang-switch-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={current.label}
        title={current.label}
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden="true">🌐</span>
        <span className="lang-switch-code">{SHORT_CODE[current.value]}</span>
        <span className="lang-switch-caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <div
          className={`lang-switch-menu${align === 'left' ? ' lang-switch-menu--left' : ''}`}
          role="listbox"
          aria-label={current.label}
        >
          {LANGUAGES.map((lang) => (
            <button
              key={lang.value}
              type="button"
              role="option"
              aria-selected={language === lang.value}
              className={`lang-switch-opt${language === lang.value ? ' active' : ''}`}
              onClick={() => { setLanguage(lang.value); setOpen(false) }}
            >
              <span className="lang-switch-opt-code">{SHORT_CODE[lang.value]}</span>
              <span className="lang-switch-opt-name">{lang.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
