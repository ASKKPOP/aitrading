// Per-page user guide content model.
//
// English is required; every other language is optional and falls back to it.
//
// This used to be Record<Language, string> — every language mandatory. That
// read as a stronger guarantee than it was: GuidePanel has always rendered
// these through tr() and `bullets[language] ?? bullets.en`, so a missing
// language was already an English fallback at runtime. The only thing the
// exhaustive type actually enforced was that adding a seventh language is a
// 604-error build break until ~135,000 characters of documentation prose have
// been translated — which pressures whoever adds it into bulk machine output,
// the exact failure this corpus is meant to avoid.
//
// Optional-with-fallback lets a language ship its UI immediately and its
// long-form guide as it is written and reviewed. `en` stays required because
// the fallback has to land somewhere.

import type { Language } from '../i18n'

export type L = { en: string } & Partial<Record<Language, string>>
export type LList = { en: string[] } & Partial<Record<Language, string[]>>

export type GuideSection = {
  heading: L
  bullets: LList
}

export type GuideFaq = {
  q: L
  a: L
}

export type PageGuide = {
  /** Panel title — usually the page name. */
  title: L
  /** One or two sentences: what this page is for and who uses it. */
  summary: L
  /** Ordered walkthrough of the page: controls, panels, workflows. */
  sections: GuideSection[]
  /** Common questions and gotchas. Optional. */
  faq?: GuideFaq[]
}
