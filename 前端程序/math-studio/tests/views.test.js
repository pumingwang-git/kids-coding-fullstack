import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { push, replace } = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock("vue-router", () => ({
  RouterLink: { template: "<a><slot /></a>" },
  useRouter: () => ({ push, replace }),
  useRoute: () => ({ query: globalThis.__mathRouteQuery || {} }),
}));

vi.mock("../src/engine/game24", async (importOriginal) => {
  const original = await importOriginal();
  return { ...original, generatePuzzle: () => [1, 2, 3, 4] };
});

vi.mock("../src/platform/session", () => ({ getUser: () => ({ id: 7, username: "小宇" }) }));
import Game24PlayView from "../src/views/Game24PlayView.vue";
import LobbyView from "../src/views/LobbyView.vue";

function buttonByText(wrapper, text) {
  return wrapper.findAll("button").find((button) => button.text().includes(text));
}

async function enterCorrectExpression(wrapper) {
  for (const label of ["使用数字 1", "添加×号", "使用数字 2", "添加×号", "使用数字 3", "添加×号", "使用数字 4"]) {
    await wrapper.get(`[aria-label="${label}"]`).trigger("click");
  }
  await buttonByText(wrapper, "验证算式").trigger("click");
}

describe("数学星球大厅", () => {
  beforeEach(() => {
    push.mockReset();
    globalThis.__mathRouteQuery = {};
  });

  it("展示唯一可玩任务和学生统计", () => {
    const wrapper = mount(LobbyView, { global: { stubs: { RouterLink: true } } });
    expect(wrapper.text()).toContain("24 点");
    expect(wrapper.text()).not.toContain("我的记录");
    expect(wrapper.text()).not.toContain("最高分");
    expect(wrapper.text()).toContain("更多数学任务");
  });
});

describe("24 点游戏台", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-16T00:00:00Z"));
    push.mockReset();
    replace.mockReset();
    globalThis.__mathRouteQuery = { mode: "practice", difficulty: "easy" };
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it("给出成功与错误反馈", async () => {
    const wrapper = mount(Game24PlayView, { attachTo: document.body });
    await enterCorrectExpression(wrapper);
    expect(wrapper.get(".game-feedback").text()).toContain("正好等于 24");
    expect(wrapper.text()).toContain("得分 10");
    wrapper.unmount();

    const wrongWrapper = mount(Game24PlayView);
    for (const label of ["使用数字 1", "添加+号", "使用数字 2", "添加+号", "使用数字 3", "添加+号", "使用数字 4"]) {
      await wrongWrapper.get(`[aria-label="${label}"]`).trigger("click");
    }
    await buttonByText(wrongWrapper, "验证算式").trigger("click");
    expect(wrongWrapper.get(".game-feedback").text()).toContain("这次算得 10");
  });

  it("支持键盘输入并在练习结束时结算", async () => {
    const wrapper = mount(Game24PlayView, { attachTo: document.body });
    for (const key of ["1", "*", "2", "*", "3", "*", "4", "Enter"]) {
      window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      await wrapper.vm.$nextTick();
    }
    expect(wrapper.get(".game-feedback").text()).toContain("正好等于 24");
    vi.advanceTimersByTime(2000);
    await buttonByText(wrapper, "结束本次练习").trigger("click");
    expect(wrapper.text()).toContain("本轮任务完成");
    wrapper.unmount();
  });

  it("60 秒到时进入结果页", async () => {
    globalThis.__mathRouteQuery = { mode: "challenge", difficulty: "medium" };
    const wrapper = mount(Game24PlayView);
    await buttonByText(wrapper, "开始计时").trigger("click");
    await vi.advanceTimersByTimeAsync(60_500);
    expect(wrapper.text()).toContain("本轮任务完成");
    expect(wrapper.text()).toContain("正确率");
  });

  it("在简洁浮窗中调整玩法和难度", async () => {
    const wrapper = mount(Game24PlayView, { attachTo: document.body });
    await buttonByText(wrapper, "设置").trigger("click");
    expect(wrapper.get("[role='dialog']").text()).toContain("游戏设置");

    await buttonByText(wrapper, "60 秒挑战").trigger("click");
    await buttonByText(wrapper, "高手").trigger("click");
    await buttonByText(wrapper, "应用设置").trigger("click");

    expect(replace).toHaveBeenCalledWith({ name: "game24-play", query: { mode: "challenge", difficulty: "hard" } });
    expect(wrapper.find("[role='dialog']").exists()).toBe(false);
    expect(wrapper.text()).toContain("准备好连续解题了吗？");
    wrapper.unmount();
  });
});
