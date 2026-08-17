// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const routeMock = vi.hoisted(() => ({ query: {}, params: { areaKey: "kids" } }));
const replaceMock = vi.hoisted(() => vi.fn());
vi.mock("vue-router", () => ({
  useRoute: () => routeMock,
  useRouter: () => ({ replace: replaceMock }),
  RouterLink: { template: "<a><slot /></a>" },
}));

const requestMock = vi.hoisted(() => vi.fn());
vi.mock("../src/services/auth", () => ({ request: requestMock }));

import KidsCourseList from "../src/views/KidsCourseList.vue";

beforeEach(() => {
  routeMock.query = {};
  routeMock.params = { areaKey: "kids" };
  replaceMock.mockReset();
  requestMock.mockReset();
  requestMock.mockImplementation((url) => {
    if (url.startsWith("/api/learning-areas/")) return Promise.resolve({ key: "kids", name: "少儿编程" });
    if (url.startsWith("/api/course-types")) return Promise.resolve({ items: [
      { key: "systematic", name: "系统课程", description: "按稳定顺序学习" },
      { key: "special", name: "专题课程", description: "集中学习一个主题" },
    ] });
    if (url.startsWith("/api/course-taxonomy")) return Promise.resolve({ items: [
      { id: 1, name: "图形化编程", course_count: 1, children: [
        { id: 2, name: "Scratch", course_count: 1, children: [] },
      ] },
    ] });
    if (url.startsWith("/api/course-tags")) return Promise.resolve({ items: [
      { id: 11, name: "游戏创作", course_count: 1 },
    ] });
    return Promise.resolve({ items: [], total: 0, page: 1 });
  });
});

describe("少儿专区课程筛选", () => {
  it("默认从目录接口加载少儿专区，并请求第一个可用课程类型", async () => {
    mount(KidsCourseList);
    await flushPromises();

    const urls = requestMock.mock.calls.map(([url]) => url);
    expect(urls).toContain("/api/learning-areas/kids");
    expect(urls.some((url) => url.startsWith("/api/course-taxonomy?") && url.includes("area_key=kids"))).toBe(true);
    expect(urls.some((url) => url.startsWith("/api/courses?") && url.includes("area_key=kids") && url.includes("course_kind=systematic"))).toBe(true);
  });

  it("切换专题课会更新 URL，并重新加载专题分类和课程", async () => {
    const wrapper = mount(KidsCourseList);
    await flushPromises();
    await wrapper.findAll(".course-kind-tabs button")[1].trigger("click");
    await flushPromises();

    expect(replaceMock).toHaveBeenCalledWith({ query: { kind: "special" } });
    const latestCourse = requestMock.mock.calls.map(([url]) => url).filter((url) => url.startsWith("/api/courses?")).at(-1);
    expect(latestCourse).toContain("course_kind=special");
  });

  it("选择方向后才显示课程特色，并按方向重新请求可用标签", async () => {
    const wrapper = mount(KidsCourseList);
    await flushPromises();
    expect(wrapper.find(".tag-bar").exists()).toBe(false);

    await wrapper.findAll(".direction-option")[1].trigger("click");
    await flushPromises();

    expect(wrapper.find(".tag-bar").exists()).toBe(true);
    const latestTagRequest = requestMock.mock.calls.map(([url]) => url)
      .filter((url) => url.startsWith("/api/course-tags")).at(-1);
    expect(latestTagRequest).toContain("course_kind=systematic");
    expect(latestTagRequest).toContain("category_id=1");
  });
});
