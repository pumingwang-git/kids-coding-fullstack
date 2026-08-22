/**
 * 平台扩展垫片（构建时拼在每个扩展体前面，各扩展不得自带副本）。
 *
 * 为什么需要它：我们的扩展按 **TurboWarp 沙箱格式**写（`Scratch.extensions.register`
 * + `getInfo()`，与 TurboWarp 官方 hello-world 同形），这样同一份代码将来若真迁到
 * TW / Gandi 的 VM 也能直接用。但 LLK 15.0.1 的 `extension-worker.js` 只暴露四样东西：
 *
 *     Scratch.ArgumentType / BlockType / TargetType / extensions.register
 *
 * TW 沙箱模式里常用的 `Scratch.Cast`、`Scratch.translate` 它没有。这段垫片补的就是
 * 这几个**纯函数**，补完两边的差集就基本抹平了。
 *
 * ## 只补这些，别再加
 *
 * `Scratch.vm` / `Scratch.runtime` / `renderer` / `document` / `fetch` **一律不补**：
 * 扩展跑在独立 Worker 线程里，这些东西**根本拿不到**，假装有只会让扩展在运行时
 * 才炸，比加载时就炸更难查。需要它们的扩展属于"非沙箱"那一档，只能等迁 VM，
 * 见《51、Scratch 扩展接入方案》§2。
 *
 * `self.window = self` 是唯一的例外，且**只为让"检测 window 是否存在"的写法不炸**，
 * 它不带来任何 DOM 能力。
 */

/* eslint-env worker */
/* global Scratch */

self.window = self;

Scratch.Cast = {
    toNumber (value) {
        const n = Number(value);
        return isNaN(n) ? 0 : n;
    },
    toString (value) {
        return String(value);
    },
    toBoolean (value) {
        if (typeof value === 'boolean') return value;
        if (typeof value === 'string') {
            return value !== '' && value !== '0' && value.toLowerCase() !== 'false';
        }
        return Boolean(value);
    }
};

Scratch.translate = message => (message && message.default) || message;
