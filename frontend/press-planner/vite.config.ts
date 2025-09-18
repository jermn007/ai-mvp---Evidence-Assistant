import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import type { UserConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  // Performance optimizations
  build: {
    // Enable minification and tree shaking
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },

    // Chunk splitting for better caching
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          api: ['./src/services/apiClient.ts'],
        },
      },
    },

    // Target modern browsers for smaller bundles
    target: 'esnext',

    // Enable source maps for production debugging
    sourcemap: true,
  },

  // Development optimizations
  server: {
    // Enable HMR for faster development
    hmr: true,

    // CORS for API calls
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },

  // Dependency optimization
  optimizeDeps: {
    include: ['react', 'react-dom'],
    exclude: ['@vitejs/plugin-react'],
  },

  // Define global constants
  define: {
    __API_BASE_URL__: JSON.stringify(process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'),
    __DEV__: JSON.stringify(process.env.NODE_ENV === 'development'),
  },
} satisfies UserConfig)
