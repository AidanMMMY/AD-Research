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
    // 生产不发 sourcemap：dist 里 .map 曾达 ~8.5MB（echarts 单文件 5.9MB），
    // 既翻倍部署体积又完整暴露源码（前端审计 2026-08-06）。本地调试不受影响。
    sourcemap: false,
    // 调回 500KB 让超大 chunk（echarts/ui ~1MB+）在 CI build 时暴露告警。
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // React ecosystem stays together to avoid internal singleton errors.
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router-dom')) {
            return 'vendor';
          }
          // Keep all Ant Design code (antd + icons + colors + helpers) in a
          // single chunk. Splitting icons into its own chunk creates a runtime
          // cyclic dependency: icons top-level init needs color helpers that
          // end up in the ui chunk, while ui chunk imports icons.
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
