import { useState } from 'react'
import StakeCalculator from './StakeCalculator'

const SPORT_EMOJI = { nhl: '🏒', nfl: '🏈', nba: '🏀', mlb: '⚾', mls: '⚽', soccer: '⚽' }

export default function OpportunitiesTable({ opps, newIds }) {
  const [expanded, setExpanded] = useState(new Set())

  const sorted = Object.values(opps).sort((a, b) => {
    // Pin new items first for 10s (tracked by newIds), then sort by margin
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
    return <p style={{ padding: '40px 20px', color: '#64748b' }}>No arbitrage opportunities detected.</p>
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Sport</th>
          <th>Event</th>
          <th>Market</th>
          <th>Profit</th>
          <th>Books</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(opp => {
          const isExp = expanded.has(opp.id)
          const isNew = newIds.has(opp.id)
          const books = [...new Set(opp.outcomes.map(o => o.book))].join(', ')
          return (
            <>
              <tr
                key={opp.id}
                className={`expandable ${isNew ? 'new-flash' : ''}`}
                onClick={() => toggleExpand(opp.id)}
              >
                <td>{SPORT_EMOJI[opp.sport] || '🎯'} {opp.sport.toUpperCase()}</td>
                <td>{opp.event_name}</td>
                <td>{opp.market}</td>
                <td><span className="profit-badge">+{(opp.margin * 100).toFixed(2)}%</span></td>
                <td>{books} {isExp ? '▲' : '▼'}</td>
              </tr>
              {isExp && (
                <tr key={`${opp.id}-detail`} className="expanded-row">
                  <td colSpan={5}>
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
