import { useState, useCallback, useRef } from 'react'
import { fetchOpportunities } from '../api'

export function useOpportunities() {
  // Map of id → opportunity, plus a Set of "new" ids for flash animation
  const [opps, setOpps] = useState({})
  const [newIds, setNewIds] = useState(new Set())
  const newIdTimers = useRef({})

  const loadInitial = useCallback(async () => {
    try {
      const data = await fetchOpportunities()
      const map = {}
      for (const o of data.opportunities) map[o.id] = o
      setOpps(map)
    } catch (e) {
      console.error('Failed to load opportunities', e)
    }
  }, [])

  const handleMessage = useCallback((msg) => {
    if (msg.type === 'new_opportunity') {
      setOpps(prev => ({ ...prev, [msg.data.id]: msg.data }))
      setNewIds(prev => new Set([...prev, msg.data.id]))
      // Remove from newIds after 10s
      if (newIdTimers.current[msg.data.id]) clearTimeout(newIdTimers.current[msg.data.id])
      newIdTimers.current[msg.data.id] = setTimeout(() => {
        setNewIds(prev => { const s = new Set(prev); s.delete(msg.data.id); return s })
      }, 10000)
    } else if (msg.type === 'opportunity_updated') {
      setOpps(prev => ({ ...prev, [msg.data.id]: msg.data }))
    } else if (msg.type === 'opportunity_expired') {
      setOpps(prev => {
        const next = { ...prev }
        delete next[msg.id]
        return next
      })
    }
  }, [])

  return { opps, newIds, loadInitial, handleMessage }
}
