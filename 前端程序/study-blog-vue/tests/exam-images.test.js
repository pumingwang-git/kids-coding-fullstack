// @vitest-environment jsdom
// 学员端题干配图的两条护栏：尺寸后缀在渲染出口翻成 width，以及"点图看大图"。
//
// 与 media-images.test.js 分家是有意的：那份直接对 DOMPurify 实例装/卸钩子，
// 而这里走的是 services/markdown.js —— 它在模块加载时就把钩子装在同一个
// DOMPurify 单例上了，两边混在一个文件里，那边的 removeAllHooks() 会把这边拆掉。

import { describe, expect, it, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { renderMarkdown } from "../src/services/markdown.js";
import { closeLightbox, lightbox } from "../src/stores/lightbox.js";
import MarkdownBody from "../src/components/exam/MarkdownBody.vue";

const SHA = "a".repeat(64);
const GOOD = `/media/${SHA.slice(0, 2)}/${SHA}.png`;

describe("学员端渲染管线认得尺寸后缀", () => {
  it("![alt|50%](src) 渲染成带 width 的 img，alt 上不留后缀", () => {
    const html = renderMarkdown(`如图 ![三角形|50%](${GOOD}) 所示`);
    expect(html).toContain('width="50%"');
    expect(html).toContain('alt="三角形"');
    expect(html).not.toContain("|50%");
  });

  it("图片独占一段也一样", () => {
    // 这是老 <img> 写法唯一还能显示的情形，换写法后不能反而退化
    expect(renderMarkdown(`![|100%](${GOOD})`)).toContain('width="100%"');
  });

  it("没设尺寸就不给 width——默认 25% 靠 CSS 的 :not([width]) 生效", () => {
    expect(renderMarkdown(`![三角形](${GOOD})`)).not.toContain("width=");
  });

  it("旧数据的内联 <img width> 继续显示", () => {
    const html = renderMarkdown(`<img src="${GOOD}" width="75%">`);
    expect(html).toContain('width="75%"');
    expect(html).toContain(GOOD);
  });

  it("外链图仍然被摘掉 src", () => {
    const html = renderMarkdown(`![外链|50%](https://evil.example.com/track.png)`);
    expect(html).not.toContain("evil.example.com");
    expect(html).toContain("data-blocked-src");
  });
});

describe("点题干配图看大图", () => {
  beforeEach(closeLightbox);

  it("点块级题干里的图会打开大图", () => {
    const wrapper = mount(MarkdownBody, { props: { source: `![三角形|50%](${GOOD})` } });
    wrapper.get("img").trigger("click");
    expect(lightbox.src).toBe(GOOD);
    // alt 的后缀在渲染出口就摘掉了，标题栏不该出现 "三角形|50%"
    expect(lightbox.alt).toBe("三角形");
  });

  it("选项里的行内图不劫持点击", () => {
    // 选项整块是个 <button>，在那儿开大图等于让学员想看清图就先把题答了
    const wrapper = mount(MarkdownBody, {
      props: { source: `![选项甲](${GOOD})`, inline: true },
    });
    wrapper.get("img").trigger("click");
    expect(lightbox.src).toBe("");
  });

  it("src 被摘掉的坏图点了没反应", () => {
    const wrapper = mount(MarkdownBody, {
      props: { source: `![外链](https://evil.example.com/x.png)` },
    });
    wrapper.get("img").trigger("click");
    expect(lightbox.src).toBe("");
  });

  it("点图片以外的地方不开大图", () => {
    const wrapper = mount(MarkdownBody, { props: { source: `如图 ![](${GOOD}) 所示` } });
    wrapper.get(".md-body").trigger("click");
    expect(lightbox.src).toBe("");
  });
});
