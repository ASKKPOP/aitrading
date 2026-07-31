// Shared helpers for the ga-style trading pages (My Assets / Spot / Futures).
// Sooppiy's API trades plain symbols (BTC) at USD prices; ga displays USDT pairs.
// We show SYMBOL/USDT visually and trade the plain symbol underneath.

// Mirrors crypto_feed.TOP_20_PAIRS (bare base form) — every pair here has OKX
// market data behind /api/markets/crypto/* and trades as the bare symbol.
export const POPULAR_PAIRS = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX', 'LINK', 'DOT',
  'LTC', 'BCH', 'UNI', 'ATOM', 'TRX', 'NEAR', 'POL', 'FIL', 'APT', 'ARB',
]

export const TRADE_FEE_RATE = 0.001 // conservative fallback until /api/markets/fees loads

// Live per-market fee rates (fees.fee_rate server-side, incl. operator
// overrides). Cached per session — rates change maybe once a quarter.
let feeRates: Record<string, number> | null = null
export async function fetchFeeRate(market = 'crypto'): Promise<number> {
  if (feeRates === null) {
    try {
      const res = await fetch('/api/markets/fees')
      const data = await res.json()
      if (res.ok && data.rates) feeRates = data.rates
    } catch { /* transient — fall back below */ }
  }
  return feeRates?.[market] ?? TRADE_FEE_RATE
}

export function pair(symbol: string) {
  return `${symbol.toUpperCase()}/USDT`
}

export function fmtUsd(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function fmtQty(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const abs = Math.abs(v)
  const digits = abs >= 100 ? 2 : abs >= 1 ? 4 : 6
  return v.toLocaleString('en-US', { maximumFractionDigits: digits })
}

export function pnlColor(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return 'var(--text-secondary,#8a8073)'
  return v > 0 ? '#3fb950' : '#f0663f'
}

export async function fetchPrice(token: string, symbol: string, market = 'crypto'): Promise<number | null> {
  try {
    const res = await fetch(`/api/price?symbol=${encodeURIComponent(symbol.toUpperCase())}&market=${market}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    return res.ok && data.price ? Number(data.price) : null
  } catch {
    return null
  }
}

export async function placeOrder(token: string, body: {
  market: string; action: 'buy' | 'sell' | 'short' | 'cover'; symbol: string;
  price: number; quantity: number; content?: string;
}): Promise<{ ok: boolean; message: string; signalId?: number }> {
  try {
    const res = await fetch('/api/signals/realtime', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ ...body, symbol: body.symbol.toUpperCase(), executed_at: new Date().toISOString() }),
    })
    const data = await res.json()
    if (!res.ok) return { ok: false, message: typeof data.detail === 'string' ? data.detail : 'Order failed' }
    return { ok: true, message: 'Filled', signalId: data.signal_id }
  } catch (e: any) {
    return { ok: false, message: e?.message || 'Network error' }
  }
}
