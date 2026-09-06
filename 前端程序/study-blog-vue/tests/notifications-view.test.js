// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NotificationsView from "../src/views/NotificationsView.vue";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  unreadNotificationCount,
} from "../src/services/notifications";

vi.mock("../src/services/notifications", () => ({
  listNotifications: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
  unreadNotificationCount: vi.fn(),
}));
const push = vi.fn();
const replace = vi.fn();
vi.mock("vue-router", () => ({ useRouter: () => ({ push, replace }) }));

const global = { stubs: { AppIcon: true } };
// 时间断言全部相对这个固定的「现在」，否则半夜跑测试会把「今天」滚成「昨天」。
const NOW = new Date("2026-08-27T10:00:00");

function notice(overrides = {}) {
  return {
    id: 1,
    kind: "homework_published",
    kind_label: "作业已发布",
    title: "第 3 课作业已发布",
    body: "请在本周日前提交。",
    link_url: "/tasks/homework",
    created_at: "2026-08-27T09:30:00",
    read_at: null,
    revoked_at: null,
    actions: [{ type: "open", label: "打开" }],
    ...overrides,
  };
}

function mountView() {
  const wrapper = mount(NotificationsView, { global });
  return flushPromises().then(() => wrapper);
}

describe("通知页面", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    unreadNotificationCount.mockResolvedValue({ count: 0 });
    listNotifications.mockResolvedValue({ items: [], total: 0 });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("先给骨架再渲染列表，按天分组并显示接口下发的类型文案", async () => {
    listNotifications.mockResolvedValue({
      items: [
        notice(),
        notice({ id: 2, title: "昨天的公告", created_at: "2026-08-26T21:00:00" }),
        notice({ id: 3, title: "更早的公告", created_at: "2026-06-01T09:00:00" }),
      ],
      total: 3,
    });
    const wrapper = mount(NotificationsView, { global });
    expect(wrapper.find(".notifications-skeleton").exists()).toBe(true);
    await flushPromises();

    expect(wrapper.findAll(".group-label").map((node) => node.text())).toEqual([
      "今天",
      "昨天",
      "6月1日",
    ]);
    expect(wrapper.find(".notification-kind").text()).toBe("作业已发布");
    expect(wrapper.findAll(".notification-time").map((node) => node.text())).toEqual([
      "30 分钟前",
      "21:00",
      "09:00",
    ]);
  });

  it("未读条目带未读样式，读掉一条后未读计数跟着减一", async () => {
    unreadNotificationCount.mockResolvedValue({ count: 2 });
    listNotifications.mockResolvedValue({
      items: [notice(), notice({ id: 2, read_at: "2026-08-27T08:00:00" })],
      total: 2,
    });
    markNotificationRead.mockResolvedValue({ ok: true });
    const wrapper = await mountView();

    expect(wrapper.findAll(".notification-item.unread")).toHaveLength(1);
    expect(wrapper.find(".tab-count").text()).toBe("2");
    expect(wrapper.find(".unread-pill").text()).toBe("2 条未读");

    await wrapper.find(".notification-item").trigger("click");
    await flushPromises();
    expect(markNotificationRead).toHaveBeenCalledWith(1);
    expect(replace).toHaveBeenCalledWith("/tasks/homework");
    expect(wrapper.find(".tab-count").text()).toBe("1");
    expect(wrapper.findAll(".notification-item.unread")).toHaveLength(0);
  });

  it("撤回的通知不跳转也不标已读", async () => {
    listNotifications.mockResolvedValue({
      items: [notice({ revoked_at: "2026-08-27T09:40:00", actions: [] })],
      total: 1,
    });
    const wrapper = await mountView();

    await wrapper.find(".notification-item").trigger("click");
    await flushPromises();
    expect(markNotificationRead).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("这条通知已撤回。");
  });

  it("两个页签的空状态说不同的话，未读空态能切回全部", async () => {
    const wrapper = await mountView();
    expect(wrapper.find(".state-title").text()).toBe("暂时没有通知");

    await wrapper.findAll(".notifications-tabs button")[1].trigger("click");
    await flushPromises();
    expect(listNotifications).toHaveBeenLastCalledWith({ tab: "unread", page: 1 });
    expect(wrapper.find(".state-title").text()).toBe("未读通知已清空");

    await wrapper.find(".notifications-empty .notifications-more").trigger("click");
    await flushPromises();
    expect(listNotifications).toHaveBeenLastCalledWith({ tab: "all", page: 1 });
  });

  it("在未读页签全部标为已读后重新拉列表，不把读过的条目留在原地", async () => {
    unreadNotificationCount.mockResolvedValue({ count: 1 });
    listNotifications.mockResolvedValue({ items: [notice()], total: 1 });
    markAllNotificationsRead.mockResolvedValue({ ok: true });
    const wrapper = await mountView();
    await wrapper.findAll(".notifications-tabs button")[1].trigger("click");
    await flushPromises();
    listNotifications.mockResolvedValue({ items: [], total: 0 });

    await wrapper.find(".notifications-heading button").trigger("click");
    await flushPromises();
    expect(listNotifications).toHaveBeenLastCalledWith({ tab: "unread", page: 1 });
    expect(wrapper.find(".state-title").text()).toBe("未读通知已清空");
  });

  it("确实没有未读时才锁「全部标为已读」，计数接口挂了不锁", async () => {
    const wrapper = await mountView();
    expect(wrapper.find(".notifications-heading button").attributes("disabled")).toBeDefined();

    unreadNotificationCount.mockRejectedValue(new Error("boom"));
    const degraded = await mountView();
    expect(degraded.find(".notifications-heading button").attributes("disabled")).toBeUndefined();
  });

  it("翻页把新一页接在后面，取完了给到底提示", async () => {
    listNotifications.mockResolvedValue({
      items: Array.from({ length: 5 }, (_, index) => notice({ id: index + 1 })),
      total: 6,
    });
    const wrapper = await mountView();
    expect(wrapper.find(".notifications-end").exists()).toBe(false);

    listNotifications.mockResolvedValue({ items: [notice({ id: 6 })], total: 6 });
    await wrapper.find(".notifications-list .notifications-more").trigger("click");
    await flushPromises();
    expect(listNotifications).toHaveBeenLastCalledWith({ tab: "all", page: 2 });
    expect(wrapper.findAll(".notification-item")).toHaveLength(6);
    expect(wrapper.find(".notifications-end").text()).toBe("已经到底了");
  });
});
