import { useState, createContext, useContext } from 'react'
import './App.css'

export const BankrollContext = createContext(100)

export default function App() {
  const [bankroll, setBankroll] = useState(100)
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
        </header>
        <main>
          <p>Loading...</p>
        </main>
      </div>
    </BankrollContext.Provider>
  )
}
