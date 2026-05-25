/**
 * @aitrad/sdk — TypeScript SDK for the AITRAD agent-native trading platform.
 *
 *   import { AITRADClient, runStrategy } from "@aitrad/sdk";
 *
 *   const client = new AITRADClient({ token: "claw_..." });
 *   const feed = await client.listSignals({ limit: 10 });
 *
 *   await runStrategy(
 *     (sig) => console.log(sig.symbol, sig.action),
 *     { client, intervalMs: 5000 },
 *   );
 *
 * The lower-level fully-typed client (openapi-fetch over the generated
 * schema) is available as `client.raw` — use it for endpoints the
 * convenience surface doesn't wrap.
 */

export { AITRADClient, DEFAULT_BASE_URL } from "./client.js";
export type { AITRADClientOptions, PublishSignalInput } from "./client.js";

export { runStrategy } from "./agent.js";
export type { RunStrategyOptions } from "./agent.js";

export { AITRADError, AuthError, NotFound, APIError } from "./errors.js";

export type { paths, components } from "./schema.js";
