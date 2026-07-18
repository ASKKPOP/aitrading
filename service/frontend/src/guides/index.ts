// Route → page-guide registry.
//
// Each entry is a dynamic import rather than a static one, so opening the
// guide fetches only that page's content instead of all five languages of
// every guide at once. Vite emits one small chunk per guide file.
//
// `resolveGuide` matches the exact path first, then the longest registered
// path that prefixes it, so `/teams/:key` falls back to the `/teams` guide
// and `/challenges/abc` falls back to `/challenges`.

import type { PageGuide } from './types'

type GuideLoader = () => Promise<PageGuide>

export const GUIDES: Record<string, GuideLoader> = {
  // Root renders LeaderboardPage, same as /leaderboard.
  '/': () => import('./leaderboard').then(m => m.leaderboardGuide),
  '/leaderboard': () => import('./leaderboard').then(m => m.leaderboardGuide),

  '/market': () => import('./market').then(m => m.marketGuide),
  '/signals-board': () => import('./signalsBoard').then(m => m.signalsBoardGuide),
  '/financial-events': () => import('./financialEvents').then(m => m.financialEventsGuide),
  '/docs': () => import('./docs').then(m => m.docsGuide),

  '/trade': () => import('./trade').then(m => m.tradeGuide),
  '/spot': () => import('./spot').then(m => m.spotGuide),
  '/futures': () => import('./futures').then(m => m.futuresGuide),
  '/exchange': () => import('./exchange').then(m => m.exchangeGuide),
  '/positions': () => import('./positions').then(m => m.positionsGuide),

  '/backtest': () => import('./backtest').then(m => m.backtestGuide),
  '/monitor': () => import('./monitor').then(m => m.monitorGuide),
  '/analyst': () => import('./analyst').then(m => m.analystGuide),
  '/consult': () => import('./consult').then(m => m.consultGuide),

  '/automation': () => import('./automation').then(m => m.automationGuide),
  '/accounts': () => import('./accounts').then(m => m.accountsGuide),
  '/assets': () => import('./assets').then(m => m.assetsGuide),
  '/settings': () => import('./settings').then(m => m.settingsGuide),

  '/challenges': () => import('./challenges').then(m => m.challengesGuide),
  '/team-missions': () => import('./teamMissions').then(m => m.teamMissionsGuide),
  '/teams': () => import('./teamMissions').then(m => m.teamMissionsGuide),
  '/strategies': () => import('./strategies').then(m => m.strategiesGuide),
  '/discussions': () => import('./discussions').then(m => m.discussionsGuide),
  '/agent': () => import('./agentProfile').then(m => m.agentProfileGuide),

  '/my-trading': () => import('./myTrading').then(m => m.myTradingGuide),
  '/notifications': () => import('./notifications').then(m => m.notificationsGuide),
  '/support': () => import('./support').then(m => m.supportGuide),
  '/subscribe': () => import('./subscribe').then(m => m.subscribeGuide),
  '/contract': () => import('./contract').then(m => m.contractGuide),
  '/experiments': () => import('./experiments').then(m => m.experimentsGuide),
  '/research-exports': () => import('./researchExports').then(m => m.researchExportsGuide),
  '/dev': () => import('./dev').then(m => m.devGuide),
}

/** The registered route whose guide covers `pathname`, or null. */
export function matchGuideRoute(pathname: string): string | null {
  if (GUIDES[pathname]) return pathname

  let best: string | null = null
  for (const key of Object.keys(GUIDES)) {
    if (key === '/') continue
    if (pathname.startsWith(key + '/') && (best === null || key.length > best.length)) {
      best = key
    }
  }
  return best
}

/** Loads the guide for `pathname`, or resolves null when none is registered. */
export async function resolveGuide(pathname: string): Promise<PageGuide | null> {
  const key = matchGuideRoute(pathname)
  return key ? GUIDES[key]() : null
}

export type { PageGuide, GuideSection, GuideFaq } from './types'
