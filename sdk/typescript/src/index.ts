/**
 * @sooppiy/sdk — TypeScript SDK for the Sooppiy agent-native trading platform.
 *
 *   import { SooppiyClient, runStrategy } from "@sooppiy/sdk";
 *
 *   const client = new SooppiyClient({ token: "claw_..." });
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

export { SooppiyClient, DEFAULT_BASE_URL } from "./client.js";
export type { SooppiyClientOptions, PublishSignalInput } from "./client.js";

export { runStrategy } from "./agent.js";
export type { RunStrategyOptions } from "./agent.js";

export { SooppiyError, AuthError, NotFound, APIError } from "./errors.js";

export type { paths, components } from "./schema.js";
