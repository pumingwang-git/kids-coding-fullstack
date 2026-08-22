// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const routeMock = vi.hoisted(() => ({
  name: "area-mistake-review",
  path: "/areas/programmer/tasks/mistakes/review",
  fullPath: "/areas/programmer/tasks/mistakes/review",
  params: { areaKey: "programmer" },
  query: {},
  meta: { shell: "learning", requiresAuth: true },
}));

vi.mock("vue-router", () => ({
  useRoute: () => routeMock,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  RouterView: { template: "<div class='router-view-stub' />" },
  RouterLink: {
    props: ["to"],
    template: '<a class="router-link" :data-to="JSON.stringify(to)"><slot /></a>',
  },
}));

vi.mock("../src/services/auth", () => ({
  getCsrf: vi.fn().mockResolvedValue(null),
  logout: vi.fn().mockResolvedValue(null),
  request: vi.fn().mockResolvedValue({ items: [] }),
}));

vi.mock("../src/stores/session", () => ({
  ensureSession: vi.fn().mockResolvedValue(null),
  session: { user: { username: "同学" }, loaded: true },
}));

vi.mock("../src/composables/useSessionKeepalive", () => ({
  useSessionKeepalive: vi.fn(),
}));

import App from "../src/App.vue";
import { learningCatalog } from "../src/stores/learningCatalog";

const PROGRAMMER_AREA = {
  key: "programmer",
  name: "程序员专区",
  theme_key: "programmer",
  // 题库和工具箱现在由后端种子下发到每个专区（原先是前端硬编码兜底），
  // fixture 与 /api/learning-areas 的真实返回保持一致。
  modules: [
    { module_key: "overview", label: "概览", status: "available" },
    { module_key: "paths", label: "学习路线", status: "available" },
    { module_key: "courses", label: "课程", status: "available" },
    { module_key: "projects", label: "实战项目", status: "available" },
    { module_key: "question-bank", label: "题库", status: "available" },
    { module_key: "toolbox", label: "工具箱", status: "available" },
  ],
};

beforeEach(() => {
  learningCatalog.areas = [PROGRAMMER_AREA];
  learningCatalog.loaded = true;
  learningCatalog.loading = null;
});

describe("学生端侧边栏", () => {
  it.each([
    ["area-mistake-review", "复习任务", "/areas/programmer/tasks/mistakes/review"],
    ["area-mistake-stats", "复习统计", "/areas/programmer/tasks/mistakes/stats"],
  ])("%s 页面展开题库并正确标记当前入口", async (name, label, target) => {
    routeMock.name = name;
    routeMock.path = target;
    routeMock.fullPath = target;
    const wrapper = mount(App);
    await flushPromises();

    const questionRow = wrapper.findAll(".nav-row").find((row) => row.text().includes("题库"));
    expect(questionRow?.find("a").classes()).toContain("nav-current");

    const subnav = wrapper.find('.kids-subnav[aria-label="题库"]');
    expect(subnav.exists()).toBe(true);
    expect(subnav.findAll("a").map((link) => link.text())).toEqual([
      "我的错题",
      "复习任务",
      "复习统计",
    ]);
    const current = subnav.findAll("a").find((link) => link.text().includes(label));
    expect(JSON.parse(current.attributes("data-to"))).toBe(target);
    expect(current.classes()).toContain("subnav-current");
  });

  it("设置入口保留当前专区，避免跳回少儿编程侧栏", async () => {
    routeMock.name = "area-mistake-review";
    const wrapper = mount(App);
    await flushPromises();

    const settings = wrapper
      .findAll(".kids-sidebar-foot a")
      .find((link) => link.text().includes("设置"));
    expect(JSON.parse(settings.attributes("data-to"))).toEqual({
      path: "/settings",
      query: { area: "programmer" },
    });
  });
});
