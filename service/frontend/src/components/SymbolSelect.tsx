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

// Volume-ranked picks (same source the AI auto-pick modes rank from). Shown as
// the first optgroup so the handful of symbols actually worth trading today are
// reachable without scrolling past ~230 alphabetical tickers.
let topCache: string[] | null = null
let topPromise: Promise<string[]> | null = null

function loadTopSymbols(): Promise<string[]> {
  if (topCache) return Promise.resolve(topCache)
  if (!topPromise) {
    topPromise = fetch(`${API_BASE}/markets/top-symbols`)
      .then(r => r.json())
      .then((d): string[] => {
        // the endpoint speaks OKX pair form (BTCUSDT); the pickers speak base
        // symbols (BTC) unless variant='pair'
        const list: string[] = (Array.isArray(d.symbols) ? d.symbols : [])
          .map((s: any) => String(s?.symbol || ''))
          .filter(Boolean)
        topCache = list
        return list
      })
      .catch((): string[] => { topPromise = null; return [] })
  }
  return topPromise
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
  const [top, setTop] = useState<string[]>([])

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
      // Ranking is crypto-only; stock/forex lists are short enough to scan.
      if (m.includes('crypto') || variant === 'pair') {
        loadTopSymbols().then(t => { if (alive) setTop(t) })
      } else {
        setTop([])
      }
    }
    return () => { alive = false }
  }, [market, variant])

  // Keep pre-existing values (old data, other markets) selectable.
  const opts = value && !options.some(o => o.value === value)
    ? [{ value, label: value }, ...options]
    : options

  // Split into "ranked now" and "everything else". Matching is done on the base
  // symbol so the pair-form ranking (BTCUSDT) also lights up a base-form list
  // (BTC); an entry that is ranked but absent from the list is dropped rather
  // than invented, so the picker can never offer an unfetchable symbol.
  const base = (s: string) => s.replace(/USDT$|USD$/, '')
  const rankedSet = new Set(top.map(base))
  const ranked = top.length
    ? opts.filter(o => rankedSet.has(base(o.value)))
    : []
  const rest = ranked.length
    ? opts.filter(o => !ranked.some(r => r.value === o.value))
    : opts

  const opt = (o: Option) => <option key={o.value} value={o.value}>{o.label}</option>

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
      {ranked.length > 0 && (
        <optgroup label="🔥 지금 거래량 상위 · Top by volume now">
          {ranked.map(opt)}
        </optgroup>
      )}
      {ranked.length > 0
        ? <optgroup label={`전체 · All (${rest.length})`}>{rest.map(opt)}</optgroup>
        : rest.map(opt)}
    </select>
  )
}
