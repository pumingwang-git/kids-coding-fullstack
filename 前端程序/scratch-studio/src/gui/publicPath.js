/**
 * 把 Studio 的运行时 publicPath 挂到全局，供 `webpack.config.js` 里的
 * `NestedPublicPathPlugin` 回填进 scratch-gui 产物。
 *
 * ## 为什么需要这个
 *
 * `@scratch/scratch-gui` 的 dist 里嵌着**第二个** webpack runtime（打包
 * scratch-storage 时留下的），它的 publicPath 被**硬编码成 `"/"`**：
 *
 *     __nested_webpack_require_108080__.p = "/"
 *     __nested_webpack_require_108080__.u = e => "chunks/fetch-worker.<hash>.js"
 *
 * 它只负责一件事——起 scratch-storage 的取数 worker。素材（背景 / 角色 / 声音）
 * 的字节全部由这个 worker 去拉，主线程只等它回话。
 *
 * Studio 单独跑在 8602 时根路径就是自己，`/chunks/fetch-worker.js` 恰好能命中，
 * 所以直连调试一切正常。挂到主站 `/scratch-studio/` 之后，这条请求打的仍然是
 * **站点根**，于是被 Vue 那边的 SPA history fallback 接走，回来一份 index.html，
 * worker 里当场 `Uncaught SyntaxError: Unexpected token '<'`。
 *
 * worker 起不来的后果不是报错，是**静默**：`storage.load()` 的 Promise 永远
 * 不 settle，`vm.addBackdrop()` / `vm.addSprite()` 卡在 `loadCostume` 里，
 * 素材库照常显示（缩略图走 `cdn.assets.scratch.mit.edu` 的绝对地址，不经这条路），
 * 点一下却什么都不发生。2026-08-27 实测：直连 8602 点背景，背景数 1 → 2；
 * 同一次点击走 5173 的 `/scratch-studio/`，背景数纹丝不动停在 1。
 *
 * 外层那个 runtime（`publicPath: 'auto'`）是好的，`static/`、`chunks/*-steps.js`
 * 都正确解析到 `/scratch-studio/` 下；坏的只有被硬编码的这一个。
 *
 * ## 为什么不直接读 `__webpack_require__.p`
 *
 * 补丁是在 `processAssets` 阶段往**已压缩**的产物里塞字符串，webpack 不会再解析它。
 * 生产构建里 runtime 变量早被压缩器改名，`__webpack_require__` 在那段代码的作用域里
 * 根本不叫这个名字——写成读它，dev 能过、prod 静默退回 `"/"`，等于没修。
 * 所以走一个自己声明的全局：`__webpack_public_path__` 由 webpack 在编译期替换成
 * 运行时 publicPath 变量，dev 与 prod 拿到的都是真值。
 *
 * 必须是 `src/index.jsx` 的**第一个** import：ESM 按声明顺序求值，排在
 * `@scratch/scratch-gui` 后面就晚于它初始化了。
 */
window.__STUDIO_PUBLIC_PATH__ = __webpack_public_path__;
