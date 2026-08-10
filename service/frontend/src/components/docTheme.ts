// Site-theme injection for guide documents rendered in a same-origin srcdoc
// iframe. Extracted from DocsPage — where every trap below was found — so the
// in-page guide overlay (GuideDocOverlay) and the /docs rail cannot drift.
//
// Documents ship their own light/dark palette keyed on prefers-color-scheme,
// which follows the OS — not this app's theme. On the 'claude' theme (always
// dark) with a light OS that produced dark text on a dark surface. So the
// SITE's resolved theme variables are pushed into the document and it paints
// with them.
//
// The page background is PAINTED, not left transparent: a transparent page
// under color-scheme:dark makes the browser fall back to its own black
// canvas, which on the warm-charcoal 'claude' surface reads as a black box
// around the document.
//
// Documents disagree on variable names — --page/--bg/--ground for the page,
// --card/--panel/--surface for a raised surface, --ink-2/--ink2/--ink-3 for
// secondary text — so every alias in guide_content/ is mapped. A name no
// document uses simply goes unread. Borders come from the site's border
// tokens, NOT --bg-tertiary: on 'claude' that fill is barely one shade off
// the card, and every diagram stroke painted with it disappeared. --grid
// stays a hairline; every other border alias gets --border-strong.
//
// Each document also brought its OWN measure (860–1120px, self-centred), so
// the container width is neutralised and the embedder decides the column.

/** Is the SITE currently dark? 'signal' and 'claude' are dark, 'light' is
 *  not; before the theme is applied fall back to the OS. */
export function siteIsDark(): boolean {
  const t = document.documentElement.getAttribute('data-theme')
  return t ? t !== 'light' : matchMedia('(prefers-color-scheme: dark)').matches
}

/** Inject (or refresh) the site palette into a guide document's iframe
 *  contentDocument. Returns whether the site is dark — the caller mirrors
 *  that onto the iframe element's colorScheme, which is what makes the
 *  document's own prefers-color-scheme block follow the site theme instead
 *  of the reader's OS (inside a nested browsing context it resolves against
 *  the EMBEDDER element). */
export function injectSiteTheme(doc: Document | null | undefined): boolean {
  const dark = siteIsDark()
  if (!doc?.body) return dark
  try {
    const root = getComputedStyle(document.documentElement)
    const v = (name: string) => root.getPropertyValue(name).trim()
    const page = v('--bg-primary')
    const card = v('--bg-card')
    const surface = v('--bg-secondary')
    const hairline = v('--border-color')
    const strong = v('--border-strong')
    const ink = v('--text-primary')
    const ink2 = v('--text-secondary')
    const muted = v('--text-muted')
    const accent = v('--accent-primary')
    let style = doc.getElementById('site-theme') as HTMLStyleElement | null
    if (!style) {
      style = doc.createElement('style')
      style.id = 'site-theme'
      doc.head.appendChild(style)
    }
    style.textContent = `
      :root,.viz-root{color-scheme:${dark ? 'dark' : 'light'};
        --page:${page}; --bg:${page}; --ground:${page}; --surface-0:${page};
        --card:${card}; --panel:${card}; --surface-1:${card};
        --surface:${surface}; --surf:${surface}; --panel-2:${surface}; --surface-2:${surface};
        --grid:${hairline};
        --border:${strong}; --bd:${strong}; --hair:${strong}; --line:${strong};
        --axis:${strong}; --baseline:${strong}; --border-strong:${strong};
        --ink:${ink}; --text-primary:${ink};
        --ink2:${ink2}; --ink-2:${ink2}; --ink-3:${muted}; --text-secondary:${ink2};
        --muted:${muted}; --text-muted:${muted};
        --accent:${accent}; --ai:${accent};}
      html,body,.viz-root{background:${page}}
      .wrap,main,.viz-root{max-width:none; padding-left:0; padding-right:0}
      main,.viz-root{padding-top:0}`
  } catch {
    /* styling is a nicety — never let it stop the document rendering */
  }
  return dark
}
