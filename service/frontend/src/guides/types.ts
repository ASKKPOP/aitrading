// Per-page user guide content model.
//
// Every string is localized across all five supported languages so the guide
// follows the UI language switcher rather than falling back to English.

import type { Language } from '../i18n'

export type L = Record<Language, string>
export type LList = Record<Language, string[]>

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
