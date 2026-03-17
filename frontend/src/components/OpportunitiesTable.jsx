import { useState, useContext } from 'react'
import { BankrollContext } from '../App'
import StakeCalculator from './StakeCalculator'

const SPORT_EMOJI = { nhl: '🏒', nfl: '🏈', nba: '🏀', mlb: '⚾', mls: '⚽', soccer: '⚽' }

function calcLegs(bankroll, outcomes) {
  const implied = outcomes.map(o => 1 / o.decimal_odds)
  const arbSum = implied.reduce((a, b) => a + b, 0)
  return outcomes.map((o, i) => ({
    book: o.book,
    outcome: o.outcome,
    odds: o.decimal_odds,
    stake: (bankroll * implied[i] / arbSum).toFixed(2),
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
        <div className="empty-sub">Monitoring 6 Alberta sportsbooks every 45 seconds</div>
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
                  {/* Always-visible bet instructions with dollar amounts */}
                  <div className="bet-instructions">
                    {legs.map(leg => (
                      <div key={leg.outcome} className="bet-leg">
                        <span className="bet-book">{leg.book}</span>
                        <span className="bet-sep">·</span>
                        <span className="bet-outcome">{leg.outcome}</span>
                        <span className="bet-amount">${leg.stake}</span>
                        <span className="bet-odds">@ {leg.odds}</span>
                      </div>
                    ))}
                    <div className="bet-profit-line">→ guaranteed +${profit}</div>
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
