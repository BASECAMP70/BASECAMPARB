import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = 'ws://localhost:8000/ws'
const BACKOFF = [1000, 2000, 4000, 8000, 30000]

export function useWebSocket(onMessage) {
  const [status, setStatus] = useState('connecting')
  const wsRef = useRef(null)
  const attemptRef = useRef(0)
  const mountedRef = useRef(true)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return ws.close()
      attemptRef.current = 0
      setStatus('connected')
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        onMessageRef.current(msg)
      } catch (err) {
        console.error('WS parse error', err)
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setStatus('reconnecting')
      const delay = BACKOFF[Math.min(attemptRef.current, BACKOFF.length - 1)]
      attemptRef.current += 1
      setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      wsRef.current?.close()
    }
  }, [connect])

  return { status }
}
