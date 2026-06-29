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
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // React ecosystem stays together to avoid internal singleton errors.
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) {
            return 'vendor';
          }
          // Ant Design icons are huge; keep them separate from antd components.
          if (id.includes('node_modules/@ant-design/icons')) {
            return 'icons';
          }
          if (id.includes('node_modules/antd') || id.includes('node_modules/@ant-design')) {
            return 'ui';
          }
          // Split charting libraries so a page without charts doesn't pull them.
          if (id.includes('node_modules/echarts') || id.includes('node_modules/echarts-for-react')) {
            return 'echarts';
          }
          if (id.includes('node_modules/lightweight-charts')) {
            return 'lightweight-charts';
          }
          if (id.includes('node_modules/@tanstack') || id.includes('node_modules/axios') || id.includes('node_modules/zustand') || id.includes('node_modules/dayjs')) {
            return 'data';
          }
        },
      },
    },
  },
});
