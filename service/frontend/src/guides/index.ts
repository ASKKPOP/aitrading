// Route → page-guide registry.
//
// Guides are keyed by route path. `resolveGuide` picks the most specific
// matching entry, so `/teams/:key` falls back to the `/teams` guide and
// `/challenges/abc` falls back to the `/challenges` guide.

import type { PageGuide } from './types'

import { accountsGuide } from './accounts'
import { agentProfileGuide } from './agentProfile'
import { analystGuide } from './analyst'
import { assetsGuide } from './assets'
import { automationGuide } from './automation'
import { backtestGuide } from './backtest'
import { challengesGuide } from './challenges'
import { consultGuide } from './consult'
import { contractGuide } from './contract'
import { devGuide } from './dev'
import { discussionsGuide } from './discussions'
import { docsGuide } from './docs'
import { exchangeGuide } from './exchange'
import { experimentsGuide } from './experiments'
import { financialEventsGuide } from './financialEvents'
import { futuresGuide } from './futures'
import { leaderboardGuide } from './leaderboard'
import { marketGuide } from './market'
import { monitorGuide } from './monitor'
import { myTradingGuide } from './myTrading'
import { positionsGuide } from './positions'
import { researchExportsGuide } from './researchExports'
import { settingsGuide } from './settings'
import { signalsBoardGuide } from './signalsBoard'
import { spotGuide } from './spot'
import { strategiesGuide } from './strategies'
import { subscribeGuide } from './subscribe'
import { teamMissionsGuide } from './teamMissions'
import { tradeGuide } from './trade'

export const GUIDES: Record<string, PageGuide> = {
  // Root renders LeaderboardPage, same as /leaderboard.
  '/': leaderboardGuide,
  '/leaderboard': leaderboardGuide,

  '/market': marketGuide,
  '/signals-board': signalsBoardGuide,
  '/financial-events': financialEventsGuide,
  '/docs': docsGuide,

  '/trade': tradeGuide,
  '/spot': spotGuide,
  '/futures': futuresGuide,
  '/exchange': exchangeGuide,
  '/positions': positionsGuide,

  '/backtest': backtestGuide,
  '/monitor': monitorGuide,
  '/analyst': analystGuide,
  '/consult': consultGuide,

  '/automation': automationGuide,
  '/accounts': accountsGuide,
  '/assets': assetsGuide,
  '/settings': settingsGuide,

  '/challenges': challengesGuide,
  '/team-missions': teamMissionsGuide,
  '/teams': teamMissionsGuide,
  '/strategies': strategiesGuide,
  '/discussions': discussionsGuide,
  '/agent': agentProfileGuide,

  '/my-trading': myTradingGuide,
  '/subscribe': subscribeGuide,
  '/contract': contractGuide,
  '/experiments': experimentsGuide,
  '/research-exports': researchExportsGuide,
  '/dev': devGuide,
}

/** Exact match first, then the longest registered path that prefixes it. */
export function resolveGuide(pathname: string): PageGuide | null {
  if (GUIDES[pathname]) return GUIDES[pathname]

  let best: string | null = null
  for (const key of Object.keys(GUIDES)) {
    if (key === '/') continue
    if (pathname.startsWith(key + '/') && (best === null || key.length > best.length)) {
      best = key
    }
  }
  return best ? GUIDES[best] : null
}

export type { PageGuide, GuideSection, GuideFaq } from './types'
