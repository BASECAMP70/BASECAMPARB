import { useEffect, useRef, useCallback } from 'react'

const WS_URL = 'ws://localhost:8000/ws'

export function useWebSocket(onMessage) {
  const wsRef = useRef(null)
  const retryDelay = useRef(1000)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        onMessageRef.current(msg)
      } catch (err) {
        console.error('WS parse error', err)
      }
    }

    ws.onopen = () => {
      retryDelay.current = 1000  // reset backoff
    }

    ws.onclose = () => {
      const delay = retryDelay.current
      retryDelay.current = Math.min(delay * 2, 30000)
      setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()  // triggers onclose → reconnect
  }, [])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])
}
