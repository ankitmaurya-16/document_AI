import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // Split the vendor bundle so the React runtime is cached across deploys
    // and big deps (Prism, react-markdown) only ship on routes that use them.
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (!id.includes('node_modules')) return
          if (id.includes('react-router')) return 'router'
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) {
            return 'react'
          }
          // prismjs is dynamic-imported in Message; keep it in its own chunk.
          if (id.includes('prismjs')) return 'prism'
          if (id.includes('moment')) return 'moment'
        },
      },
    },
    // Raise the default 500-KB "chunk too big" warning so the vendor chunk
    // (which we intentionally keep together) doesn't noise up the build log.
    chunkSizeWarningLimit: 800,
  },
})
