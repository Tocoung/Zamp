import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'lucide-react': 'lucide-react/dist/cjs/lucide-react.js',
    },
  },
  optimizeDeps: {
    include: ['lucide-react', 'react', 'react-dom'],
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
  },
  preview: {
    port: 5173,
    host: '0.0.0.0',
  },
});
