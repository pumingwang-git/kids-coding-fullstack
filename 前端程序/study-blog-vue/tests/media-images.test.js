// @vitest-environment jsdom
// 题干配图的渲染护栏：src 白名单与尺寸后缀在后台与学员端是同一份实现（installImageHooks），
// 学员端漏装的后果比后台严重——题面里一条外链就能把每个考生的 IP 发给第三方站点。
import DOMPurify from "dompurify";
import { beforeEach, describe, expect, it } from "vitest";
import {
  IMAGE_WIDTHS,
  installImageHooks,
  rewriteImageWidth,
  sanitizeRenderedHtml,
  splitImageAlt,
} from "../public/admin/admin-markdown.js";

// 后端 media_relative_path() 拼出来的形状：/media/{sha[:2]}/{sha}.{ext}
const SHA = "a".repeat(64);
const GOOD = `/media/${SHA.slice(0, 2)}/${SHA}.png`;

describe("题干配图的 src 白名单", () => {
  // addHook 是累加的、装过的标记留在实例上，每个用例都从干净状态开始，
  // 否则"重复安装不会叠加"那条会因为前一个用例装过而失去意义。
  beforeEach(() => {
    DOMPurify.removeAllHooks();
    delete DOMPurify.__imageHooksInstalled;
  });

  it("放行同源 /media/ 配图", () => {
    installImageHooks(DOMPurify);
    const html = DOMPurify.sanitize(`<img src="${GOOD}">`, { USE_PROFILES: { html: true } });
    expect(html).toContain(GOOD);
    expect(html).not.toContain("data-blocked-src");
  });

  it("摘掉外链图的 src，但留下坏图占位", () => {
    installImageHooks(DOMPurify);
    const html = DOMPurify.sanitize('<img src="https://evil.example.com/track.png">', {
      USE_PROFILES: { html: true },
    });
    expect(html).not.toContain("evil.example.com");
    expect(html).toContain("data-blocked-src");
    expect(html).toContain("<img");
  });

  it("摘掉 data: 内联图", () => {
    installImageHooks(DOMPurify);
    const html = DOMPurify.sanitize('<img src="data:image/png;base64,iVBORw0KGgo=">', {
      USE_PROFILES: { html: true },
    });
    expect(html).not.toContain("base64");
    expect(html).toContain("data-blocked-src");
  });

  it("路径形状不对的一律摘掉（防止 /media/ 前缀被拿来当跳板）", () => {
    installImageHooks(DOMPurify);
    for (const bad of ["/media/../../etc/passwd", "/media/zz/notahash.png", "/media/aa/aa.png"]) {
      const html = DOMPurify.sanitize(`<img src="${bad}">`, { USE_PROFILES: { html: true } });
      expect(html, bad).toContain("data-blocked-src");
    }
  });

  it("重复安装不会叠加钩子", () => {
    installImageHooks(DOMPurify);
    installImageHooks(DOMPurify);
    installImageHooks(DOMPurify);
    const html = DOMPurify.sanitize(`<img src="${GOOD}">`, { USE_PROFILES: { html: true } });
    expect(html).toContain(GOOD);
  });

  it("后台 sanitizeRenderedHtml 自动装钩子", () => {
    window.DOMPurify = DOMPurify;
    const html = sanitizeRenderedHtml('<p><img src="https://evil.example.com/x.png"></p>');
    expect(html).not.toContain("evil.example.com");
    expect(DOMPurify.__imageHooksInstalled).toBe(true);
  });
});

