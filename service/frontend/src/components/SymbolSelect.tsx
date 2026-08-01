import { useEffect, useState, type CSSProperties } from 'react'
import { API_BASE } from '../appShared'

// Shared selection-only symbol picker. All symbol fields in the app are
// dropdowns (no free-text input); options come from /api/markets/symbols
// and, for polymarket, from /api/markets/polymarket.

type SymbolLists = {
  crypto: string[]; crypto_pairs: string[]; stock: string[]; forex: string[]
  futures: string[]; option_underlyings: string[]
}
type Option = { value: string; label: string }

const EMPTY_LISTS: SymbolLists = {
  crypto: [], crypto_pairs: [], stock: [], forex: [],
  futures: [], option_underlyings: [],
}
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
          futures: Array.isArray(d.futures) ? d.futures : [],
          option_underlyings: Array.isArray(d.option_underlyings) ? d.option_underlyings : [],
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

type OptionContract = {
  symbol: string; strike: number; bid: number | null; ask: number | null
  last: number | null; price: number | null; open_interest: number | null
  in_the_money: boolean
}
type OptionChain = {
  underlying: string; underlying_price: number | null
  expirations: number[]; expiry: number | null
  calls: OptionContract[]; puts: OptionContract[]
}

function expiryLabel(epoch: number): string {
  return new Date(epoch * 1000).toISOString().slice(0, 10)
}

// Options are the one market where the traded symbol is not a ticker: a
// position is booked under an OCC contract (AAPL260720C00205000), which nobody
// types by hand. Underlying → expiry → strike, then the OCC symbol is what
// leaves this component.
function OptionContractSelect({ value, onChange, className, style, required, disabled }: {
  value: string
  onChange: (symbol: string) => void
  className?: string
  style?: CSSProperties
  required?: boolean
  disabled?: boolean
}) {
  const [underlyings, setUnderlyings] = useState<string[]>([])
  const [underlying, setUnderlying] = useState('')
  const [chain, setChain] = useState<OptionChain | null>(null)
  const [expiry, setExpiry] = useState<number | null>(null)
  const [right, setRight] = useState<'C' | 'P'>('C')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    loadLists().then(l => setUnderlyings(l.option_underlyings))
  }, [])

  useEffect(() => {
    if (!underlying) { setChain(null); return }
    let alive = true
    setLoading(true)
    setError('')
    const qs = expiry ? `?expiry=${expiry}` : ''
    fetch(`${API_BASE}/markets/options/${underlying}${qs}`)
      .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(d?.detail || r.statusText)))
      .then((d: OptionChain) => { if (alive) { setChain(d); setExpiry(d.expiry ?? null) } })
      .catch((e) => { if (alive) { setChain(null); setError(String(e)) } })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // `expiry` drives a refetch, but only after an underlying is chosen.
  }, [underlying, expiry])

  const contracts = chain ? (right === 'C' ? chain.calls : chain.puts) : []

  return (
    <div style={{ display: 'grid', gap: 6, ...style }}>
      <select
        className={className}
        value={underlying}
        required={required}
        disabled={disabled}
        onChange={e => { setUnderlying(e.target.value); setExpiry(null); onChange('') }}
      >
        <option value="">기초자산 · Underlying</option>
        {underlyings.map(u => <option key={u} value={u}>{u}</option>)}
      </select>

      {underlying && (
        <div style={{ display: 'flex', gap: 6 }}>
          <select
            className={className}
            style={{ flex: 1 }}
            value={expiry ?? ''}
            disabled={disabled || !chain}
            onChange={e => { setExpiry(Number(e.target.value) || null); onChange('') }}
          >
            {(chain?.expirations || []).map(x => (
              <option key={x} value={x}>{expiryLabel(x)}</option>
            ))}
          </select>
          <select
            className={className}
            value={right}
            disabled={disabled}
            onChange={e => { setRight(e.target.value as 'C' | 'P'); onChange('') }}
          >
            <option value="C">콜 · Call</option>
            <option value="P">풋 · Put</option>
          </select>
        </div>
      )}

      {underlying && (
        <select
          className={className}
          value={value}
          required={required}
          disabled={disabled || loading || !contracts.length}
          onChange={e => onChange(e.target.value)}
        >
          <option value="">
            {loading ? '불러오는 중… · Loading…' : '행사가 · Strike'}
          </option>
          {contracts.map(c => (
            <option key={c.symbol} value={c.symbol}>
              {c.strike} {c.in_the_money ? '· ITM' : ''}
              {c.price != null ? ` · $${c.price}` : ' · 호가 없음'}
              {c.open_interest ? ` · OI ${c.open_interest}` : ''}
            </option>
          ))}
        </select>
      )}

      {error && <span style={{ fontSize: 12, opacity: 0.7 }}>{error}</span>}
      {chain?.underlying_price != null && (
        <span style={{ fontSize: 12, opacity: 0.7 }}>
          {chain.underlying} ${chain.underlying_price} · 1계약 = 100주
        </span>
      )}
    </div>
  )
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
  const isOptions = (market || '').toLowerCase() === 'options'

  useEffect(() => {
    let alive = true
    const m = (market || '').toLowerCase()
    if (m === 'options') {
      // Handled by OptionContractSelect below; no flat list to load.
      setOptions([])
      setTop([])
    } else if (m === 'polymarket') {
      loadPolymarketOptions().then(opts => { if (alive) setOptions(opts) })
    } else {
      loadLists().then(lists => {
        if (!alive) return
        let symbols: string[]
        if (variant === 'pair') symbols = lists.crypto_pairs
        else if (m === 'forex') symbols = lists.forex
        else if (m === 'futures') symbols = lists.futures
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

  if (isOptions) {
    return (
      <OptionContractSelect
        value={value}
        onChange={onChange}
        className={className}
        style={style}
        required={required}
        disabled={disabled}
      />
    )
  }

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
