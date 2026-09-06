import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8002", ws: true },
      // 题干配图。URL 是站点相对路径（/media/{sha[:2]}/{sha}.ext），没有 base_url 可配——
      // 开发期由后端的 StaticFiles 发（ENVIRONMENT != production 才挂），生产由 nginx 直发。
      // 少了这一条，后台预览和学员端的题图在 dev 下全是 404。
      "/media": "http://127.0.0.1:8001",
      // 学生头像。与题干配图同因：URL 是站点相对路径（/avatars/{sha[:2]}/{sha}.ext），
      // dev 必须代理到后端，否则 SPA fallback 会把 index.html 当头像返回，
      // <img> 解不出图——上传流程在 dev 下看着就像坏的。
      "/avatars": "http://127.0.0.1:8001",
      // 视频播放流 /v/{token}/{videoId}/...。同样是站点相对路径（master.m3u8 内就是
      // 相对引用，播放器会按 /v/ 拼 URL）——dev 必须代理到后端，否则 SPA fallback
      // 会把 index.html 当 m3u8 返回，Video.js 一直转圈不播放。
      "/v": "http://127.0.0.1:8001",
      // Scratch 工作台。它是独立的 webpack 子应用（dev 跑在 8602，生产由 nginx 挂在
      // 同源 /scratch-studio/）。少了这一条，学员端「打开编程工作台」会被 SPA 的
      // history fallback 接走：Vite 返回 index.html → 路由匹配不到 /scratch-studio/
      // → 撞上 router/index.js 末尾的 `{path: "/:pathMatch(.*)*", redirect: "/"}`
      // → **直接跳回首页**，看起来像链接坏了，其实是被自家兜底路由吃掉了。
      //
      // 前缀要剥掉：Studio 的 dev server 服务在自己的根路径上。资源能对得上是因为
      // webpack 那边 `publicPath: 'auto'`——脚本按自己的实际位置解析 chunks/static，
      // 挂在子路径下也不会去根目录找。
      "/scratch-studio": {
        target: "http://127.0.0.1:8602",
        rewrite: (p) => p.replace(/^\/scratch-studio/, "") || "/",
        ws: true,
      },
      // 打字两个子应用，同一个坑：少了代理，工具箱里的「字母乐园」「打字星球」会被
      // history fallback 接走 → 兜底路由 redirect: "/" → **跳回首页**。
      //
      // 与 scratch 那条的区别：这两个是 Vite 子应用，**不能 rewrite 掉前缀**。
      // webpack 的 publicPath:'auto' 会按脚本实际位置找 chunk，Vite 不会——它按
      // 配置里的 base 生成绝对资源路径。所以两边各自把 base 设成自己的挂载路径
      // （见各自 vite.config），这里原样透传，dev 与生产 nginx 的路径就一致了。
      //
      // 顺序无关：`(?!-qwerty)` 负向断言挡住 `^/typing-studio` 抢走 qwerty 的请求。
      "^/typing-studio-qwerty": {
        target: "http://127.0.0.1:8605",
        ws: true,
      },
      "^/typing-studio(?!-qwerty)": {
        target: "http://127.0.0.1:8603",
        ws: true,
      },
      // 数学星球独立应用（Vite，dev 跑 8604）。base 固定为 /math-studio/，
      // 因此这里保留前缀，与生产 nginx 的挂载路径一致。
      "^/math-studio": {
        target: "http://127.0.0.1:8604",
        ws: true,
      },
      // 专注星球（Nuxt 子应用，dev 跑 8610）：baseURL='/focus-studio/' 生成绝对路径，
      // 原样透传不能 rewrite（与 typing 两条同因）。少了它，工具箱里的「专注星球」
      // 会被 history fallback 接走 → 跳回首页。
      //
      // target 必须写 `localhost` 而不是 `127.0.0.1`：nuxi dev 底下的 listhen 默认把
      // `localhost` 解析成 `::1`，dev server 只 bind 了 IPv6 回环。写死 IPv4 字面量时
      // 连不上（IP 字面量没有 DNS 回退），Vite 把 ECONNREFUSED 兜成 **HTTP 500**——
      // 浏览器直连 8610 却是通的，所以极像 SSR 报错，其实压根没连上。
      // 用主机名则走 Node 20+ 默认开启的 Happy Eyeballs，IPv4/IPv6 都能接上。
      // 另一半在 focus-studio/nuxt.config.ts 里把 devServer.host 钉成 127.0.0.1，
      // 两边任一生效都能连通。
      "^/focus-studio": {
        target: "http://localhost:8610",
        changeOrigin: true,
        ws: true,
      },
      // 打字星球的词库 JSON。前端在主应用代理后用绝对路径 `/dicts/xxx.json` 拿词库，
      // 没有这条代理会吃 SPA fallback → 404 → 单词页 isLoading 永远 true → 转圈。
      // 路径要补上 8605 vite 的 base 前缀（qwerty 的 public/dicts 在 base 下）。
      "^/dicts": {
        target: "http://127.0.0.1:8605",
        rewrite: (p) => p.replace(/^\/dicts/, "/typing-studio-qwerty/dicts") || "/typing-studio-qwerty/dicts",
      },
    },
  },
});
