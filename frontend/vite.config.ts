import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5173,
    // WSL 挂载目录收不到文件变更通知，改用轮询
    watch: { usePolling: true, interval: 400 },
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: { echarts: ['echarts', 'vue-echarts'], naive: ['naive-ui'], hljs: ['highlight.js'] },
      },
    },
  },
})
