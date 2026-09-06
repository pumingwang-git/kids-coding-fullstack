// Scratch 工作台的"去紫"是**构建期字面量替换**（见 scratch-studio/scripts/brand-palette.cjs）：
// 官方紫编译进产物时已经是字面量，运行时没有变量可覆盖，300+ 处也不可能靠类名一条条盖。
//
// 这里守四件事：
//
//  1. 该换的都换掉——hsla 三种透明度、以及造型编辑器用的十六进制写法；
//  2. **不该换的一个都别动**——「外观」积木也是 #855CD6，但那是 Blockly 主题表里带引号的
//     JS 字符串。积木配色是 Scratch 这门语言的一部分（学生按颜色找积木），染绿了等于改教材。
//     这条是"别拦过头"的哨兵，比上一条更容易写错；
//  3. 替换逐字节等长——产物在 source map 生成之后才被改，长度一变 mapping 整体错位；
//  4. 主色只有一个来源——`brand-palette.cjs` 的 ACCENT 必须与 index.html 的 `--accent`
//     （与 public/admin/admin.css 同源）逐字相同，否则工作台里会出现"两种绿"。
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const {
  ACCENT,
  ACCENT_DEEP,
  LITERAL_REPLACEMENTS,
  repaintScratchPurple,
  findResidualPurple,
} = require("../../scratch-studio/scripts/brand-palette.cjs");

const STUDIO_INDEX = fileURLToPath(
  new URL("../../scratch-studio/index.html", import.meta.url),
);

/** hsl(H, S%, L%) → #rrggbb，用来核对替换值确实是 ACCENT 的等值写法。 */
function hslToHex(h, s, l) {
  const sat = s / 100;
  const lig = l / 100;
  const c = (1 - Math.abs(2 * lig - 1)) * sat;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = lig - c / 2;
  const [r, g, b] = h >= 120 && h < 180 ? [0, c, x] : [c, x, 0];
  const to255 = (v) => Math.round((v + m) * 255).toString(16).padStart(2, "0");
  return `#${to255(r)}${to255(g)}${to255(b)}`;
}

function parseHsl(prefix) {
  const [h, s, l] = prefix.replace("hsla(", "").split(",").map(parseFloat);
  return hslToHex(h, s, l);
}

describe("Scratch 工作台去紫", () => {
  it("菜单栏 / 圆钮那类 hsla 紫全换成主色，三种透明度都跟着走", () => {
    const css = [
      ".menu-bar { background-color: hsla(260, 60%, 60%, 1); }",
      ".ring { box-shadow: 0 0 0 4px hsla(260, 60%, 60%, 0.35); }",
      ".tint { background: hsla(260, 60%, 60%, 0.15); }",
      ".more-column { background: hsla(260, 42%, 51%, 1); }",
    ].join("\n");
    const painted = repaintScratchPurple(css);
    expect(painted).not.toContain("hsla(260,");
    expect(painted).toContain("hsla(167,46%,34.3%, 1)");
    expect(painted).toContain("hsla(167,46%,34.3%, 0.35)");
    expect(painted).toContain("hsla(167,46%,34.3%, 0.15)");
    expect(painted).toContain("hsla(167,46%,27.1%, 1)");
  });

  it("造型编辑器那套十六进制写法也换（scratch-paint 用的是 #855CD6 不是 hsla）", () => {
    const css = ".tool.is-selected { background-color: #855CD6; }";
    expect(repaintScratchPurple(css)).toBe(
      `.tool.is-selected { background-color: ${ACCENT}; }`,
    );
  });

  // —— 哨兵：这条一旦变红，说明替换写宽了，积木被染色 ——
  it("积木配色原样保留：带引号的 #855CD6 是 Blockly 主题表，不是 CSS", () => {
    const theme = 'looks:{colourPrimary:"#9966FF",colourSecondary:"#855CD6",colourTertiary:"#774DCB"}';
    expect(repaintScratchPurple(theme)).toBe(theme);
    expect(findResidualPurple(repaintScratchPurple(theme))).toBeNull();
  });

  it("替换逐字节等长，source map 的 mapping 不会整体错位", () => {
    for (const [from, to] of LITERAL_REPLACEMENTS) {
      expect(to).toHaveLength(from.length);
    }
    expect(ACCENT).toHaveLength("#855CD6".length);

    const css = ".a { color: hsla(260, 60%, 60%, 1); border: 1px solid #855CD6; }";
    expect(repaintScratchPurple(css)).toHaveLength(css.length);
  });

  it("残留检查：换之前报得出来，换之后为 null", () => {
    const css = ".a { background: hsla(260, 42%, 51%, 1); }";
    expect(findResidualPurple(css)).toBe("hsla(260, 42%, 51%");
    expect(findResidualPurple(repaintScratchPurple(css))).toBeNull();
    expect(findResidualPurple(".a { color: #855cd6; }")).toBe("#855cd6");
  });

  it("替换值就是 ACCENT / ACCENT_DEEP 的等值写法，不是另挑的绿", () => {
    expect(parseHsl(LITERAL_REPLACEMENTS[0][1])).toBe(ACCENT);
    expect(parseHsl(LITERAL_REPLACEMENTS[1][1])).toBe(ACCENT_DEEP);
  });

  it("主色单一来源：与工作台 index.html 的 --accent 逐字相同", () => {
    const tokens = readFileSync(STUDIO_INDEX, "utf8");
    expect(tokens).toMatch(new RegExp(`--accent:\\s*${ACCENT};`));
  });
});
