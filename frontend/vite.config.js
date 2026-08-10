import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

const apiTarget = process.env.VITE_API_TARGET || 'http://localhost:8000'

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
      '/app': {
        target: apiTarget,
        changeOrigin: true
      },
      '/auth': {
        target: apiTarget,
        changeOrigin: true
      },
      '/projects': {
        target: apiTarget,
        changeOrigin: true,
        bypass(req) {
          // The workspace page and the Projects API intentionally share the
          // /projects prefix. A direct browser refresh must stay in the SPA.
          if (
            req.method === 'GET' &&
            /^\/projects\/[^/]+\/tasks\/[^/?]+(?:\?.*)?$/.test(req.url || '')
          ) {
            return '/index.html'
          }
        }
      },
      '/resume-sources': {
        target: apiTarget,
        changeOrigin: true
      },
      '/tasks': {
        target: apiTarget,
        changeOrigin: true
      },
      '/settings': {
        target: apiTarget,
        changeOrigin: true
      },
      '/health': {
        target: apiTarget,
        changeOrigin: true
      },
      '/load_resume': {
        target: apiTarget,
        changeOrigin: true
      },
      '/save_resume': {
        target: apiTarget,
        changeOrigin: true
      },
      '/translate_resume': {
        target: apiTarget,
        changeOrigin: true
      },
      '/restore_resume_translation': {
        target: apiTarget,
        changeOrigin: true
      },
      '/load_jd': {
        target: apiTarget,
        changeOrigin: true
      },
      '/save_jd': {
        target: apiTarget,
        changeOrigin: true
      },
      '/load_conversation': {
        target: apiTarget,
        changeOrigin: true
      },
      '/save_conversation': {
        target: apiTarget,
        changeOrigin: true
      },
      '/chat': {
        target: apiTarget,
        changeOrigin: true
      },
      '/parse_jd': {
        target: apiTarget,
        changeOrigin: true
      },
      '/export_pdf': {
        target: apiTarget,
        changeOrigin: true
      },
      '/export_docx': {
        target: apiTarget,
        changeOrigin: true
      },
      '/confirm': {
        target: apiTarget,
        changeOrigin: true
      },
      '/api': {
        target: apiTarget,
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      }
    }
  }
})
