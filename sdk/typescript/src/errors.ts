/**
 * Exception hierarchy for the @aitrad/sdk package.
 *
 * All SDK errors derive from AITRADError so callers can catch
 * everything with a single `instanceof AITRADError` check.
 */

export class AITRADError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AITRADError";
  }
}

export class AuthError extends AITRADError {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}

export class NotFound extends AITRADError {
  constructor(message: string) {
    super(message);
    this.name = "NotFound";
  }
}

export class APIError extends AITRADError {
  readonly statusCode: number;
  readonly body: string;

  constructor(statusCode: number, body: string = "") {
    super(`AITRAD API returned ${statusCode}: ${body.slice(0, 200)}`);
    this.name = "APIError";
    this.statusCode = statusCode;
    this.body = body;
  }
}
