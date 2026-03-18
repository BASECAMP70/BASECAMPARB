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
          <span className="stake-market-badge">{marketLabel}</span>
          <span className="stake-meta">@ {leg.decimal_odds} · stake <strong>${stakes[i]}</strong></span>
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
