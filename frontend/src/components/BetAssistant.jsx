import { useState, useEffect, useContext } from 'react'
import { BankrollContext } from '../App'

const BOOK_DISPLAY = {
  playalberta:      'PlayAlberta',
  bet365:           'Bet365',
  betway:           'Betway',
  sportsinteraction:'SportsInteraction',
}

const SPORT_EMOJI = {
  nhl: '🏒', nba: '🏀', mlb: '⚾', nfl: '🏈', soccer: '⚽',
}

// Sport-level fallback URLs — kept in sync with OpportunitiesTable.jsx BOOK_SPORT_URL
const BOOK_SPORT_URL = {
  playalberta: {
    // stg-XXXXX IDs confirmed via live browser inspection of playalberta.ca/sports
    nhl:    'https://playalberta.ca/sports/hockey/nhl/stg-19217',
    nba:    'https://playalberta.ca/sports/basketball/nba/stg-19658',
    mlb:    'https://playalberta.ca/sports/baseball/mlb/stg-20831',
    nfl:    'https://playalberta.ca/sports/football/nfl/stg-19218',
    soccer: 'https://playalberta.ca/sports/soccer/sp-1',
    default: 'https://playalberta.ca/sports',
  },
  bet365: {
    nhl:    'https://www.bet365.ca/en/sports/ice-hockey/nhl/',
    nba:    'https://www.bet365.ca/en/sports/basketball/',
    mlb:    'https://www.bet365.ca/en/sports/baseball/',
    nfl:    'https://www.bet365.ca/en/sports/american-football/',
    soccer: 'https://www.bet365.ca/en/sports/soccer/',
    default: 'https://www.bet365.ca',
  },
  betway: {
    nhl:    'https://betway.com/g/en-ca/sports/grp/ice-hockey/north-america/nhl',
    nba:    'https://betway.com/g/en-ca/sports/grp/basketball/usa/nba',
    mlb:    'https://betway.com/g/en-ca/sports/grp/baseball/usa/mlb',
    soccer: 'https://betway.com/g/en-ca/sports/cat/soccer/',
    default: 'https://betway.com/g/en-ca/sports',
  },
  sportsinteraction: {
    nhl:    'https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/',
    nba:    'https://www.sportsinteraction.com/en-ca/sports-betting/basketball/',
    mlb:    'https://www.sportsinteraction.com/en-ca/sports-betting/baseball/',
    nfl:    'https://www.sportsinteraction.com/en-ca/sports-betting/american-football/',
    soccer: 'https://www.sportsinteraction.com/en-ca/sports-betting/soccer/',
    default: 'https://www.sportsinteraction.com/en-ca/',
  },
  bet99: {
    nhl:    'https://bet99.com/sports/hockey',
    nba:    'https://bet99.com/sports/basketball',
    mlb:    'https://bet99.com/sports/baseball',
    soccer: 'https://bet99.com/sports/soccer',
    default: 'https://bet99.com/sports',
  },
}

function getEventUrl(leg, sport) {
  if (leg.event_url) return leg.event_url
  const bookUrls = BOOK_SPORT_URL[leg.book] || {}
  return bookUrls[sport] || bookUrls.default || '#'
}

function calcLegs(bankroll, outcomes) {
  const implied = outcomes.map(o => 1 / o.decimal_odds)
  const arbSum = implied.reduce((a, b) => a + b, 0)
  return outcomes.map((o, i) => ({
    ...o,
    odds: o.decimal_odds,
    stake: ((implied[i] / arbSum) * bankroll).toFixed(2),
  }))
}

function timeAgo(isoStr) {
  if (!isoStr) return null
  const secs = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

export default function BetAssistant({ opportunity, onClose }) {
  const bankroll = useContext(BankrollContext)
  const [confirmed, setConfirmed] = useState(new Set())

  // Reset checklist when a new opportunity is loaded
  useEffect(() => { setConfirmed(new Set()) }, [opportunity?.id])

  if (!opportunity) return null

  const legs = calcLegs(bankroll, opportunity.outcomes)
  const profit = (bankroll * opportunity.margin).toFixed(2)
  const allConfirmed = confirmed.size === legs.length

  // Stale odds warning: any leg older than 90 seconds
  const stale = legs.some(l => {
    if (!l.scraped_at) return false
    return (Date.now() - new Date(l.scraped_at).getTime()) / 1000 > 90
  })

  function toggleConfirm(key) {
    setConfirmed(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  return (
    <div className="bet-assistant">
      <div className="ba-header">
        <div className="ba-header-left">
          <span className="ba-title">Bet Assistant</span>
          <span className="ba-sport">{SPORT_EMOJI[opportunity.sport] || '🎯'} {opportunity.sport.toUpperCase()}</span>
        </div>
        <div className="ba-header-right">
          <span className="profit-badge ba-profit">+{(opportunity.margin * 100).toFixed(2)}%</span>
          <button className="ba-close" onClick={onClose} title="Close">✕</button>
        </div>
      </div>

      <div className="ba-event">
        <div className="ba-event-name">{opportunity.event_name}</div>
        <div className="ba-event-sub">{opportunity.market} · Guaranteed profit: <strong>${profit}</strong></div>
      </div>

      {stale && (
        <div className="ba-stale-warning">
          ⚠️ Odds may have moved — verify on each site before placing
        </div>
      )}

      <div className="ba-legs">
        {legs.map(leg => {
          const key = `${leg.book}:${leg.outcome}`
          const done = confirmed.has(key)
          const url = getEventUrl(leg, opportunity.sport)
          return (
            <div key={key} className={`ba-leg ${done ? 'ba-leg--done' : ''}`}>
              <label className="ba-leg-label">
                <input
                  type="checkbox"
                  checked={done}
                  onChange={() => toggleConfirm(key)}
                  className="ba-checkbox"
                />
                <div className="ba-leg-body">
                  <div className="ba-leg-top">
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ba-book-link"
                      onClick={e => e.stopPropagation()}
                    >
                      {BOOK_DISPLAY[leg.book] || leg.book} ↗
                    </a>
                    <span className="ba-leg-stake">${leg.stake}</span>
                  </div>
                  <div className="ba-leg-bottom">
                    <span className="ba-leg-selection">{leg.participant}</span>
                    <span className="ba-leg-odds">@ {leg.odds.toFixed(2)}</span>
                  </div>
                </div>
              </label>
              {leg.scraped_at && (
                <span className="ba-scraped-at">🕐 {timeAgo(leg.scraped_at)}</span>
              )}
            </div>
          )
        })}
      </div>

      <div className={`ba-footer ${allConfirmed ? 'ba-footer--done' : ''}`}>
        {allConfirmed ? (
          <span>✅ All bets placed — Profit locked in: <strong>+${profit}</strong></span>
        ) : (
          <span>{confirmed.size}/{legs.length} legs placed · <strong>+${profit}</strong> guaranteed</span>
        )}
      </div>
    </div>
  )
}
