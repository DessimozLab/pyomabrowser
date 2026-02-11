import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],

  // Base path: always use /static/ to match django-vite's behavior
  // In dev mode, Vite dev server will serve from http://localhost:5173/static/
  // In production, files are in STATIC_ROOT and served at /static/vite/
  base: '/static/',

  build: {
    // Output directly to Django static directory (not dist/ subdirectory)
    outDir: resolve(__dirname, '../oma/static'),
    emptyOutDir: false,  // Don't delete other static files

    // Generate manifest for django-vite in vite/ subdirectory
    manifest: 'vite/manifest.json',

    rollupOptions: {
      input: {
        // Entry points for different pages
        searchToken: resolve(__dirname, 'src/entries/search-token.js'),
      },
      output: {
        // Predictable naming for Django static files
        entryFileNames: 'vite/js/[name].js',
        chunkFileNames: 'vite/js/[name]-[hash].js',
        assetFileNames: 'vite/assets/[name].[ext]'
      }
    }
  },

  // Dev server configuration
  server: {
    port: 5173,
    strictPort: true,
    host: '0.0.0.0',  // Listen on all interfaces for Docker
    // Allow Django dev server to proxy
    cors: true,
    origin: 'http://localhost:5173',
    hmr: {
      // HMR websocket needs to connect from browser to host
      host: 'localhost',
      port: 5173,
    }
  },

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    }
  }
})
