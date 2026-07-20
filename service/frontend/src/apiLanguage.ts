// Tags every /api request with the language picked in the top bar, so the
// backend can localize the error messages it raises (server-side
// i18n_errors.py does the lookup).
//
// This patches window.fetch rather than adding a request wrapper because the
// app calls fetch directly from ~190 places. A wrapper would mean touching
// every one of them and would silently miss the next one somebody writes;
// patching catches all of them, including future ones, at a single point.

import { DEFAULT_LANGUAGE, LANGUAGES, Language } from './i18n'

const STORAGE_KEY = 'sooppiy_language'

// Read at call time, not module load — the header has to follow a language
// switch immediately, without a page reload.
function currentLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && LANGUAGES.some(l => l.value === saved)) return saved as Language
  } catch {
    // Private-mode / disabled storage: fall through to the default.
  }
  return DEFAULT_LANGUAGE
}

function isApiRequest(input: RequestInfo | URL): boolean {
  const url = typeof input === 'string' ? input
    : input instanceof URL ? input.href
    : input.url
  if (!url) return false
  // Same-origin API calls only. Never attach the header to a third-party
  // request — it would leak the user's language to an unrelated host and can
  // trip CORS preflight on endpoints that don't allow the header.
  if (/^https?:\/\//i.test(url)) {
    try {
      return new URL(url).origin === window.location.origin
        && new URL(url).pathname.startsWith('/api')
    } catch {
      return false
    }
  }
  return url.startsWith('/api')
}

export function installLanguageHeader(): void {
  const original = window.fetch
  window.fetch = function patchedFetch(input, init) {
    if (!isApiRequest(input)) return original.call(this, input, init)

    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined),
    )
    // An explicit Accept-Language from the caller wins — nothing sets one
    // today, but this keeps the patch from overriding a deliberate choice.
    if (!headers.has('Accept-Language')) {
      headers.set('Accept-Language', currentLanguage())
    }
    return original.call(this, input, { ...init, headers })
  }
}
