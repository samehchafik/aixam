import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { mockApi } from './dev/mockApi'

// base './' : le meme bundle fonctionne servi sous /kiosk/ par FastAPI ET
// charge depuis le systeme de fichiers dans le shell Tauri.
export default defineConfig(({ mode }) => ({
  base: './',
  plugins: [react(), ...(mode === 'mock' ? [mockApi()] : [])],
  build: { outDir: 'dist', emptyOutDir: true },
  server: { port: 5173, strictPort: true },
}))
