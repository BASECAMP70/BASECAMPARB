import { useState, useContext, Fragment } from 'react'
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

// Sport-specific deep links for each book.
// Base paths confirmed from scraper ODDS_URLs; sport sub-paths derived from site structure.
const BOOK_SPORT_URL = {
  playalberta: {
    // stg-XXXXX IDs confirmed via live browser inspection of playalberta.ca/sports
    nhl:    'https://playalberta.ca/sports/hockey/nhl/stg-19217',
    nba:    'https://playalberta.ca/sports/basketball/nba/stg-19658',
    mlb:    'https://playalberta.ca/sports/baseball/mlb/stg-20831',
    nfl:    'https://playalberta.ca/sports/football/nfl/stg-19218',
    soccer: 'https://playalberta.ca/sports/soccer/sp-1',
    _default: 'https://playalberta.ca/sports',
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
    nfl:    'https://www.sportsinteraction.com/en-ca/sports-betting/american-football/',
    soccer: 'https://www.sportsinteraction.com/en-ca/sports-betting/soccer/',
    _default: 'https://www.sportsinteraction.com/en-ca/',
  },
  betmgm:  { _default: 'https://sports.betmgm.ca' },
  fanduel: { _default: 'https://www.fanduel.com/sports/alberta' },
  betway:  {
    nhl:    'https://betway.com/g/en-ca/sports/grp/ice-hockey/north-america/nhl',
    nba:    'https://betway.com/g/en-ca/sports/grp/basketball/usa/nba',
    mlb:    'https://betway.com/g/en-ca/sports/grp/baseball/usa/mlb',
    soccer: 'https://betway.com/g/en-ca/sports/cat/soccer/',
    _default: 'https://betway.com/g/en-ca/sports',
  },
  bet99:   {
    nhl:    'https://bet99.com/sports/hockey',
    nba:    'https://bet99.com/sports/basketball',
    mlb:    'https://bet99.com/sports/baseball',
    soccer: 'https://bet99.com/sports/soccer',
    _default: 'https://bet99.com/sports',
  },
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

// Spread label varies by sport — hockey=Puck Line, basketball=Point Spread, baseball=Run Line
function spreadLabel(sport) {
  if (sport === 'nba') return 'Point Spread'
  if (sport === 'mlb') return 'Run Line'
  return 'Puck Line'   // NHL default
}

// The exact column/field name each sportsbook uses on their site
// spread is sport-dependent so it receives the sport as a second arg
const BOOK_MARKET_COLUMN = {
  playalberta:       { moneyline: 'Money Line', totals: 'Total' },
  bet365:            { moneyline: 'Money Line', totals: 'Over/Under' },
  sportsinteraction: { moneyline: 'Money Line', totals: 'Total' },
  betmgm:            { moneyline: 'Moneyline',  totals: 'Total' },
  fanduel:           { moneyline: 'Moneyline',  totals: 'Total' },
  betway:            { moneyline: 'Moneyline',  totals: 'Over/Under' },
  bet99:             { moneyline: 'Money Line', totals: 'Total' },
}

function getColumnLabel(book, market, sport) {
  if (market === 'spread') return spreadLabel(sport)
  return (BOOK_MARKET_COLUMN[book] || {})[market] || MARKET_LABEL[market] || market
}

// All books display decimal odds
function displayOdds(book, decimal) {
  return decimal.toFixed(2)
}

// Format an ISO event_start as "Today 7:05 PM" or "Mar 22 7:05 PM"
function formatGameDate(isoStr) {
  if (!isoStr) return null
  const d = new Date(isoStr)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (isToday) return `Today ${time}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + time
}

// Format an ISO scraped_at timestamp as "Xs ago" / "Xm ago"
function timeAgo(isoStr) {
  if (!isoStr) return null
  const secs = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (secs < 60)  return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

// Format an ISO detected_at as "Today 3:22 PM" or "Mar 26 3:22 PM"
function formatDetectedAt(isoStr) {
  if (!isoStr) return null
  const d = new Date(isoStr)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (isToday) return `Today ${time}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + time
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

export default function OpportunitiesTable({ opps, newIds, onPlaceBets }) {
  const [expanded, setExpanded] = useState(new Set())
  const bankroll = useContext(BankrollContext)

  const sorted = Object.values(opps).sort((a, b) => {
    const aNew = newIds.has(a.id) ? 1 : 0
    const bNew = newIds.has(b.id) ? 1 : 0
    if (bNew !== aNew) return bNew - aNew
    return b.margin - a.margin
  })

  function handlePlaceBets(e, opp) {
    e.stopPropagation()
    // Open each book's event page in a new tab simultaneously
    opp.outcomes.forEach(leg => {
      const url = leg.event_url || getBookUrl(leg.book, opp.sport)
      window.open(url, '_blank', 'noopener')
    })
    if (onPlaceBets) onPlaceBets(opp)
  }

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
            <Fragment key={opp.id}>
              {/* Summary row */}
              <tr
                className={`opp-row ${isNew ? 'new-flash' : ''}`}
                onClick={() => toggleExpand(opp.id)}
              >
                <td className="td-sport">{SPORT_EMOJI[opp.sport] || '🎯'} {opp.sport.toUpperCase()}</td>
                <td className="td-event">
                  <div>{opp.event_name}</div>
                  {opp.event_start && (
                    <div className="game-date">{formatGameDate(opp.event_start)}</div>
                  )}
                </td>
                <td className="td-market">{opp.market}</td>
                <td className="td-profit">
                  <span className="profit-badge">+{(opp.margin * 100).toFixed(2)}%</span>
                  {opp.detected_at && (
                    <div className="detected-at">🕵️ {formatDetectedAt(opp.detected_at)}</div>
                  )}
                </td>
                <td className="td-bets">
                  <div className="bet-instructions">
                    {legs.map(leg => (
                      <div key={leg.outcome} className="bet-leg">
                        <span className="bet-book-name">{BOOK_DISPLAY[leg.book] || leg.book}</span>
                        <span className="bet-sep">→</span>
                        <span className="bet-selection">{leg.participant}</span>
                        <span className="bet-column-badge" title="Column name on sportsbook site">
                          {getColumnLabel(leg.book, opp.market, opp.sport)}
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
                <td className="td-action">
                  <button
                    className="place-bets-btn"
                    onClick={e => handlePlaceBets(e, opp)}
                    title="Open each book to the game page and launch Bet Assistant"
                  >
                    Place Bets
                  </button>
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
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}
