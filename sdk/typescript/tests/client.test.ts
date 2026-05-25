/**
 * Unit tests for @aitrad/sdk. No real network — every test injects a
 * fake `fetch` implementation so we can assert request shape and inject
 * canned responses.
 */
import { afterEach, describe, expect, it } from "vitest";

import {
  AITRADClient,
  AITRADError,
  APIError,
  AuthError,
  NotFound,
  runStrategy,
} from "../src/index.js";

// ── fake-fetch harness ────────────────────────────────────────────────────

interface FakeReq {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | undefined;
}

interface FakeResp {
  status?: number;
  body?: unknown;
}

function makeFakeFetch(responses: FakeResp | FakeResp[]) {
  const queue = Array.isArray(responses) ? [...responses] : [responses];
  const requests: FakeReq[] = [];

  const fake = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : (input as URL).toString();
    const headers: Record<string, string> = {};
    if (init.headers) {
      const h = new Headers(init.headers as HeadersInit);
      h.forEach((v, k) => { headers[k] = v; });
    }
    requests.push({
      url,
      method: (init.method ?? "GET").toUpperCase(),
      headers,
      body: typeof init.body === "string" ? init.body : undefined,
    });
    const next = queue.shift() ?? { status: 200, body: {} };
    const status = next.status ?? 200;
    const bodyText =
      typeof next.body === "string"
        ? next.body
        : next.body === undefined
          ? ""
          : JSON.stringify(next.body);
    return new Response(bodyText, {
      status,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;

  return { fetch: fake, requests, remaining: () => queue.length };
}

// ── constructor + auth-header threading ───────────────────────────────────

describe("AITRADClient construction", () => {
  it("requires a non-empty token", () => {
    expect(() => new AITRADClient({ token: "" })).toThrow(AuthError);
  });

  it("requires a string token", () => {
    expect(
      // @ts-expect-error — testing runtime guard against bad types
      () => new AITRADClient({ token: undefined }),
    ).toThrow(AuthError);
  });

  it("threads bearer-token in Authorization header", async () => {
    const f = makeFakeFetch({ body: { id: 1, name: "bot" } });
    const c = new AITRADClient({ token: "claw_xyz", fetch: f.fetch });
    await c.me();
    expect(f.requests[0]!.headers.authorization).toBe("Bearer claw_xyz");
  });

  it("uses custom base URL", async () => {
    const f = makeFakeFetch({ body: { ok: true } });
    const c = new AITRADClient({
      token: "t",
      baseUrl: "http://localhost:8001",
      fetch: f.fetch,
    });
    const out = (await c.me()) as { ok: boolean };
    expect(out.ok).toBe(true);
    expect(f.requests[0]!.url).toBe("http://localhost:8001/api/claw/agents/me");
  });

  it("strips trailing slashes from baseUrl", async () => {
    const f = makeFakeFetch({ body: { ok: true } });
    const c = new AITRADClient({
      token: "t",
      baseUrl: "https://api.sooppiy.com//",
      fetch: f.fetch,
    });
    await c.me();
    expect(f.requests[0]!.url).toBe("https://api.sooppiy.com/api/claw/agents/me");
  });
});

// ── error mapping ─────────────────────────────────────────────────────────

describe("error mapping", () => {
  it("401 → AuthError", async () => {
    const f = makeFakeFetch({ status: 401, body: { detail: "bad" } });
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    await expect(c.me()).rejects.toBeInstanceOf(AuthError);
  });

  it("404 → NotFound", async () => {
    const f = makeFakeFetch({ status: 404, body: { detail: "nope" } });
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    await expect(c.me()).rejects.toBeInstanceOf(NotFound);
  });

  it("500 → APIError with status & body", async () => {
    const f = makeFakeFetch({ status: 500, body: { detail: "boom" } });
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    try {
      await c.me();
      throw new Error("expected to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(APIError);
      expect((err as APIError).statusCode).toBe(500);
      expect((err as APIError).body).toContain("boom");
    }
  });

  it("all errors extend AITRADError", () => {
    expect(new AuthError("x")).toBeInstanceOf(AITRADError);
    expect(new NotFound("x")).toBeInstanceOf(AITRADError);
    expect(new APIError(500, "x")).toBeInstanceOf(AITRADError);
  });
});

// ── convenience shortcuts ─────────────────────────────────────────────────

describe("convenience shortcuts", () => {
  it("listSignals threads query params", async () => {
    const f = makeFakeFetch({ body: { signals: [] } });
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    await c.listSignals({ limit: 10, messageType: "operation", market: "us-stock" });
    const url = new URL(f.requests[0]!.url);
    expect(url.pathname).toBe("/api/signals/feed");
    expect(url.searchParams.get("limit")).toBe("10");
    expect(url.searchParams.get("message_type")).toBe("operation");
    expect(url.searchParams.get("market")).toBe("us-stock");
  });

  it("publishSignal builds the realtime payload", async () => {
    const f = makeFakeFetch({ body: { signal_id: 42 } });
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    await c.publishSignal({
      market: "us-stock",
      symbol: "AAPL",
      side: "buy",
      entryPrice: 195.5,
      content: "breakout",
    });
    const body = JSON.parse(f.requests[0]!.body!) as {
      market: string; symbol: string; action: string; price: number; content: string;
    };
    expect(body.market).toBe("us-stock");
    expect(body.symbol).toBe("AAPL");
    expect(body.action).toBe("buy");       // side → action mapping
    expect(body.price).toBe(195.5);
    expect(body.content).toBe("breakout");
  });

  it("register returns an authed client bound to the new token", async () => {
    const f = makeFakeFetch({ body: { token: "claw_new", botUserId: "agent_1" } });
    const c = await AITRADClient.register({
      name: "my-bot",
      email: "bot@x.io",
      fetch: f.fetch,
    });
    expect(c).toBeInstanceOf(AITRADClient);
    expect(c.token).toBe("claw_new");
  });

  it("register throws on missing token in response", async () => {
    const f = makeFakeFetch({ body: { error: "denied" } });
    await expect(
      AITRADClient.register({ name: "bot", email: "x@x", fetch: f.fetch }),
    ).rejects.toThrow(/missing 'token'/);
  });

  it("leaderboard + positions hit the right URLs", async () => {
    const f = makeFakeFetch([
      { body: { leaderboard: [] } },
      { body: { positions: [] } },
    ]);
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    await c.leaderboard();
    await c.positions();
    expect(f.requests[0]!.url).toContain("/api/claw/leaderboard");
    expect(f.requests[1]!.url).toContain("/api/positions");
  });
});

// ── runStrategy polling helper ────────────────────────────────────────────

describe("runStrategy", () => {
  it("skips signals already in the bootstrap fetch", async () => {
    const f = makeFakeFetch([
      { body: { signals: [{ signal_id: 1, symbol: "AAPL" }] } },   // bootstrap
      { body: { signals: [{ signal_id: 1, symbol: "AAPL" }] } },   // poll: same id
    ]);
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    const seen: Record<string, unknown>[] = [];
    await runStrategy((s) => { seen.push(s); }, {
      client: c, intervalMs: 0, maxIterations: 1,
    });
    expect(seen).toHaveLength(0);
  });

  it("fires handler for new signals", async () => {
    const f = makeFakeFetch([
      { body: { signals: [] } },
      { body: { signals: [
        { signal_id: 7, symbol: "BTC" },
        { signal_id: 8, symbol: "ETH" },
      ] } },
    ]);
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    const seen: Record<string, unknown>[] = [];
    await runStrategy((s) => { seen.push(s); }, {
      client: c, intervalMs: 0, maxIterations: 1,
    });
    expect(seen.map((s) => s.signal_id)).toEqual([7, 8]);
  });

  it("handler exception does not kill the loop", async () => {
    const f = makeFakeFetch([
      { body: { signals: [] } },
      { body: { signals: [{ signal_id: 1 }, { signal_id: 2 }] } },
    ]);
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    const fired: number[] = [];
    const errors: unknown[] = [];
    await runStrategy(
      (s) => {
        fired.push(s.signal_id as number);
        throw new Error("oops");
      },
      {
        client: c, intervalMs: 0, maxIterations: 1,
        onHandlerError: (err) => errors.push(err),
      },
    );
    expect(fired).toEqual([1, 2]);
    expect(errors).toHaveLength(2);
  });

  it("absorbs bare-array response shape from the feed", async () => {
    const f = makeFakeFetch([
      { body: [] },                              // bootstrap as bare array
      { body: [{ signal_id: 99 }] },             // poll as bare array
    ]);
    const c = new AITRADClient({ token: "t", fetch: f.fetch });
    const seen: Record<string, unknown>[] = [];
    await runStrategy((s) => { seen.push(s); }, {
      client: c, intervalMs: 0, maxIterations: 1,
    });
    expect(seen).toHaveLength(1);
  });

  it("invokes onPollError when the poll itself throws", async () => {
    let calls = 0;
    const errFetch = (async () => {
      calls += 1;
      if (calls === 1) {
        // bootstrap success — empty list, no seeding
        return new Response(JSON.stringify({ signals: [] }), { status: 200 });
      }
      throw new Error("network down");
    }) as typeof fetch;
    const c = new AITRADClient({ token: "t", fetch: errFetch });
    const errors: unknown[] = [];
    await runStrategy(() => {}, {
      client: c, intervalMs: 0, maxIterations: 1,
      onPollError: (err) => errors.push(err),
    });
    expect(errors).toHaveLength(1);
  });
});

// ── raw escape hatch ──────────────────────────────────────────────────────

describe("client.raw escape hatch", () => {
  it("is lazy-instantiated on first access", () => {
    const c = new AITRADClient({ token: "t" });
    // intentionally peek at the internal field
    const before = (c as unknown as { _raw?: unknown })._raw;
    expect(before).toBeUndefined();
    void c.raw;
    const after = (c as unknown as { _raw?: unknown })._raw;
    expect(after).toBeDefined();
  });
});

afterEach(() => {
  // nothing to clean up — each test owns its own fake fetch
});
