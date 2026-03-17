import { useState, createContext, useEffect, useRef } from 'react'
import './App.css'
import BookStatusBar from './components/BookStatusBar'
import OpportunitiesTable from './components/OpportunitiesTable'
import AlertSound from './components/AlertSound'
import { useWebSocket } from './hooks/useWebSocket'
import { useOpportunities } from './hooks/useOpportunities'

export const BankrollContext = createContext(100)

export default function App() {
  const [bankroll, setBankroll] = useState(100)
  const soundRef = useRef(null)

  const { opps, newIds, loadInitial, handleMessage } = useOpportunities()

  // Wrap handleMessage to also trigger sound on new opportunity
  const handleMessageWithSound = (msg) => {
    if (msg.type === 'new_opportunity') {
      soundRef.current?.playChime()
    }
    handleMessage(msg)
  }

  useWebSocket(handleMessageWithSound)

  useEffect(() => { loadInitial() }, [loadInitial])

  return (
    <BankrollContext.Provider value={bankroll}>
      <div className="app">
        <header className="app-header">
          <h1>ARB FINDER — Alberta</h1>
          <label className="bankroll-label">
            Bankroll: $
            <input
              type="number"
              value={bankroll}
              min={1}
              onChange={e => setBankroll(Number(e.target.value))}
              className="bankroll-input"
            />
          </label>
          <AlertSound ref={soundRef} />
        </header>
        <BookStatusBar />
        <OpportunitiesTable opps={opps} newIds={newIds} />
      </div>
    </BankrollContext.Provider>
  )
}
