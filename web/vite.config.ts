import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Keep all React internals in a single chunk to avoid
          // "__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED" errors.
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) {
            return 'vendor';
          }
          if (id.includes('node_modules/echarts') || id.includes('node_modules/echarts-for-react') || id.includes('node_modules/lightweight-charts')) {
            return 'charts';
          }
          if (id.includes('node_modules/antd') || id.includes('node_modules/@ant-design')) {
            return 'ui';
          }
          if (id.includes('node_modules/@tanstack') || id.includes('node_modules/axios') || id.includes('node_modules/zustand') || id.includes('node_modules/dayjs')) {
            return 'data';
          }
        },
      },
    },
  },
});
