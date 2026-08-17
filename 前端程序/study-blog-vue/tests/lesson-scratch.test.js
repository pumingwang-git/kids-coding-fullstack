// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import BlockScratch from "../src/components/lesson/blocks/BlockScratch.vue";

function mountBlock(block = {}) {
  return mount(BlockScratch, {
    props: {
      lessonId: 12,
      block: { id: 34, block_type: "scratch", title: "小猫走路", ...block },
    },
    global: { stubs: { LessonIcon: true, VideoPlayer: true } },
  });
}

describe("BlockScratch", () => {
  it("只用非敏感课时/内容块上下文打开同域 Studio", () => {
    const wrapper = mountBlock({ scratch: { challenge_id: 9 } });
    const link = wrapper.find("a");
    expect(link.attributes("href")).toBe("/scratch-studio/?lesson_id=12&block_id=34");
    expect(link.text()).toContain("打开编程工作台");
    expect(link.attributes("href")).not.toContain("token");
  });

  it("通过状态只能来自服务器 DTO，不由组件自行判分", () => {
    const wrapper = mountBlock({
      scratch: { challenge_id: 9, submission_status: "failed", feedback: "还要让小猫移动 10 步" },
    });
    expect(wrapper.text()).toContain("还需要调整");
    expect(wrapper.text()).toContain("还要让小猫移动 10 步");

    const passed = mountBlock({ scratch: { challenge_id: 9, submission_status: "passed" } });
    expect(passed.text()).toContain("本关已通过");
    expect(passed.text()).toContain("查看作品");
  });

  it("未配置挑战时不给出可用入口，并把说明交给课时壳", async () => {
    const wrapper = mountBlock();
    await wrapper.find("a").trigger("click");
    expect(wrapper.emitted("toast")?.[0]).toEqual([
      "该 Scratch 任务尚未配置，暂时不能进入工作台。",
    ]);
  });

  it("保留壳提供的课时导航插槽，不在块内直接完成课时", () => {
    const wrapper = mount(BlockScratch, {
      props: {
        lessonId: 12,
        block: { id: 34, block_type: "scratch", scratch: { challenge_id: 9 } },
      },
      slots: { next: '<button class="shell-next">继续下一块</button>' },
      global: { stubs: { LessonIcon: true, VideoPlayer: true } },
    });
    expect(wrapper.find(".shell-next").exists()).toBe(true);
    expect(wrapper.text()).toContain("请在工作台内提交并通过本关");
  });

  it("示范项目入口只在服务端标记开放后出现，且页面里没有 .sb3 地址", () => {
    // 有示范项目但未提交：只说"有这么一份"，不给入口。
    const pending = mountBlock({ scratch: { challenge_id: 9, has_demo: true } });
    expect(pending.text()).toContain("提交作品并得到结果后可只读查看");
    expect(pending.findAll("a")).toHaveLength(1);
    expect(pending.text()).not.toContain("查看示范项目");

    const open = mountBlock({
      scratch: { challenge_id: 9, has_demo: true, demo_available: true, submission_status: "failed" },
    });
    const links = open.findAll("a");
    expect(links).toHaveLength(2);
    expect(links[1].attributes("href")).toBe(
      "/scratch-studio/?lesson_id=12&block_id=34&mode=student_demo",
    );
    expect(open.text()).toContain("查看示范项目");
    // 答案文件的地址压根不该出现在 DOM 里——学生随手看源码就能拿到。
    expect(open.html()).not.toContain("demo.sb3");
  });

  it("判定中不放行示范项目：只信 demo_available，不由本地状态推断", () => {
    const evaluating = mountBlock({
      scratch: { challenge_id: 9, has_demo: true, submission_status: "evaluating" },
    });
    expect(evaluating.text()).not.toContain("查看示范项目");
    expect(evaluating.findAll("a")).toHaveLength(1);
  });

  it("解析视频只在服务端标记为提交后可用时渲染", () => {
    const locked = mountBlock({ scratch: { challenge_id: 9, has_analysis_video: true } });
    expect(locked.text()).toContain("提交作品并得到结果后可观看");
    expect(locked.find("video-player-stub").exists()).toBe(false);

    const available = mountBlock({
      scratch: { challenge_id: 9, has_analysis_video: true, analysis_available: true },
    });
    const player = available.find("video-player-stub");
    expect(player.exists()).toBe(true);
    expect(player.attributes("playpath")).toBe("/api/scratch/lesson-blocks/34/analysis-play");
  });
});
