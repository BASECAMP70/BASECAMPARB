import { useState, useEffect, useCallback } from 'react'
import { fetchBooks } from '../api'

// Sportsbooks and prediction markets we actively monitor
// `key` must match the BOOK_NAME used by the backend scraper
const ALBERTA_BOOKS = [
  { key: 'playalberta',        name: 'PlayAlberta',        url: 'https://www.playalberta.ca' },
  { key: 'bet365',             name: 'Bet365',             url: 'https://www.bet365.ca' },
  { key: 'sportsinteraction',  name: 'Sports Interaction', url: 'https://www.sportsinteraction.com' },
  { key: 'betway',             name: 'Betway',             url: 'https://betway.com/g/en-ca/sports' },
  { key: 'bet99',              name: 'Bet99',              url: 'https://bet99.com/sports/hockey' },
  { key: 'polymarket',         name: 'Polymarket',         url: 'https://polymarket.com/sports' },
  { key: 'myriad',             name: 'Myriad',             url: 'https://myriad.markets/markets?topic=Sports' },
]

function timeSince(iso) {
  if (!iso) return null
  const secs = Math.round((Date.now() - new Date(iso)) / 1000)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  return `${Math.floor(secs / 3600)}h ago`
}

export default function BookStatusBar({ wsMessage }) {
  const [books, setBooks] = useState({})
  const [enabled, setEnabled] = useState({})

  // Initial load
  useEffect(() => {
    fetchBooks()
      .then(data => {
        const map = {}
        for (const b of data.books) map[b.name] = b
        setBooks(map)
      })
      .catch(() => {})
    fetch('/api/scraper/books')
      .then(r => r.json())
      .then(data => {
        const map = {}
        for (const b of data.books) map[b.name] = b.enabled
        setEnabled(map)
      })
      .catch(() => {})
  }, [])

  // Live updates from WS
  useEffect(() => {
    if (!wsMessage) return
    if (wsMessage.type === 'odds_updated') {
      const msg = wsMessage
      setBooks(prev => ({
        ...prev,
        [msg.book]: {
          name: msg.book,
          status: msg.status,
          last_scraped_at: msg.scraped_at,
          record_count: msg.record_count,
          last_error: null,
        },
      }))
    }
    if (wsMessage.type === 'scraper_book_state') {
      setEnabled(prev => ({ ...prev, [wsMessage.book]: wsMessage.enabled }))
    }
  }, [wsMessage])

  const toggleBook = useCallback(async (key, currentlyEnabled, e) => {
    e.preventDefault()
    e.stopPropagation()
    const endpoint = currentlyEnabled ? `/api/scraper/${key}/disable` : `/api/scraper/${key}/enable`
    setEnabled(prev => ({ ...prev, [key]: !currentlyEnabled }))
    try {
      await fetch(endpoint, { method: 'POST' })
    } catch {
      setEnabled(prev => ({ ...prev, [key]: currentlyEnabled }))
    }
  }, [])

  const enabledCount = ALBERTA_BOOKS.filter(b => enabled[b.key] !== false).length

  return (
    <section className="book-section">
      <div className="book-section-header">
        <span className="book-section-title">Alberta Sportsbooks</span>
        <span className="book-section-sub">{enabledCount} of {ALBERTA_BOOKS.length} enabled · click to open</span>
      </div>
      <div className="book-grid">
        {ALBERTA_BOOKS.map(({ key, name, url }) => {
          const data = books[key]
          const isEnabled = enabled[key] !== false
          const status = !isEnabled ? 'disabled' : (data?.status ?? 'idle')
          const ago = timeSince(data?.last_scraped_at)
          const count = data?.record_count ?? 0
          const err = data?.last_error

          return (
            <a
              key={name}
              href={url}
              target="_blank"
              rel="noreferrer"
              className={`book-card book-card--${status}`}
              title={err || `Open ${name}`}
            >
              <div className="book-card-dot" />
              <div className="book-card-body">
                <div className="book-card-name">{name}</div>
                <div className="book-card-meta">
                  {!isEnabled
                    ? 'Disabled'
                    : status === 'ok'
                    ? `${count} odds${ago ? ` · ${ago}` : ''}`
                    : status === 'error'
                    ? `Error${err ? ': ' + err.slice(0, 28) : ''}`
                    : 'Awaiting data'}
                </div>
              </div>
              <button
                className={`book-toggle-btn ${isEnabled ? 'book-toggle-btn--on' : 'book-toggle-btn--off'}`}
                onClick={e => toggleBook(key, isEnabled, e)}
                title={isEnabled ? 'Disable scraper' : 'Enable scraper'}
              >
                {isEnabled ? 'ON' : 'OFF'}
              </button>
            </a>
          )
        })}
      </div>
    </section>
  )
}
