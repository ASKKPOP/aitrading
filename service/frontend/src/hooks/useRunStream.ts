// Live run stream hook (Plan 10, Phase 8).
//
// Owns ONE WebSocket to /ws/runs, authenticated by a short-lived ticket
// (minted via POST /api/runs/ws-ticket — never a session token in the URL).
// Multiplexes per-run subscriptions, tracks last seq for replay, reconnects
// with exponential backoff, and fast-forwards on visibilitychange (the
// Browser pane throttles rAF while hidden; the buffer catches up on focus).

import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../appShared'

export type RunEvent = {
  seq: number
  event_type: string
  ts: string
  payload: any
}

export type RunTick = { symbol: string; market: string; price: number; ts: string }

export type RunStreamState = {
  connected: boolean
  eventsByRun: Record<number, RunEvent[]>
  tickByRun: Record<number, RunTick>
  lastSeqByRun: Record<number, number>
}

async function mintTicket(token: string): Promise<string | null> {
  try {
    const resp = await fetch(`${API_BASE}/runs/ws-ticket`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!resp.ok) return null
    return (await resp.json()).ticket
  } catch {
    return null
  }
}

// `lang` rides the socket URL because one payload field is localized
// server-side: a gate_skip's REASON is English prose from the run engine, and
// its catalogue lives on the server (see routes_run_stream._event_frame).
// Everything else on the wire stays a code the caller maps itself.
export function useRunStream(token: string | null, runIds: number[],
                             lang?: string): RunStreamState {
  const [connected, setConnected] = useState(false)
  const [eventsByRun, setEvents] = useState<Record<number, RunEvent[]>>({})
  const [tickByRun, setTicks] = useState<Record<number, RunTick>>({})
  const lastSeqRef = useRef<Record<number, number>>({})
  const langRef = useRef(lang)
  const wsRef = useRef<WebSocket | null>(null)
  const closedRef = useRef(false)
  const runIdsKey = runIds.slice().sort((a, b) => a - b).join(',')

  useEffect(() => {
    closedRef.current = false
    let backoff = 500
    let reconnectTimer: any = null
    // A language change re-opens the socket, and replaying from the old cursor
    // would leave every already-delivered event in the previous language while
    // only new ones switched. Reset the cursors so the reconnect backfills.
    if (langRef.current !== lang) {
      langRef.current = lang
      lastSeqRef.current = {}
      setEvents({})
    }

    const subscribeAll = (ws: WebSocket) => {
      for (const id of runIds) {
        ws.send(JSON.stringify({
          op: 'sub', run_id: id, from_seq: lastSeqRef.current[id] || 0,
        }))
      }
    }

    const connect = async () => {
      if (closedRef.current || !token || runIds.length === 0) return
      const ticket = await mintTicket(token)
      if (!ticket || closedRef.current) return
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(
        `${proto}://${location.host}/ws/runs?ticket=${encodeURIComponent(ticket)}`
        + (lang ? `&lang=${encodeURIComponent(lang)}` : ''))
      wsRef.current = ws

      ws.onopen = () => { backoff = 500; setConnected(true); subscribeAll(ws) }
      ws.onclose = () => {
        setConnected(false)
        if (!closedRef.current) {
          reconnectTimer = setTimeout(connect, backoff)
          backoff = Math.min(backoff * 2, 15000)
        }
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (ev) => {
        let msg: any
        try { msg = JSON.parse(ev.data) } catch { return }
        if (msg.type === 'event') {
          const rid = msg.run_id
          lastSeqRef.current[rid] = Math.max(lastSeqRef.current[rid] || 0, msg.seq)
          setEvents((prev) => {
            const list = (prev[rid] || []).concat({
              seq: msg.seq, event_type: msg.event_type, ts: msg.ts,
              payload: msg.payload,
            })
            // cap in-memory history; the journal endpoint has the full record
            const trimmed = list.length > 2000 ? list.slice(list.length - 2000) : list
            return { ...prev, [rid]: trimmed }
          })
        } else if (msg.type === 'tick') {
          // a tick belongs to whichever run drained it (the server sends it
          // per-subscription); attach it to every watched run of that symbol
          const tick: RunTick = {
            symbol: msg.symbol, market: msg.market, price: msg.price, ts: msg.ts,
          }
          setTicks((prev) => {
            const next = { ...prev }
            for (const id of runIds) {
              const prevTick = next[id]
              if (!prevTick || prevTick.symbol === msg.symbol) next[id] = tick
            }
            return next
          })
        } else if (msg.type === 'resync_required') {
          // drop our cursor and re-subscribe from scratch on next open
          lastSeqRef.current[msg.run_id] = 0
        }
      }
    }

    connect()
    // visibility fast-forward: on refocus, force a fresh subscribe so the
    // server backfills anything the throttled tab missed
    const onVis = () => {
      if (document.visibilityState === 'visible' && wsRef.current
          && wsRef.current.readyState === WebSocket.OPEN) {
        subscribeAll(wsRef.current)
      }
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      closedRef.current = true
      document.removeEventListener('visibilitychange', onVis)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (wsRef.current) wsRef.current.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, runIdsKey, lang])

  return { connected, eventsByRun, tickByRun, lastSeqByRun: lastSeqRef.current }
}
