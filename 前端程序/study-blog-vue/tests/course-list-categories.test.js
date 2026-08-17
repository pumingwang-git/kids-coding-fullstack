// @vitest-environment jsdom
// CourseList.vue 分类筛选护栏：chips 渲染、URL query 保持选择、按分类请求。
// 覆盖：无参数默认全部 / URL 带 category 选中并请求 / 点击分类写 URL / 点全部清参数。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const routeMock = vi.hoisted(() => ({ query: {} }));
const replaceMock = vi.hoisted(() => vi.fn());
vi.mock("vue-router", () => ({
  useRoute: () => routeMock,
  useRouter: () => ({ replace: replaceMock }),
  RouterLink: { template: "<a><slot /></a>" },
}));

const requestMock = vi.hoisted(() => vi.fn());
vi.mock("../src/services/auth", () => ({ request: requestMock }));

import CourseList from "../src/views/CourseList.vue";

const CATS = {
  items: [
    { id: 5, name: "编程基础", course_count: 2 },
    { id: 7, name: "竞赛课程", course_count: 1 },
  ],
};

function coursesPayload() {
  return {
    items: [
      {
        id: 1, title: "CSP-J 冲刺营", subtitle: "", category_name: "编程基础",
        cover_url: null, difficulty: "beginner", section_count: 2,
        lesson_count: 4, total_minutes: 90,
      },
    ],
  };
}

beforeEach(() => {
  routeMock.query = {};
  replaceMock.mockReset();
  requestMock.mockReset();
  requestMock.mockImplementation((url) =>
    url.startsWith("/api/course-categories")
      ? Promise.resolve(CATS)
      : Promise.resolve(coursesPayload()),
  );
});

const courseReq = () => requestMock.mock.calls.filter(([url]) => url.startsWith("/api/courses"));

describe("CourseList 分类筛选", () => {
  it("无 URL 参数 → 请求不带 category_id，「全部」默认选中", async () => {
    const wrapper = mount(CourseList);
    await flushPromises();

    expect(courseReq()[0][0]).toContain("page=1&page_size=24");
    expect(courseReq()[0][0]).not.toContain("category_id");
    expect(wrapper.findAll(".category-bar .chip").length).toBe(3); // 全部 + 2 分类
    expect(wrapper.find(".category-bar .chip.active").text()).toContain("全部");
  });

  it("URL 带 category=5 → 选中该分类且请求带 category_id=5", async () => {
    routeMock.query = { category: "5" };
    const wrapper = mount(CourseList);
    await flushPromises();

    expect(courseReq()[0][0]).toContain("category_id=5");
    const chips = wrapper.findAll(".category-bar .chip");
    expect(chips[1].classes()).toContain("active");
    expect(chips[1].text()).toContain("编程基础");
  });

  it("点击分类 chip → URL 写入 category 并带 category_id 重新请求", async () => {
    const wrapper = mount(CourseList);
    await flushPromises();

    const chips = wrapper.findAll(".category-bar .chip");
    await chips[2].trigger("click"); // 竞赛课程 id=7
    await flushPromises();

    expect(replaceMock).toHaveBeenCalledWith({ query: { category: "7" } });
    expect(courseReq().at(-1)[0]).toContain("category_id=7");
  });

  it("点击「全部」→ 清掉 URL 参数并请求不带 category_id", async () => {
    routeMock.query = { category: "5" };
    const wrapper = mount(CourseList);
    await flushPromises();

    await wrapper.findAll(".category-bar .chip")[0].trigger("click");
    await flushPromises();

    expect(replaceMock).toHaveBeenCalledWith({ query: {} });
    expect(courseReq().at(-1)[0]).not.toContain("category_id");
  });

  it("分类超过八个时收敛为下拉选择，仍能按分类请求", async () => {
    requestMock.mockImplementation((url) =>
      url.startsWith("/api/course-categories")
        ? Promise.resolve({ items: Array.from({ length: 9 }, (_, index) => ({ id: index + 1, name: `分类 ${index + 1}`, course_count: 1 })) })
        : Promise.resolve(coursesPayload()),
    );
    const wrapper = mount(CourseList);
    await flushPromises();

    expect(wrapper.find(".category-bar").exists()).toBe(false);
    const select = wrapper.find(".category-select select");
    expect(select.exists()).toBe(true);
    await select.setValue("9");
    expect(courseReq().at(-1)[0]).toContain("category_id=9");
  });
});
