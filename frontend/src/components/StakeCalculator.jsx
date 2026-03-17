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
          <strong>{leg.outcome}</strong>: {leg.book} @ {leg.decimal_odds} → <strong>${stakes[i]}</strong>
        </div>
      ))}
      <div className="stake-profit">Guaranteed profit: ${profit} ({(opportunity.margin * 100).toFixed(2)}%)</div>
    </div>
  )
}
