import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  build: {
    rolldownOptions: {
      input: {
        main: path.resolve(import.meta.dirname, 'index.html'),
        report: path.resolve(import.meta.dirname, 'report-preview.html'),
      },
    },
  },
  server: {
    // 前端同源转发到本地后端（start.ps1 同时拉起 127.0.0.1:8000）
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
