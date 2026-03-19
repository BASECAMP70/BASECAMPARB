import { useState, useContext } from 'react'
import { BankrollContext } from '../App'
import StakeCalculator from './StakeCalculator'

const SPORT_EMOJI = { nhl: '🏒', nfl: '🏈', nba: '🏀', mlb: '⚾', mls: '⚽', soccer: '⚽' }

const BOOK_DISPLAY = {
  playalberta: 'PlayAlberta',
  betmgm: 'BetMGM',
  fanduel: 'FanDuel',
  bet365: 'Bet365',
  sportsinteraction: 'Sports Interaction',
  betway: 'Betway',
}

// Sport-specific deep links for each book
const BOOK_SPORT_URL = {
  playalberta: {
    nhl:    'https://www.playalberta.ca/sports/hockey',
    nba:    'https://www.playalberta.ca/sports/basketball',
    mlb:    'https://www.playalberta.ca/sports/baseball',
    nfl:    'https://www.playalberta.ca/sports/football',
    soccer: 'https://www.playalberta.ca/sports/soccer',
    _default: 'https://www.playalberta.ca/sports',
  },
  bet365: {
    nhl:    'https://www.bet365.ca/en/sports/ice-hockey/nhl/',
    nba:    'https://www.bet365.ca/en/sports/basketball/',
    mlb:    'https://www.bet365.ca/en/sports/baseball/',
    nfl:    'https://www.bet365.ca/en/sports/american-football/',
    soccer: 'https://www.bet365.ca/en/sports/soccer/',
    _default: 'https://www.bet365.ca',
  },
  sportsinteraction: {
    nhl:    'https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/',
    nba:    'https://www.sportsinteraction.com/en-ca/sports-betting/basketball/',
    mlb:    'https://www.sportsinteraction.com/en-ca/sports-betting/baseball/',
    soccer: 'https://www.sportsinteraction.com/en-ca/sports-betting/soccer/',
    _default: 'https://www.sportsinteraction.com',
  },
  betmgm:  { _default: 'https://sports.betmgm.ca' },
  fanduel: { _default: 'https://www.fanduel.com/sports/alberta' },
  betway:  { _default: 'https://www.betway.com/en-ca' },
}

function getBookUrl(book, sport) {
  const map = BOOK_SPORT_URL[book] || {}
  return map[sport] || map._default || '#'
}

// Human-readable market labels (generic fallback)
const MARKET_LABEL = {
  moneyline: 'Moneyline',
  spread:    'Spread',
  totals:    'Over/Under',
}

// The exact column/field name each sportsbook uses on their site
const BOOK_MARKET_COLUMN = {
  playalberta: { spread: 'Puck Line', moneyline: 'Money Line', totals: 'Total' },
  bet365:      { spread: 'Puck Line', moneyline: 'Money Line', totals: 'Over/Under' },
  sportsinteraction: { spread: 'Puck Line', moneyline: 'Money Line', totals: 'Total' },
  betmgm:      { spread: 'Spread',    moneyline: 'Moneyline',   totals: 'Total' },
  fanduel:     { spread: 'Spread',    moneyline: 'Moneyline',   totals: 'Total' },
  betway:      { spread: 'Spread',    moneyline: 'Moneyline',   totals: 'Over/Under' },
}

function getColumnLabel(book, market) {
  return (BOOK_MARKET_COLUMN[book] || {})[market] || MARKET_LABEL[market] || market
}

// Books that natively display American odds (e.g. "+170", "-245")
const AMERICAN_ODDS_BOOKS = new Set(['bet365'])

// Display odds in the book's native format
function displayOdds(book, decimal) {
  if (!AMERICAN_ODDS_BOOKS.has(book)) return decimal.toFixed(2)
  // decimal → American
  if (decimal >= 2.0) return '+' + Math.round((decimal - 1) * 100)
  return '-' + Math.round(100 / (decimal - 1))
}

