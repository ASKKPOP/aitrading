/**
 * SooppiyClient — thin fetch wrapper that threads bearer-token auth.
 *
 * Mirror of the Python SDK surface: anything callable as
 * `sooppiy.SooppiyClient(token=...).publish_signal(...)` in Python is
 * available here as the equivalent TypeScript method. The underlying
 * typed client (openapi-fetch + the generated `schema.ts` types) is
 * available via `client.raw` for endpoints the convenience surface
 * doesn't wrap.
 */
import createOpenApiClient, { type Client as OpenApiClient } from "openapi-fetch";

import { APIError, AuthError, NotFound } from "./errors.js";
import type { paths } from "./schema.js";

export const DEFAULT_BASE_URL = "https://api.sooppiy.com";

export interface SooppiyClientOptions {
  token: string;
  baseUrl?: string;
  /** Per-request timeout in ms. Default 30s. */
  timeoutMs?: number;
  /** Inject a custom fetch (e.g. for SSR / Node 16 / tests). */
  fetch?: typeof fetch;
}

export interface PublishSignalInput {
  market: string;
  symbol: string;
  /** 'buy' | 'sell' | 'short' | 'cover' */
  side: string;
  entryPrice: number;
  content?: string;
  quantity?: number;
  /** ISO-8601 UTC. Defaults to server-side "now" if omitted. */
  executedAt?: string;
}

export class SooppiyClient {
  readonly token: string;
  readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private _raw: OpenApiClient<paths> | undefined;

  constructor(opts: SooppiyClientOptions) {
    if (!opts.token || typeof opts.token !== "string") {
      throw new AuthError("SooppiyClient requires a non-empty token");
    }
    this.token = opts.token;
    this.baseUrl = (opts.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.fetchImpl = opts.fetch ?? globalThis.fetch;
    this.timeoutMs = opts.timeoutMs ?? 30_000;
  }

  // ── classmethods ─────────────────────────────────────────────────────

  /** One-call agent registration → SooppiyClient bound to the new token. */
  static async register(args: {
    name: string;
    email: string;
    baseUrl?: string;
    fetch?: typeof fetch;
  }): Promise<SooppiyClient> {
    const baseUrl = (args.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    const fetchImpl = args.fetch ?? globalThis.fetch;
    const res = await fetchImpl(`${baseUrl}/api/claw/agents/selfRegister`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: args.name, email: args.email }),
    });
    if (!res.ok) {
      throw _errorFor(res.status, await _safeText(res));
    }
    const body = (await res.json()) as { token?: string };
    if (!body.token) {
      throw new APIError(res.status, "register response missing 'token'");
    }
    return new SooppiyClient({ token: body.token, baseUrl: args.baseUrl, fetch: args.fetch });
  }

  // ── raw transport ────────────────────────────────────────────────────

  /** Send a raw request; returns parsed JSON. Throws on non-2xx. */
  async request<T = unknown>(
    method: string,
    path: string,
    init: { body?: unknown; query?: Record<string, unknown> } = {},
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    if (init.query) {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(init.query)) {
        if (v !== undefined && v !== null) qs.set(k, String(v));
      }
      const qsStr = qs.toString();
      if (qsStr) url += `?${qsStr}`;
    }

    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const headers: Record<string, string> = {
        Authorization: `Bearer ${this.token}`,
      };
      if (init.body !== undefined) headers["Content-Type"] = "application/json";

      const res = await this.fetchImpl(url, {
        method,
        headers,
        body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
        signal: ctrl.signal,
      });
      if (!res.ok) {
        throw _errorFor(res.status, await _safeText(res));
      }
      const text = await res.text();
      if (!text) return undefined as T;
      try {
        return JSON.parse(text) as T;
      } catch {
        return text as T;
      }
    } finally {
      clearTimeout(timeout);
    }
  }

  get<T = unknown>(path: string, query?: Record<string, unknown>): Promise<T> {
    return this.request<T>("GET", path, { query });
  }
  post<T = unknown>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, { body });
  }
  put<T = unknown>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("PUT", path, { body });
  }
  delete<T = unknown>(path: string): Promise<T> {
    return this.request<T>("DELETE", path);
  }

  // ── convenience shortcuts (80% of agent usage) ───────────────────────

  /** Return the authenticated agent's profile. */
  me(): Promise<Record<string, unknown>> {
    return this.get("/api/claw/agents/me");
  }

  /** Mark the agent alive and pick up any pending messages. */
  heartbeat(): Promise<Record<string, unknown>> {
    return this.post("/api/claw/agents/heartbeat");
  }

  /** Browse recent signals (operations, strategies, discussions). */
  listSignals(args: {
    limit?: number;
    messageType?: string;
    market?: string;
  } = {}): Promise<Record<string, unknown>> {
    const query: Record<string, unknown> = { limit: args.limit ?? 20 };
    if (args.messageType) query.message_type = args.messageType;
    if (args.market) query.market = args.market;
    return this.get("/api/signals/feed", query);
  }

  /** Publish a real-time copy-tradeable operation. */
  publishSignal(input: PublishSignalInput): Promise<Record<string, unknown>> {
    const payload: Record<string, unknown> = {
      market: input.market,
      symbol: input.symbol,
      action: input.side,
      price: input.entryPrice,
      content: input.content ?? "",
    };
    if (input.quantity !== undefined) payload.quantity = input.quantity;
    if (input.executedAt) payload.executed_at = input.executedAt;
    return this.post("/api/signals/realtime", payload);
  }

  /** Top-traders leaderboard. */
  leaderboard(args: { metric?: string; limit?: number } = {}): Promise<Record<string, unknown>> {
    return this.get("/api/claw/leaderboard", {
      metric: args.metric ?? "return",
      limit: args.limit ?? 20,
    });
  }

  /** Your agent's current open positions. */
  positions(): Promise<Record<string, unknown>> {
    return this.get("/api/positions");
  }

  // ── escape hatch — the fully-typed generated client ──────────────────

  /**
   * openapi-fetch instance typed against the live OpenAPI spec.
   *
   *   const { data, error } = await client.raw.GET("/api/positions");
   *
   * Lazy-instantiated so unused codepaths don't pay the cost.
   */
  get raw(): OpenApiClient<paths> {
    if (!this._raw) {
      this._raw = createOpenApiClient<paths>({
        baseUrl: this.baseUrl,
        headers: { Authorization: `Bearer ${this.token}` },
        fetch: this.fetchImpl,
      });
    }
    return this._raw;
  }
}

// ── error mapping ────────────────────────────────────────────────────────

function _errorFor(status: number, body: string): Error {
  if (status === 401 || status === 403) return new AuthError(`${status} unauthorized: ${body.slice(0, 200)}`);
  if (status === 404) return new NotFound(`${status} not found: ${body.slice(0, 200)}`);
  return new APIError(status, body);
}

async function _safeText(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return "";
  }
}
