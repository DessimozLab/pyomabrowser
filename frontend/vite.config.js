import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  
  // Base path for production (Django static files)
  base: '/static/',
  
  build: {
    // Output to Django static directory
    outDir: resolve(__dirname, '../oma/static/dist'),
    emptyOutDir: true,
    
    // Generate manifest for django-vite
    manifest: 'manifest.json',
    
    rollupOptions: {
      input: {
        // Entry points for different pages
        searchToken: resolve(__dirname, 'src/entries/search-token.js'),
      },
      output: {
        // Predictable naming for Django static files
        entryFileNames: 'js/[name].js',
        chunkFileNames: 'js/[name]-[hash].js',
        assetFileNames: 'assets/[name].[ext]'
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