describe("题干配图的尺寸改写", () => {
  it("改写产物仍是 Markdown 图片，不是内联 HTML", () => {
    // 这条是整个尺寸档位功能的地基。改写成 <img> 的那一版，Vditor 的 IR 模式对行内 HTML
    // 只给一个 0×0 的隐藏 marker，图会直接从编辑器里消失、再也点不回来改第二次。
    const next = rewriteImageWidth(`![](${GOOD})`, GOOD, "50%");
    expect(next).toBe(`![|50%](${GOOD})`);
    expect(next).not.toContain("<img");
  });

  it("改尺寸时 alt 跟着搬家", () => {
    // 丢了 alt，改一次尺寸就把无障碍文本抹掉了，而且作者不会发现
    expect(rewriteImageWidth(`如图 ![三角形](${GOOD}) 所示`, GOOD, "75%")).toBe(
      `如图 ![三角形|75%](${GOOD}) 所示`,
    );
    expect(rewriteImageWidth(`![三角形|75%](${GOOD})`, GOOD, "")).toBe(`![三角形](${GOOD})`);
  });

  it("旧数据里的 <img width> 顺手迁到新写法", () => {
    expect(rewriteImageWidth(`<img src="${GOOD}" alt="三角形" width="75%">`, GOOD, "50%")).toBe(
      `![三角形|50%](${GOOD})`,
    );
    expect(rewriteImageWidth(`<img src="${GOOD}" width="75%">`, GOOD, null)).toBe(`![](${GOOD})`);
  });

  it("alt 里的替换模式字符不会被 String.replace 吃掉", () => {
    // `$&` 在字符串形式的替换里是"整个匹配"，不走函数形式的话会把整段源码塞回去
    expect(rewriteImageWidth(`![价格 $& 说明](${GOOD})`, GOOD, "50%")).toBe(
      `![价格 $& 说明|50%](${GOOD})`,
    );
  });

  it("已有尺寸的再改是替换而不是叠加", () => {
    const once = rewriteImageWidth(`![三角形](${GOOD})`, GOOD, "25%");
    const twice = rewriteImageWidth(once, GOOD, "100%");
    expect(twice).toBe(`![三角形|100%](${GOOD})`);
    expect(twice.match(/\|/g)).toHaveLength(1);
  });

  it("alt 正文里本来就有竖线时只认最末尾那段", () => {
    expect(rewriteImageWidth(`![甲|乙](${GOOD})`, GOOD, "50%")).toBe(`![甲|乙|50%](${GOOD})`);
    expect(splitImageAlt("甲|乙|50%")).toEqual({ text: "甲|乙", width: "50%" });
  });

  it("只认档位里的四个值，别的百分比留在 alt 正文里", () => {
    // 编辑区那侧是四条写死的 CSS 规则，放行任意值就会"源码里写了、编辑器不认"
    expect(splitImageAlt("三角形|60%")).toEqual({ text: "三角形|60%", width: "" });
    expect(splitImageAlt("三角形|100%")).toEqual({ text: "三角形", width: "100%" });
  });

  it("不匹配的 src 一个字都不动", () => {
    const source = "没有这张图 ![](/media/zz/other.png)";
    expect(rewriteImageWidth(source, GOOD, "50%")).toBe(source);
  });

  it("档位里的最小值与 CSS 默认宽度一致", () => {
    // admin.css 与 MarkdownBody.vue 里 img:not([width]) 的默认是 25%。
    // 这里对不上，"小"就会和"没设过"显示成两个大小。
    expect(IMAGE_WIDTHS[0].value).toBe("25%");
  });
});

describe("渲染出口把 alt 后缀翻成 width", () => {
  beforeEach(() => {
    DOMPurify.removeAllHooks();
    delete DOMPurify.__imageHooksInstalled;
    installImageHooks(DOMPurify);
  });

  const sanitize = (html) => DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });

  it("后缀变成 width 属性，并从 alt 上摘掉", () => {
    // 留在 alt 里的话读屏器会把"三角形竖线五十百分号"念出来
    const html = sanitize(`<img src="${GOOD}" alt="三角形|50%">`);
    expect(html).toContain('width="50%"');
    expect(html).toContain('alt="三角形"');
    expect(html).not.toContain("|50%");
  });

  it("alt 只有后缀时不留下空 alt", () => {
    const html = sanitize(`<img src="${GOOD}" alt="|75%">`);
    expect(html).toContain('width="75%"');
    expect(html).not.toContain("alt=");
  });

  it("旧数据的 width 属性照旧生效", () => {
    expect(sanitize(`<img src="${GOOD}" width="50%">`)).toContain('width="50%"');
  });

  it("没有后缀就不设 width——CSS 的默认 25% 靠 :not([width]) 生效", () => {
    expect(sanitize(`<img src="${GOOD}" alt="三角形">`)).not.toContain("width=");
  });
});
