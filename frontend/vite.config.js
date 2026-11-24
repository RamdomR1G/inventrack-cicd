import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const devProxy = {
  '/api': process.env.API_URL || 'http://localhost:8000',
  '/otlp': { target: process.env.OTLP_URL || 'http://localhost:4318', rewrite: (p) => p.replace(/^\/otlp/, '') },
}

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: devProxy },
  preview: { port: 4173, proxy: devProxy },
})
