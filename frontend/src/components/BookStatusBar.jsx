import { useState, useEffect, useCallback } from 'react'
import { fetchBooks } from '../api'
import { useWebSocket } from '../hooks/useWebSocket'

export default function BookStatusBar() {
  const [books, setBooks] = useState({})

  useEffect(() => {
    fetchBooks()
      .then(data => {
        const map = {}
        for (const b of data.books) map[b.name] = b
        setBooks(map)
      })
      .catch(console.error)
  }, [])

  const handleMessage = useCallback((msg) => {
    if (msg.type === 'odds_updated') {
      setBooks(prev => ({
        ...prev,
        [msg.book]: {
          name: msg.book,
          status: msg.status,
          last_scraped_at: msg.scraped_at,
          record_count: msg.record_count,
          last_error: null,
        }
      }))
    }
  }, [])

  useWebSocket(handleMessage)

  function timeSince(iso) {
    if (!iso) return '?'
    const secs = Math.round((Date.now() - new Date(iso)) / 1000)
    return secs < 60 ? `${secs}s` : `${Math.round(secs / 60)}m`
  }

  return (
    <div className="book-status-bar">
      {Object.values(books).map(b => (
        <span key={b.name} className={`book-badge ${b.status}`} title={b.last_error || ''}>
          {b.name} {b.status === 'ok' ? `✓ ${timeSince(b.last_scraped_at)}` : '✗'}
        </span>
      ))}
    </div>
  )
}
