import { useEffect, useRef, useState } from 'react'
import { tr, type Language } from '../i18n'
import { POPULAR_PAIRS, pair } from '../pages/tradeShared'

// ga PairSelector: searchable pair dropdown with localStorage favourites.
// Favourites pin to the top; the star toggles without selecting the row.

const FAV_KEY = 'sooppiy:favPairs'
const mono: any = { fontFamily: 'ui-monospace,SFMono-Regular,Menlo,monospace' }

function loadFavs(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(FAV_KEY) || '[]')
    return Array.isArray(raw) ? raw.filter(s => typeof s === 'string') : []
  } catch { return [] }
}

export function PairSelector({ value, onChange, language }: {
  value: string
  onChange: (symbol: string) => void
  language: Language
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [favs, setFavs] = useState<string[]>(loadFavs)
  const holder = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (holder.current && !holder.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const T = {
    search: tr(language, { ko: '검색', en: 'Search', ja: '検索', th: 'ค้นหา', vi: 'Tìm kiếm', id: 'Cari' }),
    noMatch: tr(language, { ko: '일치하는 페어 없음', en: 'No matching pairs', ja: '該当ペアなし', th: 'ไม่พบคู่เทรด', vi: 'Không có cặp phù hợp', id: 'Tidak ada pasangan yang cocok' }),
  }

  function toggleFav(s: string) {
    const next = favs.includes(s) ? favs.filter(f => f !== s) : [...favs, s]
    setFavs(next)
    localStorage.setItem(FAV_KEY, JSON.stringify(next))
  }

  const q = query.trim().toUpperCase()
  const matches = POPULAR_PAIRS.filter(s => !q || s.includes(q) || pair(s).includes(q))
  const ordered = [...matches.filter(s => favs.includes(s)), ...matches.filter(s => !favs.includes(s))]

  return (
    <div ref={holder} style={{ position: 'relative' }}>
      <button onClick={() => { setOpen(v => !v); setQuery('') }}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderRadius: 8, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}>
        {favs.includes(value) && <span style={{ color: 'var(--accent-primary,#c26a45)' }}>★</span>}
        {pair(value)}
        <span style={{ fontSize: 10, color: 'var(--text-secondary,#8a8073)' }}>▼</span>
      </button>
      {open && (
        <div style={{ position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 50, width: 240, maxHeight: 340, overflowY: 'auto', background: 'var(--bg-card,#fffdf9)', border: '1px solid var(--border-color,#d3c8b6)', borderRadius: 10, boxShadow: '0 8px 24px rgba(0,0,0,0.18)' }}>
          <div style={{ padding: 8, position: 'sticky', top: 0, background: 'var(--bg-card,#fffdf9)', borderBottom: '1px solid var(--border-color,#e6ddd0)' }}>
            <input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder={T.search}
              style={{ width: '100%', padding: '7px 10px', borderRadius: 7, border: '1px solid var(--border-color,#d3c8b6)', background: 'var(--bg-secondary,#fff)', color: 'var(--text-primary,inherit)', fontSize: 13 }} />
          </div>
          {ordered.length === 0 && (
            <div style={{ padding: 14, fontSize: 12.5, color: 'var(--text-secondary,#8a8073)' }}>{T.noMatch}</div>
          )}
          {ordered.map(s => (
            <div key={s} onClick={() => { onChange(s); setOpen(false) }}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', cursor: 'pointer', fontSize: 13.5, fontWeight: s === value ? 700 : 500, background: s === value ? 'var(--bg-secondary,#f3efe7)' : 'transparent' }}>
              <span onClick={e => { e.stopPropagation(); toggleFav(s) }}
                title="favorite"
                style={{ cursor: 'pointer', color: favs.includes(s) ? 'var(--accent-primary,#c26a45)' : 'var(--text-secondary,#8a8073)', width: 16, textAlign: 'center' }}>
                {favs.includes(s) ? '★' : '☆'}
              </span>
              <span style={mono}>{pair(s)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default PairSelector
