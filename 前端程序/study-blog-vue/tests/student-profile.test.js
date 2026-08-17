// @vitest-environment jsdom
// 学生个人资料页（文档 28 P2 验收第 6 条）：资料渲染、加载失败态、签名更新、头像上传、
// 设置页跳转。request 全部 mock，不连后端。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const routeMock = vi.hoisted(() => ({ query: {}, meta: {} }));
vi.mock("vue-router", () => ({
  useRoute: () => routeMock,
  RouterLink: {
    props: ["to"],
    template: '<a class="router-link" :data-to="JSON.stringify(to)"><slot /></a>',
  },
}));

const profileApi = vi.hoisted(() => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  uploadAvatar: vi.fn(),
}));
vi.mock("../src/services/auth", () => ({
  ...profileApi,
  getCurrentUser: vi.fn().mockResolvedValue(null),
}));
vi.mock("../src/stores/session", () => ({
  session: { user: null, loaded: true },
}));

import StudentProfile from "../src/views/StudentProfile.vue";
import SettingsView from "../src/views/SettingsView.vue";

const PROFILE = {
  user: {
    id: 42,
    username: "testlearner",
    email: "test@example.com",
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
  },
  avatar_url: "",
  learning_signature: "坚持就是胜利",
  overview: { total_answered: 10, total: 3, due: 2, mastered: 1, recent_review_accuracy: 66.7 },
};

beforeEach(() => {
  routeMock.query = {};
  routeMock.meta = {};
  profileApi.getProfile.mockReset();
  profileApi.updateProfile.mockReset();
  profileApi.uploadAvatar.mockReset();
  profileApi.getProfile.mockResolvedValue(PROFILE);
});

describe("StudentProfile 资料渲染", () => {
  it("渲染用户名、账号 ID 与学习概览统计，入口链接齐全", async () => {
    const wrapper = mount(StudentProfile);
    await flushPromises();

    expect(wrapper.text()).toContain("testlearner");
    expect(wrapper.text()).toContain("账号 ID 42");
    expect(wrapper.text()).toContain("test@example.com");
    expect(wrapper.text()).toContain("坚持就是胜利");
    // 统计区四个数字（成功态才出现，不露空格子）
    expect(wrapper.text()).toContain("10");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("66.7%");
    // 入口：错题本 + 工具箱 + 设置
    const targets = wrapper.findAll(".router-link").map((l) => {
      const to = JSON.parse(l.attributes("data-to"));
      return typeof to === "string" ? to : to?.path;
    });
    expect(targets).toContain("/areas/kids/tasks/mistakes");
    expect(targets).toContain("/areas/kids/toolbox");
    const settings = wrapper
      .findAll(".router-link")
      .map((link) => JSON.parse(link.attributes("data-to")))
      .find((to) => to?.path === "/settings");
    expect(settings).toEqual({ path: "/settings", query: { area: "kids" } });
  });

  it("加载失败时显示错误且不渲染统计区（不露空格子）", async () => {
    profileApi.getProfile.mockRejectedValue(new Error("网络出错了"));
    const wrapper = mount(StudentProfile);
    await flushPromises();

    expect(wrapper.text()).toContain("网络出错了");
    expect(wrapper.find(".profile-summary").exists()).toBe(false);
  });
});

describe("StudentProfile 资料编辑", () => {
  it("保存学习签名调用 updateProfile 并回显新值", async () => {
    profileApi.updateProfile.mockResolvedValue({ avatar_url: "", learning_signature: "新签名" });
    const wrapper = mount(StudentProfile);
    await flushPromises();

    await wrapper.find(".signature-edit").trigger("click");
    await wrapper.find("textarea").setValue("新签名");
    await wrapper.find(".signature-actions .button-primary").trigger("click");
    await flushPromises();

    expect(profileApi.updateProfile).toHaveBeenCalledWith({ learning_signature: "新签名" });
    expect(wrapper.text()).toContain("新签名");
  });

  it("上传头像：非图片文件被前端拦截，不上传", async () => {
    const wrapper = mount(StudentProfile);
    await flushPromises();

    const file = new File(["not image"], "a.txt", { type: "text/plain" });
    Object.defineProperty(wrapper.find('input[type="file"]').element, "files", {
      value: [file],
    });
    await wrapper.find('input[type="file"]').trigger("change");
    await flushPromises();

    expect(profileApi.uploadAvatar).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("请选择图片文件。");
  });

  it("上传头像：合法图片调用 uploadAvatar 并回显新地址", async () => {
    profileApi.uploadAvatar.mockResolvedValue({ avatar_url: "/avatars/ab/abc.png" });
    const wrapper = mount(StudentProfile);
    await flushPromises();

    const file = new File([new Uint8Array([137, 80, 78, 71])], "a.png", { type: "image/png" });
    Object.defineProperty(wrapper.find('input[type="file"]').element, "files", {
      value: [file],
    });
    await wrapper.find('input[type="file"]').trigger("change");
    await flushPromises();

    expect(profileApi.uploadAvatar).toHaveBeenCalledWith(file);
    expect(wrapper.find(".profile-avatar img").attributes("src")).toBe("/avatars/ab/abc.png");
  });
});

describe("SettingsView 设置跳转", () => {
  it("第一项是「账号与安全」，跳转既有 /security 并保留当前专区", async () => {
    routeMock.query = { area: "programmer" };
    const wrapper = mount(SettingsView);
    const item = wrapper.find(".settings-item");
    expect(item.text()).toContain("账号与安全");
    expect(JSON.parse(item.attributes("data-to"))).toEqual({
      path: "/security",
      query: { area: "programmer" },
    });
  });
});
