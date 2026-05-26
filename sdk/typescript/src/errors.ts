/**
 * Exception hierarchy for the @sooppiy/sdk package.
 *
 * All SDK errors derive from SooppiyError so callers can catch
 * everything with a single `instanceof SooppiyError` check.
 */

export class SooppiyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SooppiyError";
  }
}

export class AuthError extends SooppiyError {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}

export class NotFound extends SooppiyError {
  constructor(message: string) {
    super(message);
    this.name = "NotFound";
  }
}

export class APIError extends SooppiyError {
  readonly statusCode: number;
  readonly body: string;

  constructor(statusCode: number, body: string = "") {
    super(`Sooppiy API returned ${statusCode}: ${body.slice(0, 200)}`);
    this.name = "APIError";
    this.statusCode = statusCode;
    this.body = body;
  }
}
