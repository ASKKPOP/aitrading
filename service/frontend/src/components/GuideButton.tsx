import { useLanguage } from '../appShared'
import { tr } from '../i18n'

// Kept in its own module so the topbar can render the button eagerly without
// pulling the (large, all-languages) guide content registry into the main
// bundle — GuidePanel and its content stay lazy until the button is clicked.

export function GuideButton({ onClick }: { onClick: () => void }) {
  const { language } = useLanguage()
  const label = tr(language, { ko: '가이드', en: 'Guide', ja: 'ガイド', th: 'คู่มือ', vi: 'Hướng dẫn' })

  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        border: '1px solid var(--border-color)', background: 'transparent',
        color: 'var(--text-secondary)', borderRadius: 8,
        padding: '6px 11px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
        whiteSpace: 'nowrap',
      }}
    >
      <span aria-hidden="true">📖</span>
      <span>{label}</span>
    </button>
  )
}

export default GuideButton
