import { useContext } from 'react'
import { BankrollContext } from '../App'

function calculateStakes(bankroll, legs) {
  const implied = legs.map(l => 1 / l.decimal_odds)
  const arbSum = implied.reduce((a, b) => a + b, 0)
  return implied.map(imp => (bankroll * imp / arbSum).toFixed(2))
}

export default function StakeCalculator({ opportunity }) {
  const bankroll = useContext(BankrollContext)
  const stakes = calculateStakes(bankroll, opportunity.outcomes)
  const profit = (bankroll * opportunity.margin).toFixed(2)

  return (
    <div className="stake-calc">
      {opportunity.outcomes.map((leg, i) => (
        <div key={leg.outcome} className="stake-row">
          <span className="stake-book">{leg.book}</span>
          <span className="stake-arrow">→</span>
          <span className="stake-selection">{leg.participant || leg.outcome}</span>
          <span className="stake-meta">@ {leg.decimal_odds} · stake <strong>${stakes[i]}</strong></span>
        </div>
      ))}
      <div className="stake-profit">Guaranteed profit: ${profit} ({(opportunity.margin * 100).toFixed(2)}%)</div>
    </div>
  )
}
