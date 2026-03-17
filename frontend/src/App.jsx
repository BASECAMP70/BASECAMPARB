import { useState, createContext, useEffect, useRef, useCallback } from 'react'
import './App.css'
import BookStatusBar from './components/BookStatusBar'
import OpportunitiesTable from './components/OpportunitiesTable'
import AlertSound from './components/AlertSound'
import { useWebSocket } from './hooks/useWebSocket'
import { useOpportunities } from './hooks/useOpportunities'

export const BankrollContext = createContext(100)

const API = 'http://localhost:8000'

const WS_STATUS_CONFIG = {
  connected:    { dot: '●', label: 'Live',           cls: 'ws-live' },
  connecting:   { dot: '●', label: 'Connecting…',    cls: 'ws-connecting' },
  reconnecting: { dot: '●', label: 'Reconnecting…',  cls: 'ws-reconnecting' },
}

export default function App() {
  const [bankroll, setBankroll] = useState(100)
  const [lastWsMessage, setLastWsMessage] = useState(null)
  const [lastCycleAt, setLastCycleAt] = useState(null)
  const [elapsed, setElapsed] = useState(null)
  const [scraperRunning, setScraperRunning] = useState(true)
  const [scraperBusy, setScraperBusy] = useState(false)
  const soundRef = useRef(null)

  const { opps, newIds, loadInitial, handleMessage } = useOpportunities()

  const handleMessageWithSound = useCallback((msg) => {
    if (msg.type === 'new_opportunity') soundRef.current?.playChime()
    if (msg.type === 'scrape_cycle_complete') setLastCycleAt(Date.now())
    if (msg.type === 'scraper_state') setScraperRunning(msg.running)
    setLastWsMessage(msg)
    handleMessage(msg)
  }, [handleMessage])

  const { status: wsStatus } = useWebSocket(handleMessageWithSound)

  useEffect(() => { loadInitial() }, [loadInitial])

  // Fetch initial scraper state on mount
  useEffect(() => {
    fetch(`${API}/api/scraper/status`)
      .then(r => r.json())
      .then(d => setScraperRunning(d.running))
      .catch(() => {})
  }, [])

  // Tick elapsed seconds since last scrape cycle
  useEffect(() => {
    if (!lastCycleAt) return
    setElapsed(0)
    const id = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [lastCycleAt])

  const toggleScraper = useCallback(async () => {
    setScraperBusy(true)
    try {
      const endpoint = scraperRunning ? '/api/scraper/stop' : '/api/scraper/start'
      const res = await fetch(`${API}${endpoint}`, { method: 'POST' })
      const data = await res.json()
      setScraperRunning(data.running)
    } catch (e) {
      console.error('scraper toggle failed', e)
    } finally {
      setScraperBusy(false)
    }
  }, [scraperRunning])

  const { dot, label, cls } = WS_STATUS_CONFIG[wsStatus] ?? WS_STATUS_CONFIG.connecting

  return (
    <BankrollContext.Provider value={bankroll}>
      <div className="app">
        <header className="app-header">
          <div className="header-left">
            <h1>ARB FINDER — Alberta</h1>
            <div className={`ws-status ${cls}`}>
              <span className="ws-dot">{dot}</span>
              <span className="ws-label">{label}</span>
              {wsStatus === 'connected' && elapsed !== null && (
                <span className="ws-updated">
                  · {elapsed < 3 ? 'just updated' : `updated ${elapsed}s ago`}
                </span>
              )}
            </div>
          </div>
          <div className="header-right">
            <button
              className={`scraper-btn ${scraperRunning ? 'scraper-btn--running' : 'scraper-btn--stopped'}`}
              onClick={toggleScraper}
              disabled={scraperBusy}
              title={scraperRunning ? 'Stop scraping' : 'Start scraping'}
            >
              {scraperBusy
                ? '…'
                : scraperRunning
                  ? '⏸ Stop'
                  : '▶ Start'}
            </button>
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
          </div>
        </header>
        <BookStatusBar wsMessage={lastWsMessage} />
        <OpportunitiesTable opps={opps} newIds={newIds} />
      </div>
    </BankrollContext.Provider>
  )
}
