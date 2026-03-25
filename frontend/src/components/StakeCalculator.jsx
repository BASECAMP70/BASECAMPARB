import { useContext } from 'react'
import { BankrollContext } from '../App'

const BOOK_DISPLAY = {
  playalberta: 'PlayAlberta', betmgm: 'BetMGM', fanduel: 'FanDuel',
  bet365: 'Bet365', sportsinteraction: 'Sports Interaction', betway: 'Betway',
}

const BOOK_SPORT_URL = {
  playalberta: { nhl: 'https://www.playalberta.ca/sports/hockey', nba: 'https://www.playalberta.ca/sports/basketball', mlb: 'https://www.playalberta.ca/sports/baseball', _default: 'https://www.playalberta.ca/sports' },
  bet365:      { nhl: 'https://www.bet365.ca/en/sports/ice-hockey/nhl/', nba: 'https://www.bet365.ca/en/sports/basketball/', mlb: 'https://www.bet365.ca/en/sports/baseball/', _default: 'https://www.bet365.ca' },
  sportsinteraction: { nhl: 'https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/', _default: 'https://www.sportsinteraction.com' },
  betmgm: { _default: 'https://sports.betmgm.ca' },
  fanduel: { _default: 'https://www.fanduel.com/sports/alberta' },
  betway: { _default: 'https://www.betway.com/en-ca' },
}
const getBookUrl = (book, sport) => { const m = BOOK_SPORT_URL[book] || {}; return m[sport] || m._default || '#' }

const MARKET_LABEL = { moneyline: 'Moneyline', spread: 'Spread', totals: 'Over/Under' }

const BOOK_MARKET_COLUMN = {
  playalberta: { spread: 'Puck Line', moneyline: 'Money Line', totals: 'Total' },
  bet365:      { spread: 'Puck Line', moneyline: 'Money Line', totals: 'Over/Under' },
  sportsinteraction: { spread: 'Puck Line', moneyline: 'Money Line', totals: 'Total' },
  betmgm:      { spread: 'Spread',    moneyline: 'Moneyline',   totals: 'Total' },
  fanduel:     { spread: 'Spread',    moneyline: 'Moneyline',   totals: 'Total' },
  betway:      { spread: 'Spread',    moneyline: 'Moneyline',   totals: 'Over/Under' },
}
const getColumnLabel = (book, market) =>
  (BOOK_MARKET_COLUMN[book] || {})[market] || MARKET_LABEL[market] || market

function displayOdds(book, decimal) {
  return decimal.toFixed(2)
}

function timeAgo(isoStr) {
  if (!isoStr) return null
  const secs = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (secs < 60)   return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

function calculateStakes(bankroll, legs) {
  const implied = legs.map(l => 1 / l.decimal_odds)
  const arbSum = implied.reduce((a, b) => a + b, 0)
  return implied.map(imp => (bankroll * imp / arbSum).toFixed(2))
}

export default function StakeCalculator({ opportunity }) {
  const bankroll = useContext(BankrollContext)
  const stakes = calculateStakes(bankroll, opportunity.outcomes)
  const profit = (bankroll * opportunity.margin).toFixed(2)
  const marketLabel = MARKET_LABEL[opportunity.market] || opportunity.market

  return (
    <div className="stake-calc">
      {opportunity.outcomes.map((leg, i) => (
        <div key={leg.outcome} className="stake-row">
          <span className="stake-book">{BOOK_DISPLAY[leg.book] || leg.book}</span>
          <span className="stake-arrow">→</span>
          <span className="stake-selection">{leg.participant || leg.outcome}</span>
          <span className="stake-market-badge" title="Column name on sportsbook site">
            {getColumnLabel(leg.book, opportunity.market)}
          </span>
          <span className="stake-meta">@ {displayOdds(leg.book, leg.decimal_odds)} · stake <strong>${stakes[i]}</strong></span>
          {leg.scraped_at && (
            <span className="stake-scraped-at" title={`Odds fetched at ${leg.scraped_at}`}>
              🕐 {timeAgo(leg.scraped_at)}
            </span>
          )}
          <a
            className="stake-open-link"
            href={getBookUrl(leg.book, opportunity.sport)}
            target="_blank"
            rel="noopener noreferrer"
          >Open ↗</a>
        </div>
      ))}
      <div className="stake-profit">Guaranteed profit: ${profit} ({(opportunity.margin * 100).toFixed(2)}%)</div>
    </div>
  )
}
