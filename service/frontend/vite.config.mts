import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy target is configurable so the same config works natively (default) and
// inside Docker Compose (set VITE_PROXY_TARGET=http://backend:8001).
const apiTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8001'
const wsTarget = apiTarget.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3000,
    proxy: {
      '/api': apiTarget,
      '/ws': { target: wsTarget, ws: true }
    }
  }
})
