import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Python API (src/api_server.py) serves the portal adapter on 8765.
// Proxying keeps the browser on one origin so there is no CORS layer to
// reason about in a prototype.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
})
