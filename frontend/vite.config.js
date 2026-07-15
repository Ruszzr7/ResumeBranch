import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    proxy: {
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/load_resume': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/save_resume': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/load_jd': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/save_jd': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/load_conversation': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/save_conversation': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/chat': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/parse_jd': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/export_pdf': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/confirm': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      }
    }
  }
})
