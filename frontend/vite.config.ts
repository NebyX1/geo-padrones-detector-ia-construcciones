import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {rollupOptions:{output:{manualChunks(id){if(id.includes('/node_modules/')){if(id.includes('/zod/'))return 'validation';if(id.includes('/framer-motion/')||id.includes('/motion-'))return 'motion';if(id.includes('/leaflet/')||id.includes('/react-leaflet/')||id.includes('/@react-leaflet/'))return 'cartography'}}}}},
  server: { proxy: { '/api': { target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8787', changeOrigin: false } } },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'], include: ['src/**/*.test.{ts,tsx}'] },
})
