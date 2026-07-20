import { useEffect, useState, type CSSProperties } from 'react'
import { API_BASE } from '../appShared'

// Shared selection-only symbol picker. All symbol fields in the app are
// dropdowns (no free-text input); options come from /api/markets/symbols
// and, for polymarket, from /api/markets/polymarket.

type SymbolLists = { crypto: string[]; crypto_pairs: string[]; stock: string[]; forex: string[] }
type Option = { value: string; label: string }

const EMPTY_LISTS: SymbolLists = { crypto: [], crypto_pairs: [], stock: [], forex: [] }
let listsCache: SymbolLists | null = null
let listsPromise: Promise<SymbolLists> | null = null

function loadLists(): Promise<SymbolLists> {
  if (listsCache) return Promise.resolve(listsCache)
  if (!listsPromise) {
    listsPromise = fetch(`${API_BASE}/markets/symbols`)
      .then(r => r.json())
      .then((d) => {
        listsCache = {
          crypto: Array.isArray(d.crypto) ? d.crypto : [],
          crypto_pairs: Array.isArray(d.crypto_pairs) ? d.crypto_pairs : [],
          stock: Array.isArray(d.stock) ? d.stock : [],
          forex: Array.isArray(d.forex) ? d.forex : [],
        }
        return listsCache
      })
      .catch(() => {
        listsPromise = null
        return EMPTY_LISTS
      })
  }
  return listsPromise
}

let polyCache: Option[] | null = null
let polyPromise: Promise<Option[]> | null = null

function loadPolymarketOptions(): Promise<Option[]> {
  if (polyCache) return Promise.resolve(polyCache)
  if (!polyPromise) {
    polyPromise = fetch(`${API_BASE}/markets/polymarket?limit=100`)
      .then(r => r.json())
      .then((d): Option[] => {
        const opts: Option[] = (Array.isArray(d.markets) ? d.markets : [])
          .filter((m: any) => m && m.slug)
          .map((m: any) => ({ value: m.slug, label: m.title || m.slug }))
        polyCache = opts
        return opts
      })
      .catch((): Option[] => {
        polyPromise = null
        return []
      })
  }
  return polyPromise
}

export function SymbolSelect({ market, variant, value, onChange, placeholder, className, style, required, disabled }: {
  market?: string          // 'crypto' | 'us-stock' | 'polymarket' | 'forex' | '' (all) …
  variant?: 'pair'         // OKX USDT pair form (BTCUSDT) — watches/consult
  value: string
  onChange: (symbol: string) => void
  placeholder?: string     // label of the empty option
  className?: string
  style?: CSSProperties
  required?: boolean
  disabled?: boolean
}) {
  const [options, setOptions] = useState<Option[]>([])

  useEffect(() => {
    let alive = true
    const m = (market || '').toLowerCase()
    if (m === 'polymarket') {
      loadPolymarketOptions().then(opts => { if (alive) setOptions(opts) })
    } else {
      loadLists().then(lists => {
        if (!alive) return
        let symbols: string[]
        if (variant === 'pair') symbols = lists.crypto_pairs
        // Exact match before the substring checks below — 'a-stock' would otherwise
        // match .includes('stock') and be offered US tickers.
        else if (m === 'forex') symbols = lists.forex
        else if (m.includes('crypto')) symbols = lists.crypto
        else if (m.includes('stock')) symbols = lists.stock
        else symbols = [...lists.crypto, ...lists.stock.filter(s => !lists.crypto.includes(s))]
        setOptions(symbols.map(s => ({ value: s, label: s })))
      })
    }
    return () => { alive = false }
  }, [market, variant])

  // Keep pre-existing values (old data, other markets) selectable.
  const opts = value && !options.some(o => o.value === value)
    ? [{ value, label: value }, ...options]
    : options

  return (
    <select
      className={className}
      style={style}
      value={value}
      required={required}
      disabled={disabled}
      onChange={e => onChange(e.target.value)}
    >
      <option value="">{placeholder ?? '—'}</option>
      {opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}
