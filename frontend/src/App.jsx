import { useState, createContext, useEffect, useRef, useCallback } from 'react'
import './App.css'
import BookStatusBar from './components/BookStatusBar'
import OpportunitiesTable from './components/OpportunitiesTable'
import BetAssistant from './components/BetAssistant'
import AlertSound from './components/AlertSound'
import { useWebSocket } from './hooks/useWebSocket'
import { useOpportunities } from './hooks/useOpportunities'

export const BankrollContext = createContext(100)

const API = ''  // relative — proxied by Vite in dev, same origin in prod

const WS_STATUS_CONFIG = {
  connected:    { dot: '●', label: 'Live',           cls: 'ws-live' },
  connecting:   { dot: '●', label: 'Connecting…',    cls: 'ws-connecting' },
  reconnecting: { dot: '●', label: 'Reconnecting…',  cls: 'ws-reconnecting' },
}

export default function App() {
  const [bankroll, setBankroll] = useState(100)
  const [activeBettingOpp, setActiveBettingOpp] = useState(null)
  const [lastWsMessage, setLastWsMessage] = useState(null)
  const [lastCycleAt, setLastCycleAt] = useState(null)
  const [elapsed, setElapsed] = useState(null)
  const [scraperRunning, setScraperRunning] = useState(true)
  const [scraperBusy, setScraperBusy] = useState(false)
  const [emailPaused, setEmailPaused] = useState(true)
  const [emailBusy, setEmailBusy] = useState(false)
  const soundRef = useRef(null)

  const { opps, newIds, loadInitial, handleMessage } = useOpportunities()

  const handleMessageWithSound = useCallback((msg) => {
    if (msg.type === 'new_opportunity') soundRef.current?.playChime()
    if (msg.type === 'scrape_cycle_complete') setLastCycleAt(Date.now())
    if (msg.type === 'scraper_state') setScraperRunning(msg.running)
    if (msg.type === 'email_state') setEmailPaused(msg.paused)
    setLastWsMessage(msg)
    handleMessage(msg)
  }, [handleMessage])

  const { status: wsStatus } = useWebSocket(handleMessageWithSound)

  useEffect(() => { loadInitial() }, [loadInitial])

  // Fetch initial scraper + email state on mount
  useEffect(() => {
    fetch(`${API}/api/scraper/status`)
      .then(r => r.json())
      .then(d => setScraperRunning(d.running))
      .catch(() => {})
    fetch(`${API}/api/email/status`)
      .then(r => r.json())
      .then(d => setEmailPaused(d.paused))
      .catch(() => {})
  }, [])

  // Tick elapsed seconds since last scrape cycle
  useEffect(() => {
    if (!lastCycleAt) return
    setElapsed(0)
    const id = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [lastCycleAt])

  const toggleEmail = useCallback(async () => {
    setEmailBusy(true)
    try {
      const endpoint = emailPaused ? '/api/email/resume' : '/api/email/pause'
      const res = await fetch(`${API}${endpoint}`, { method: 'POST' })
      const data = await res.json()
      setEmailPaused(data.paused)
    } catch (e) {
      console.error('email toggle failed', e)
    } finally {
      setEmailBusy(false)
    }
  }, [emailPaused])

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
            <img src="/logo.svg" alt="Arbiter logo" style={{height:'32px',marginRight:'10px',verticalAlign:'middle'}} />
            <h1>Arbiter <span style={{fontSize:'0.55em',fontWeight:400,color:'#64748b',letterSpacing:'0.05em'}}>v1.0.0</span></h1>
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
              {scraperBusy ? '…' : scraperRunning ? '⏸ Stop' : '▶ Start'}
            </button>
            <button
              className={`email-btn ${emailPaused ? 'email-btn--paused' : 'email-btn--active'}`}
              onClick={toggleEmail}
              disabled={emailBusy}
              title={emailPaused ? 'Resume email alerts' : 'Pause email alerts'}
            >
              {emailBusy ? '…' : emailPaused ? '✉ Alerts Off' : '✉ Alerts On'}
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
        <OpportunitiesTable opps={opps} newIds={newIds} onPlaceBets={setActiveBettingOpp} />
        <BetAssistant opportunity={activeBettingOpp} onClose={() => setActiveBettingOpp(null)} />
      </div>
    </BankrollContext.Provider>
  )
}
