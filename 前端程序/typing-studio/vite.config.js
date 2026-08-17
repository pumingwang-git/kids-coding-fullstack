import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// 打字星球 · 独立子应用
// 与 scratch-studio 同构的接入方式：独立构建、构建产物部署到 /typing-studio/，
// 主应用 study-blog-vue 通过 window.open('/typing-studio/?age=..&mode=..') 打开。
// base 用挂载路径的绝对形式（不是 './'）：dev 下主站通过 /typing-studio 代理进来，
// 相对 base 会让 index.html 里的模块请求打回主站 5173，页面白屏；绝对 base 让
// dev 与生产 nginx 走同一套路径。换挂载路径时改这一行。
export default defineConfig({
  base: '/typing-studio/',
  plugins: [vue()],
  server: {
    port: 8603,
    host: '127.0.0.1',
    // 同域联调：/api 代理到本地 FastAPI（默认 8000），与 scratch-studio 一致
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 900
  }
});
