// Video.js 本地化 bundle 入口：打包后产物 public/admin/vendor/videojs/videojs.esm.js
// 打包命令（esbuild 是 vite 的传递依赖）：
//   node_modules/.bin/esbuild scripts/videojs-entry.js --bundle --format=esm \
//     --outfile=public/admin/vendor/videojs/videojs.esm.js --target=es2020
export { default } from "video.js";
