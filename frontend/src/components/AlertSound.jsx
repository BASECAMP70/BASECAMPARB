import { useState, useCallback, useImperativeHandle, forwardRef } from 'react'

const AlertSound = forwardRef(function AlertSound(_, ref) {
  const [enabled, setEnabled] = useState(true)

  const playChime = useCallback(() => {
    if (!enabled) return
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.type = 'triangle'
      osc.frequency.setValueAtTime(880, ctx.currentTime)
      gain.gain.setValueAtTime(0.3, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1)
      osc.start(ctx.currentTime)
      osc.stop(ctx.currentTime + 0.1)
    } catch (e) {
      console.warn('Audio failed', e)
    }
  }, [enabled])

  useImperativeHandle(ref, () => ({ playChime }))

  return (
    <button
      className="sound-toggle"
      onClick={() => setEnabled(e => !e)}
      title={enabled ? 'Mute alerts' : 'Unmute alerts'}
    >
      {enabled ? '🔔' : '🔕'}
    </button>
  )
})

export default AlertSound
