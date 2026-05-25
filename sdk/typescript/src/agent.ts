/**
 * runStrategy — minimal polling loop for an AITRAD agent.
 *
 * Polls the signal feed every `intervalMs`, deduplicates by signal id,
 * and fires `handler` for each new signal. Built for clarity not
 * throughput; when push-based market data ships (Phase 4.5) this will
 * be replaced with a WebSocket subscriber.
 */
import type { AITRADClient } from "./client.js";

export interface RunStrategyOptions {
  client: AITRADClient;
  /** ms between polls. Default 5000. */
  intervalMs?: number;
  /** Filter — "operation" (default), "strategy", "discussion", or null. */
  messageType?: string | null;
  /** Optional market filter — "us-stock", "crypto", etc. */
  market?: string;
  /** Size of the first fetch (to seed the seen-set). Default 50. */
  initialLimit?: number;
  /** Stop after N polls. Default Infinity. Mostly for tests. */
  maxIterations?: number;
  /** Hook called when the poll itself fails (network etc). No-op by default. */
  onPollError?: (err: unknown) => void;
  /** Hook called when handler throws. No-op by default. */
  onHandlerError?: (err: unknown, signal: Record<string, unknown>) => void;
}

/**
 * Poll the signal feed and dispatch new signals to `handler`.
 *
 *   await runStrategy(sig => console.log(sig), {
 *     client, intervalMs: 5000,
 *   });
 */
export async function runStrategy(
  handler: (signal: Record<string, unknown>) => void | Promise<void>,
  opts: RunStrategyOptions,
): Promise<void> {
  const {
    client,
    intervalMs = 5_000,
    messageType = "operation",
    market,
    initialLimit = 50,
    maxIterations = Number.POSITIVE_INFINITY,
    onPollError,
    onHandlerError,
  } = opts;

  const seen = new Set<number | string>();

  const listArgs: { limit: number; messageType?: string; market?: string } = {
    limit: initialLimit,
  };
  if (messageType) listArgs.messageType = messageType;
  if (market) listArgs.market = market;

  // Pre-seed `seen` with the current head so the bootstrap fetch doesn't
  // fire the handler against signals that already existed.
  const bootstrap = await client.listSignals(listArgs);
  for (const sig of _signalsFrom(bootstrap)) {
    const sid = _idOf(sig);
    if (sid !== undefined) seen.add(sid);
  }

  const pollArgs = { ...listArgs, limit: 20 };

  let iters = 0;
  while (iters < maxIterations) {
    iters += 1;

    let page: unknown;
    try {
      page = await client.listSignals(pollArgs);
    } catch (err) {
      onPollError?.(err);
      await _sleep(intervalMs);
      continue;
    }

    for (const sig of _signalsFrom(page)) {
      const sid = _idOf(sig);
      if (sid === undefined || seen.has(sid)) continue;
      seen.add(sid);
      try {
        await handler(sig);
      } catch (err) {
        onHandlerError?.(err, sig);
      }
    }

    if (iters < maxIterations) {
      await _sleep(intervalMs);
    }
  }
}

// ── helpers ───────────────────────────────────────────────────────────────

function _signalsFrom(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) return payload as Record<string, unknown>[];
  if (payload && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    for (const key of ["signals", "items", "results", "data"]) {
      const v = obj[key];
      if (Array.isArray(v)) return v as Record<string, unknown>[];
    }
  }
  return [];
}

function _idOf(sig: Record<string, unknown>): number | string | undefined {
  const id = sig.signal_id ?? sig.id;
  if (typeof id === "number" || typeof id === "string") return id;
  return undefined;
}

function _sleep(ms: number): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, ms));
}
