// Uppy 本地化 bundle 入口：打包后产物 public/admin/vendor/uppy/uppy.esm.js
// 打包命令（esbuild 是 vite 的传递依赖）：
//   node_modules/.bin/esbuild scripts/uppy-entry.js --bundle --format=esm \
//     --outfile=public/admin/vendor/uppy/uppy.esm.js --target=es2020
export { Uppy } from "@uppy/core";
export { default as Dashboard } from "@uppy/dashboard";
export { default as AwsS3 } from "@uppy/aws-s3";
