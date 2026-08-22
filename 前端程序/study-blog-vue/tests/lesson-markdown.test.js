// @vitest-environment jsdom
// P0-1 护栏：课时正文与课包简介必须走统一 Markdown 管线（标题/列表/代码块真实渲染），
// 且渲染出口做 XSS 净化。人工验收第 11 步「试看图文课时能正确渲染 Markdown」依赖这两条。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { renderMarkdown } from "../src/services/markdown";

vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { lessonId: "1" } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: "<a><slot /></a>" },
}));

// 学习页有 400ms 的加载页最短展示时长（交接文档 14 §3.2：接口 80ms 返回时闪一下
// 比不闪更廉价），断言前必须等过这段，否则拿到的还是加载页。
const settle = () => new Promise((r) => setTimeout(r, 520));

/** 按新 DTO 造一节课时：内容以 blocks[] 下发，每块带两道闸门合成的 lock_reason。 */
function lessonWithBlocks(blocks, extra = {}) {
  return {
    id: 1,
    course_id: 9,
    course_title: "CSP-J 冲刺营",
    title: "环境安装",
    open_policy: "whole",
    trial_block_count: 0,
    unlocked: true,
    progress: { total: blocks.length, done: 0, percent: 0 },
    prev_lesson_id: null,
    next_lesson_id: null,
    blocks: blocks.map((b, i) => ({
      id: i + 1,
      sort_order: i,
      title: b.title || "块",
      can_access: true,
      unlock_rule: "free",
      is_unlocked: true,
      completed: false,
      lock_reason: null,
      ...b,
    })),
    ...extra,
  };
}

vi.mock("../src/services/auth", () => ({
  request: vi.fn(),
}));

import LessonPlayer from "../src/views/LessonPlayer.vue";
import CourseDetail from "../src/views/CourseDetail.vue";
import { request } from "../src/services/auth";

const markdown = `# 第一章 环境安装

先看这段**重点**：

- 安装编译器
- 配置环境变量
- 验证版本

\`\`\`bash
g++ --version
\`\`\`

> 提示：按 Ctrl+S 保存。`;

describe("renderMarkdown 管线（核心断言）", () => {
  it("标题/列表/代码块/加粗/引用都渲染成对应标签", () => {
    const html = renderMarkdown(markdown);
    expect(html).toContain("<h1>第一章 环境安装</h1>");
    expect(html).toContain("<strong>重点</strong>");
    expect(html).toContain("<ul>");
    expect(html).toContain("<li>安装编译器</li>");
    expect(html).toContain("<pre><code class=\"language-bash\">");
    expect(html).toContain("<blockquote>");
  });

  it("脚本标签被 DOMPurify 剥掉（XSS 防线）", () => {
    const html = renderMarkdown("# 标题\n\n<script>window.__xss = 1</script>\n\n<img src=x onerror=alert(1)>");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("onerror");
  });
});

describe("LessonPlayer.vue 课时正文", () => {
  beforeEach(() => {
    request.mockReset();
    request.mockResolvedValue(
      lessonWithBlocks([{ block_type: "markdown", title: "环境安装", content_md: markdown }]),
    );
  });

  it("正文渲染出标题、列表与代码块（不再是按换行拆 <p>）", async () => {
    const wrapper = mount(LessonPlayer);
    await settle();
    const html = wrapper.find(".block-article").html();
    expect(html).toContain("<h1>第一章 环境安装</h1>");
    expect(html).toContain("<li>安装编译器</li>");
    expect(html).toContain("<code class=\"language-bash\">");
  });

  it("正文中的脚本被净化", async () => {
    request.mockResolvedValue(
      lessonWithBlocks([
        { block_type: "markdown", content_md: "# t\n\n<script>window.__x=1</script>" },
      ]),
    );
    const wrapper = mount(LessonPlayer);
    await settle();
    expect(wrapper.find(".block-article").html()).not.toContain("<script");
  });

  it("加载完成后自动落到第一个内容块，不需要用户点任何东西（交接文档 §3.3）", async () => {
    request.mockResolvedValue(
      lessonWithBlocks([
        { block_type: "markdown", title: "第一块", content_md: "# 第一块" },
        { block_type: "markdown", title: "第二块", content_md: "# 第二块" },
      ]),
    );
    const wrapper = mount(LessonPlayer);
    await settle();
    expect(wrapper.find(".block-article").html()).toContain("第一块");
    // 主区一次只呈现一个块：第二块此刻不该在 DOM 里
    expect(wrapper.findAll(".block-article")).toHaveLength(1);
  });

  it("未指定内容块时，默认打开第一个阅读资料", async () => {
    request.mockResolvedValue(
      lessonWithBlocks([
        { block_type: "markdown", title: "课程导语", content_md: "# 课程导语" },
        { block_type: "materials", title: "阅读资料" },
        { block_type: "markdown", title: "补充说明", content_md: "# 补充说明" },
      ]),
    );
    const wrapper = mount(LessonPlayer);
    await settle();
    expect(wrapper.find(".block-materials").exists()).toBe(true);
    expect(wrapper.text()).toContain("阅读资料");
  });
});

