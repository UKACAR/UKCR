import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend FastAPI'ye proxy: frontend /api/... çağrılarını 8000'e yönlendirir.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