// Format an ISO scraped_at timestamp as "Xs ago" / "Xm ago"
function timeAgo(isoStr) {
  if (!isoStr) return null
  const secs = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (secs < 60)  return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

function calcLegs(bankroll, outcomes) {
  const implied = outcomes.map(o => 1 / o.decimal_odds)
  const arbSum = implied.reduce((a, b) => a + b, 0)
  return outcomes.map((o, i) => ({
    book: o.book,
    outcome: o.outcome,
    participant: o.participant || o.outcome,
    odds: o.decimal_odds,
    stake: (bankroll * implied[i] / arbSum).toFixed(2),
    scraped_at: o.scraped_at,
  }))
}

export default function OpportunitiesTable({ opps, newIds }) {
  const [expanded, setExpanded] = useState(new Set())
  const bankroll = useContext(BankrollContext)

  const sorted = Object.values(opps).sort((a, b) => {
    const aNew = newIds.has(a.id) ? 1 : 0
    const bNew = newIds.has(b.id) ? 1 : 0
    if (bNew !== aNew) return bNew - aNew
    return b.margin - a.margin
  })

  function toggleExpand(id) {
    setExpanded(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  if (sorted.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📊</div>
        <div className="empty-title">No arbitrage opportunities right now</div>
        <div className="empty-sub">Monitoring 5 Alberta sportsbooks every 45 seconds</div>
      </div>
    )
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Sport</th>
          <th>Event</th>
          <th>Market</th>
          <th>Profit</th>
          <th>Bet These Books</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(opp => {
          const isExp = expanded.has(opp.id)
          const isNew = newIds.has(opp.id)
          const legs = calcLegs(bankroll, opp.outcomes)
          const profit = (bankroll * opp.margin).toFixed(2)

          return (
            <>
              {/* Summary row */}
              <tr
                key={opp.id}
                className={`opp-row ${isNew ? 'new-flash' : ''}`}
                onClick={() => toggleExpand(opp.id)}
              >
                <td className="td-sport">{SPORT_EMOJI[opp.sport] || '🎯'} {opp.sport.toUpperCase()}</td>
                <td className="td-event">{opp.event_name}</td>
                <td className="td-market">{opp.market}</td>
                <td className="td-profit"><span className="profit-badge">+{(opp.margin * 100).toFixed(2)}%</span></td>
                <td className="td-bets">
                  <div className="bet-instructions">
                    {legs.map(leg => (
                      <div key={leg.outcome} className="bet-leg">
                        <span className="bet-book-name">{BOOK_DISPLAY[leg.book] || leg.book}</span>
                        <span className="bet-sep">→</span>
                        <span className="bet-selection">{leg.participant}</span>
                        <span className="bet-column-badge" title="Column name on sportsbook site">
                          {getColumnLabel(leg.book, opp.market)}
                        </span>
                        <span className="bet-amount">${leg.stake}</span>
                        <span className="bet-odds">@ {displayOdds(leg.book, leg.odds)}</span>
                        {leg.scraped_at && (
                          <span className="bet-scraped-at" title={`Odds fetched at ${leg.scraped_at}`}>
                            🕐 {timeAgo(leg.scraped_at)}
                          </span>
                        )}
                        <a
                          className="bet-open-link"
                          href={getBookUrl(leg.book, opp.sport)}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          title={`Open ${BOOK_DISPLAY[leg.book] || leg.book}`}
                        >Open ↗</a>
                      </div>
                    ))}
                    <div className="bet-profit-line">Guaranteed profit: +${profit}</div>
                  </div>
                </td>
                <td className="td-toggle">{isExp ? '▲' : '▼'}</td>
              </tr>

              {/* Expanded detail row */}
              {isExp && (
                <tr key={`${opp.id}-detail`} className="expanded-row">
                  <td colSpan={6}>
                    <StakeCalculator opportunity={opp} />
                  </td>
                </tr>
              )}
            </>
          )
        })}
      </tbody>
    </table>
  )
}