describe("LessonPlayer.vue 两道闸门（交接文档 §4.5）", () => {
  beforeEach(() => request.mockReset());

  it("权限锁：文案指向开通，出口按钮是「查看课包并开通」", async () => {
    request.mockResolvedValue(
      lessonWithBlocks(
        [{ block_type: "markdown", title: "收费块", can_access: false, lock_reason: "not_enrolled" }],
        { open_policy: "first_n", trial_block_count: 3 },
      ),
    );
    const wrapper = mount(LessonPlayer);
    await settle();
    const text = wrapper.find(".locked-state").text();
    expect(text).toContain("需要开通");
    expect(text).toContain("前 3 块试看");
    expect(text).toContain("查看课包并开通");
    // 锁定块不下发正文，也就渲染不出正文容器
    expect(wrapper.find(".block-article").exists()).toBe(false);
  });

  it("顺序锁：文案指向继续学习，出口按钮是「回到未完成的内容块」", async () => {
    request.mockResolvedValue(
      lessonWithBlocks([
        { block_type: "markdown", title: "A", content_md: "# A" },
        {
          block_type: "markdown", title: "B",
          unlock_rule: "sequential", is_unlocked: false, lock_reason: "sequential",
        },
      ]),
    );
    const wrapper = mount(LessonPlayer);
    await settle();
    // 落点是 A（第一个不是顺序锁的块）
    expect(wrapper.find(".block-article").html()).toContain("A");
    // 抽屉里：顺序锁的块 disabled，点不进去
    const items = wrapper.findAll(".nav-item");
    expect(items).toHaveLength(2);
    expect(items[1].attributes("disabled")).toBeDefined();
    expect(items[1].attributes("title")).toContain("完成前面的内容块");
  });

  it("权限锁的块在抽屉里仍可点击——那是开通转化路径", async () => {
    request.mockResolvedValue(
      lessonWithBlocks([
        { block_type: "markdown", title: "A", content_md: "# A" },
        { block_type: "markdown", title: "B", can_access: false, lock_reason: "not_enrolled" },
      ]),
    );
    const wrapper = mount(LessonPlayer);
    await settle();
    const items = wrapper.findAll(".nav-item");
    expect(items[1].attributes("disabled")).toBeUndefined();
    expect(items[1].attributes("title")).toContain("开通");
  });
});

describe("CourseDetail.vue 课包简介", () => {
  beforeEach(() => {
    request.mockReset();
    request.mockResolvedValue({
      course: {
        id: 9, title: "CSP-J 冲刺营", subtitle: "零基础到参赛",
        description: "# 课程简介\n\n- 系统讲解\n- 真题演练",
        cover_url: null, category_name: "编程入门", difficulty: "beginner",
        total_minutes: 90,
      },
      enrolled: false,
      sections: [],
    });
  });

  it("简介走 Markdown 渲染（标题与列表真实出现）", async () => {
    const wrapper = mount(CourseDetail);
    await new Promise((r) => setTimeout(r, 0));
    const html = wrapper.find(".intro").html();
    expect(html).toContain("<h1>课程简介</h1>");
    expect(html).toContain("<li>系统讲解</li>");
  });

  it("已开通课包不显示课时试看标签", async () => {
    request.mockResolvedValue({
      course: {
        id: 9, title: "CSP-J 冲刺营", description: "", difficulty: "beginner",
        total_minutes: 90,
      },
      enrolled: true,
      sections: [{
        id: 1,
        title: "第一章",
        lessons: [
          { id: 11, title: "整节课", content_kind: "video", unlocked: true, open_policy: "whole" },
          { id: 12, title: "前两块", content_kind: "video", unlocked: true, open_policy: "first_n", trial_block_count: 2 },
        ],
      }],
    });
    const wrapper = mount(CourseDetail);
    await new Promise((r) => setTimeout(r, 0));
    expect(wrapper.findAll(".trial")).toHaveLength(0);
    expect(wrapper.find(".facts").text()).toContain("已开通");
  });
});

describe("LessonPlayer.vue 外链视频地址适配", () => {
  beforeEach(() => request.mockReset());

  const embedBlock = (url) =>
    lessonWithBlocks([
      { block_type: "video", title: "视频", source_type: "embed", video_url: url },
    ]);

  it("B 站普通播放页自动转为 player.bilibili.com 嵌入地址（6004 修复）", async () => {
    request.mockResolvedValue(embedBlock("https://www.bilibili.com/video/BV1GJ411x7h7?p=1"));
    const wrapper = mount(LessonPlayer);
    await settle();
    const src = wrapper.find("iframe.v-external").attributes("src");
    expect(src).toContain("player.bilibili.com/player.html?bvid=BV1GJ411x7h7");
  });

  it("已是嵌入地址则幂等保留，不加 referrerpolicy=no-referrer", async () => {
    request.mockResolvedValue(
      embedBlock("https://player.bilibili.com/player.html?bvid=BV1GJ411x7h7"),
    );
    const wrapper = mount(LessonPlayer);
    await settle();
    const iframe = wrapper.find("iframe.v-external");
    expect(iframe.attributes("src")).toContain("player.bilibili.com/player.html?bvid=BV1GJ411x7h7");
    expect(iframe.attributes("referrerpolicy")).toBeUndefined();
  });
});
