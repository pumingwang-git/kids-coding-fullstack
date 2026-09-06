'use strict';

/**
 * 去紫：把 scratch-gui 产物里的官方紫（`$looks-secondary`）换成平台主色。
 *
 * 为什么在构建期改字符串，而不是在运行时写一堆覆盖规则：
 *
 *  1. **官方紫不是 CSS 变量。** `colors.css` 里的 `$looks-secondary` 是 Sass 变量，
 *     编译进 npm 产物时已经变成字面量 `hsla(260, 60%, 60%, …)`，运行时没有变量可覆盖。
 *  2. **覆盖规则要盯类名，构建哈希每次升级都变。** 全站有 300+ 处紫色，靠
 *     `[class*="xxx_"]` 一条条盖，等于给自己养一张永远会漏的清单。
 *  3. **懒加载 chunk 的样式后注入。** 造型/声音编辑器的 CSS 是点开那一刻才插进
 *     `<head>` 的，插在我们的覆盖规则之后 —— 想赢只能全上 `!important`。
 *
 * 改字面量把这三件事一次消掉：菜单栏、下拉菜单、右键菜单、添加角色/背景圆钮、
 * 添加扩展、各种对话框主按钮、删除徽标、声音编辑器…… 只要用的是官方紫，全都跟着走。
 * 这条路子仓库里已有先例（`webpack.config.js` 的 `ScratchSecurityPatchPlugin` 就是
 * 在同一个 hook 上改产物文本）。
 *
 * ⚠️ **积木本身的紫色不许动。** 「外观」类积木是 `#855CD6`，但它走的是 Blockly 的
 * 主题对象（`colourSecondary:"#855CD6"`，带引号的 JS 字符串），不是 CSS。积木配色是
 * Scratch 的语言的一部分，学生按颜色找积木；染绿了等于把教材改了。所以十六进制那条
 * 规则**带引号哨兵**：紧邻引号的一律跳过。实测产物里 `#855CD6` 出现 154 次，其中
 * 带引号的正好 2 处（motion/zelos 两张主题表），其余 152 处全在 CSS 里。
 *
 * 三条替换**逐字节等长**，故意的：产物在 source map 生成之后才被改，长度一变
 * 所有 mapping 就整体错位，调试时点行号会跳到别处。
 */

const assert = require('node:assert/strict');

/** 平台主色。与 `index.html` 的 `--accent` / `public/admin/admin.css` 同源。 */
const ACCENT = '#2f806e';

/** 主色的深一档，对应官方的 `$looks-tertiary`（角色圆钮展开后那条竖列）。 */
const ACCENT_DEEP = '#256557';

/**
 * 字面量替换表。`from` 一律截到 alpha 之前，这样
 * `…, 1)` / `…, 0.35)` / `…, 0.15)` 三种透明度都跟着换，不用各写一条。
 *
 * hsl 三元组是上面两个十六进制色的等值写法（`#2f806e` = hsl(167, 46%, 34.3%)，
 * `#256557` = hsl(167, 46%, 27.1%)）——小数位是凑够 18 个字符用的，不是精度需要。
 */
const LITERAL_REPLACEMENTS = [
    // $looks-secondary #855CD6：菜单栏、下拉菜单、圆钮、对话框主按钮……
    ['hsla(260, 60%, 60%', 'hsla(167,46%,34.3%'],
    // $looks-tertiary #714EB6：角色/背景圆钮展开后的那条竖列底色
    ['hsla(260, 42%, 51%', 'hsla(167,46%,27.1%']
];

for (const [from, to] of LITERAL_REPLACEMENTS) {
    assert.equal(from.length, to.length, `调色替换必须等长，否则 source map 整体错位：${from}`);
}
assert.equal(ACCENT.length, '#855CD6'.length);

/**
 * 十六进制那条走单独的正则：scratch-paint（造型编辑器）的 CSS 用的是 `#855CD6`
 * 而不是 hsla。前后哨兵引号把 Blockly 主题表里的积木配色排除在外。
 */
const HEX_PURPLE = /(?<!")#855cd6(?!")/gi;

/** 把一份产物文本里的官方紫换成平台主色。不改其他任何东西。 */
function repaintScratchPurple (source) {
    let out = source;
    for (const [from, to] of LITERAL_REPLACEMENTS) {
        out = out.split(from).join(to);
    }
    return out.replace(HEX_PURPLE, ACCENT);
}

/**
 * 残留检查：换完之后还剩官方紫，就说明上面的表跟不上产物了（升级换了写法、
 * 或者新出了一种紫）。返回第一处残留的字符串，没有残留返回 null。
 *
 * 带引号的积木配色**不算残留**——那是故意留的。
 */
function findResidualPurple (source) {
    for (const [from] of LITERAL_REPLACEMENTS) {
        if (source.includes(from)) return from;
    }
    const hex = source.match(HEX_PURPLE);
    return hex ? hex[0] : null;
}

module.exports = {
    ACCENT,
    ACCENT_DEEP,
    LITERAL_REPLACEMENTS,
    repaintScratchPurple,
    findResidualPurple
};
