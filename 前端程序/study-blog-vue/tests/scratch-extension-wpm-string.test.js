// 平台自研 Scratch 扩展 `wpmStringV1` 的护栏。
//
// 这里不起真 Worker，而是用 node:vm 造一个**只有 LLK worker 那四样全局**的上下文，
// 把「垫片 + 扩展体」原样跑进去——和 `extension-worker.js` 里 `importScripts` 的
// 处境一致。
//
// 于是这份测试同时守两件事：
//  1. 每个积木的边界行为（空串、越界、起止写反、emoji、空分隔符…）；
//  2. **API 面**：上下文里故意不放 `document` / `Scratch.vm` / `Scratch.runtime` /
//     `fetch`，谁哪天顺手用了，跑到那行就 ReferenceError，测试立刻红。
//     这比写在文档里的任何一条纪律都管用。
//
// 背景见《51、Scratch 扩展接入方案》。
import { describe, expect, it, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const extDir = resolve(here, "../../scratch-studio/src/extensions");
const SHIM = readFileSync(resolve(extDir, "_shim.js"), "utf8");
const BODY = readFileSync(resolve(extDir, "wpmStringV1.js"), "utf8");

/** 照抄 extension-worker.js 暴露的那四样，一样不多。 */
function makeWorkerContext() {
  let registered = null;
  const sandbox = {
    Scratch: {
      ArgumentType: {
        ANGLE: "angle", BOOLEAN: "Boolean", COLOR: "color", NUMBER: "number",
        STRING: "string", MATRIX: "matrix", NOTE: "note", IMAGE: "image",
      },
      BlockType: {
        BOOLEAN: "Boolean", BUTTON: "button", COMMAND: "command",
        CONDITIONAL: "conditional", EVENT: "event", HAT: "hat",
        LOOP: "loop", REPORTER: "reporter",
      },
      TargetType: { SPRITE: "sprite", STAGE: "stage" },
      extensions: {
        register(instance) {
          registered = instance;
        },
      },
    },
  };
  sandbox.self = sandbox; // Worker 里 self 就是全局对象
  vm.createContext(sandbox);
  vm.runInContext(`${SHIM}\n${BODY}`, sandbox);
  return { sandbox, get instance() { return registered; } };
}

let ext;
let info;

beforeEach(() => {
  const ctx = makeWorkerContext();
  ext = ctx.instance;
  info = ext.getInfo();
});

describe("装载协议", () => {
  it("在只有四样全局的沙箱里能注册（即 worker 里能装上）", () => {
    expect(ext).toBeTruthy();
    expect(typeof ext.getInfo).toBe("function");
  });

  it("ID 与文件名一致——ID 就是脚本路径，对不上历史作品会打不开", () => {
    expect(info.id).toBe("wpmStringV1");
  });

  it("ID 带版本号，且只用字母数字（VM 会按 [\\w-] 清洗前缀）", () => {
    expect(info.id).toMatch(/^wpm[A-Za-z]+V\d+$/);
  });

  it("每个积木都有对应的实现函数", () => {
    for (const block of info.blocks) {
      expect(typeof ext[block.opcode], `缺少实现：${block.opcode}`).toBe("function");
    }
  });

  it("只用沙箱里存在的参数类型", () => {
    const allowed = new Set(Object.values({
      ANGLE: "angle", BOOLEAN: "Boolean", COLOR: "color", NUMBER: "number",
      STRING: "string", MATRIX: "matrix", NOTE: "note", IMAGE: "image",
    }));
    for (const block of info.blocks) {
      for (const arg of Object.values(block.arguments || {})) {
        expect(allowed.has(arg.type), `未知参数类型 ${arg.type}`).toBe(true);
      }
    }
  });
});

describe("API 面（越界即红）", () => {
  // 这条是静态兜底：函数体里没被测试调用到的越界写法，正则也能拦下。
  it("扩展体里不出现 vm / runtime / DOM / 网络 / 存储", () => {
    // 只扫代码：注释里会正当地提到这些词（比如文件头解释"为什么 ID 就是路径"
    // 时必然要写 importScripts），连注释一起扫会把说明文字判成违规。
    const code = BODY.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/^\s*\/\/.*$/gm, " ");
    const forbidden = [
      /\bdocument\b/, /\bXMLHttpRequest\b/, /\bfetch\s*\(/, /\bimportScripts\b/,
      /\beval\s*\(/, /new\s+Function\b/, /\blocalStorage\b/, /\bindexedDB\b/,
      /Scratch\s*\.\s*vm\b/, /Scratch\s*\.\s*runtime\b/,
    ];
    for (const re of forbidden) {
      expect(re.test(code), `扩展体命中禁用写法 ${re}`).toBe(false);
    }
  });

  it("沙箱里确实没有 document / fetch（保证上面那条不是空守）", () => {
    const { sandbox } = makeWorkerContext();
    expect(sandbox.document).toBeUndefined();
    expect(sandbox.fetch).toBeUndefined();
    expect(sandbox.Scratch.vm).toBeUndefined();
    expect(sandbox.Scratch.runtime).toBeUndefined();
  });
});

describe("字符串积木", () => {
  it("长度按“字”算，emoji 不被劈成两半", () => {
    // '👍'.length === 2，按码元算会得到 4，学生眼里明明是 3 个字
    expect(ext.length({ TEXT: "你好👍" })).toBe(3);
    expect(ext.length({ TEXT: "" })).toBe(0);
  });

  it("取第 N 个字：从 1 开始，越界给空串而不是报错", () => {
    expect(ext.charAt({ TEXT: "你好👍", INDEX: 3 })).toBe("👍");
    expect(ext.charAt({ TEXT: "你好", INDEX: 9 })).toBe("");
    expect(ext.charAt({ TEXT: "你好", INDEX: 0 })).toBe("");
    // 参数填了文字：Cast 兜成 0 → 越界 → 空串，不抛异常
    expect(ext.charAt({ TEXT: "你好", INDEX: "abc" })).toBe("");
  });

  it("截取：起止写反也能给出结果", () => {
    expect(ext.substring({ TEXT: "你好世界", FROM: 2, TO: 4 })).toBe("好世界");
    expect(ext.substring({ TEXT: "你好世界", FROM: 4, TO: 2 })).toBe("好世界");
    expect(ext.substring({ TEXT: "你好", FROM: 9, TO: 10 })).toBe("");
  });

  it("替换：空的被替换串直接返回原文（否则会插满每个字之间）", () => {
    expect(ext.replaceAll({ TEXT: "你好世界", FROM: "世界", TO: "同学" })).toBe("你好同学");
    expect(ext.replaceAll({ TEXT: "aaa", FROM: "a", TO: "b" })).toBe("bbb");
    expect(ext.replaceAll({ TEXT: "你好", FROM: "", TO: "X" })).toBe("你好");
  });

  it("查找位置：找不到给 0，位置按“字”算", () => {
    expect(ext.indexOf({ TEXT: "你好世界", SUB: "世" })).toBe(3);
    expect(ext.indexOf({ TEXT: "你好世界", SUB: "猫" })).toBe(0);
    // emoji 在前：按码元会算成 3，按字才是 2
    expect(ext.indexOf({ TEXT: "👍好", SUB: "好" })).toBe(2);
  });

  it("包含判断", () => {
    expect(ext.contains({ TEXT: "你好世界", SUB: "世" })).toBe(true);
    expect(ext.contains({ TEXT: "你好世界", SUB: "猫" })).toBe(false);
    expect(ext.contains({ TEXT: "你好", SUB: "" })).toBe(true);
  });

  it("大小写与去空白", () => {
    expect(ext.changeCase({ TEXT: "Hello", CASE: "upper" })).toBe("HELLO");
    expect(ext.changeCase({ TEXT: "Hello", CASE: "lower" })).toBe("hello");
    expect(ext.trim({ TEXT: "  你好  " })).toBe("你好");
  });

  it("分段：列表要靠文本 + 分隔符（沙箱拿不到 Scratch 列表对象）", () => {
    const args = { TEXT: "苹果,香蕉,橘子", SEP: "," };
    expect(ext.splitPart({ ...args, INDEX: 2 })).toBe("香蕉");
    expect(ext.splitPart({ ...args, INDEX: 9 })).toBe("");
    expect(ext.partCount(args)).toBe(3);
    expect(ext.partCount({ TEXT: "", SEP: "," })).toBe(0);
    // 分隔符为空 → 按字拆，比返回整串更符合直觉
    expect(ext.partCount({ TEXT: "你好👍", SEP: "" })).toBe(3);
  });
});
