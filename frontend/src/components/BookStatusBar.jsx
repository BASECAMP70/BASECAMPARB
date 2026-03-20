import { useState, useEffect } from 'react'
import { fetchBooks } from '../api'

// Alberta-licensed sportsbooks we actively monitor
// `key` must match the BOOK_NAME used by the backend scraper
const ALBERTA_BOOKS = [
  { key: 'playalberta',        name: 'PlayAlberta',        url: 'https://www.playalberta.ca' },
  { key: 'bet365',             name: 'Bet365',             url: 'https://www.bet365.ca' },
  { key: 'sportsinteraction',  name: 'Sports Interaction', url: 'https://www.sportsinteraction.com' },
  { key: 'betway',             name: 'Betway',             url: 'https://betway.com/g/en-ca/sports' },
  { key: 'bet99',              name: 'Bet99',              url: 'https://bet99.com/sports/hockey' },
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

  // Initial load from REST
  useEffect(() => {
    fetchBooks()
      .then(data => {
        const map = {}
        for (const b of data.books) map[b.name] = b
        setBooks(map)
      })
      .catch(() => {})
  }, [])

  // Live updates from WS (passed down from App to avoid a second connection)
  useEffect(() => {
    if (!wsMessage || wsMessage.type !== 'odds_updated') return
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
  }, [wsMessage])

  return (
    <section className="book-section">
      <div className="book-section-header">
        <span className="book-section-title">Alberta Sportsbooks</span>
        <span className="book-section-sub">5 licensed sites monitored · click to open</span>
      </div>
      <div className="book-grid">
        {ALBERTA_BOOKS.map(({ key, name, url }) => {
          const data = books[key]
          const status = data?.status ?? 'idle'
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
                  {status === 'ok'
                    ? `${count} odds${ago ? ` · ${ago}` : ''}`
                    : status === 'error'
                    ? `Error${err ? ': ' + err.slice(0, 28) : ''}`
                    : 'Awaiting data'}
                </div>
              </div>
            </a>
          )
        })}
      </div>
    </section>
  )
}
