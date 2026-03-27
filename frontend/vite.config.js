import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,       // bind to 0.0.0.0 — accessible from phones on the same network
    proxy: {
      '/api': 'http://localhost:8001',
      '/ws':  { target: 'ws://localhost:8001', ws: true },
    },
  },
})
