// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const helpApi = vi.hoisted(() => ({
  listHelpChatLines: vi.fn(),
  getHelpChatLine: vi.fn(),
  createHelpRequest: vi.fn(),
  subscribeToHelpChatEvents: vi.fn(),
}));

vi.mock("../src/services/help", async (importOriginal) => ({
  ...(await importOriginal()),
  ...helpApi,
  idempotencyKey: () => "test-key",
}));

import HelpWidget from "../src/components/help/HelpWidget.vue";
import { Select } from "../src/components/ui/select";

describe("HelpWidget", () => {
  beforeEach(() => {
    helpApi.listHelpChatLines.mockReset();
    helpApi.getHelpChatLine.mockReset();
    helpApi.createHelpRequest.mockReset();
    helpApi.subscribeToHelpChatEvents.mockReset();
    helpApi.subscribeToHelpChatEvents.mockImplementation((onChange) => {
      helpApi.onRealtimeChange = onChange;
      const unsubscribe = vi.fn();
      unsubscribe.send = vi.fn();
      return unsubscribe;
    });
    helpApi.listHelpChatLines.mockResolvedValue({
      items: [{ id: 5, class_id: 8, class_name: "周六编程班" }],
      available_classes: [
        { class_id: 8, class_name: "周六编程班", course_id: 3, course_title: "Python 入门" },
      ],
    });
    helpApi.getHelpChatLine.mockResolvedValue({
      id: 5,
      messages: [{ id: 1, sender_type: "admin", body: "先检查循环条件。" }],
    });
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("opens directly into the conversation without a problem-type form", async () => {
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(document.body.textContent).toContain("先检查循环条件。");
    expect(document.body.textContent).not.toContain("问题类型");
    expect(document.body.querySelector("textarea")?.getAttribute("placeholder")).toBe(
      "告诉老师你卡在哪里……",
    );
    wrapper.unmount();
  });

  it("shows unread replies on the launcher before the chat is opened", async () => {
    helpApi.listHelpChatLines.mockResolvedValue({
      items: [{ id: 5, class_id: 8, class_name: "周六编程班", unread_count: 2 }],
      available_classes: [
        { class_id: 8, class_name: "周六编程班", course_id: 3, course_title: "Python 入门" },
      ],
    });
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await flushPromises();

    expect(wrapper.get("button").text()).toContain("2");
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    wrapper.unmount();
  });

  it("updates the launcher unread count from a realtime event while closed", async () => {
    helpApi.listHelpChatLines
      .mockResolvedValueOnce({
        items: [{ id: 5, class_id: 8, class_name: "周六编程班", unread_count: 0 }],
        available_classes: [{ class_id: 8, class_name: "周六编程班", course_id: 3 }],
      })
      .mockResolvedValueOnce({
        items: [{ id: 5, class_id: 8, class_name: "周六编程班", unread_count: 1 }],
        available_classes: [{ class_id: 8, class_name: "周六编程班", course_id: 3 }],
      });
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await flushPromises();

    helpApi.onRealtimeChange({ type: "help_chat_line_changed", event: "admin_message", chat_line_id: 5 });
    await new Promise((resolve) => setTimeout(resolve, 100));
    await flushPromises();

    expect(wrapper.get("button").text()).toContain("1");
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    wrapper.unmount();
  });

  it("uses a non-modal floating chat window with a linked description", async () => {
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await wrapper.get("button").trigger("click");
    await flushPromises();

    const dialog = document.body.querySelector('[role="dialog"]');
    const descriptionId = dialog?.getAttribute("aria-describedby");
    expect(dialog?.getAttribute("aria-modal")).toBe("false");
    expect(descriptionId).toBe("help-chat-description");
    expect(document.getElementById(descriptionId)?.textContent).toContain(
      "直接说哪里卡住了，老师看到后会在这里回复。",
    );

    wrapper.unmount();
  });

  it("sends on Enter with the selected class and supplied context", async () => {
    helpApi.createHelpRequest.mockResolvedValue({ chat_line_id: 5 });
    const wrapper = mount(HelpWidget, {
      attachTo: document.body,
      props: { context: { context_type: "block", context_id: 42 } },
    });
    await wrapper.get("button").trigger("click");
    await flushPromises();
    const textarea = document.body.querySelector("textarea");
    textarea.value = "这一步为什么不通过？";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await flushPromises();
    textarea.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flushPromises();

    expect(helpApi.createHelpRequest).toHaveBeenCalledWith(
      {
        class_id: 8,
        body: "这一步为什么不通过？",
        context_type: "block",
        context_id: 42,
      },
      { requestKey: "test-key" },
    );
    wrapper.unmount();
  });

  it("keeps the draft and exposes retry after a failed send", async () => {
    helpApi.createHelpRequest.mockRejectedValue(new Error("网络断开，请重试。"));
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await wrapper.get("button").trigger("click");
    await flushPromises();
    const textarea = document.body.querySelector("textarea");
    textarea.value = "请帮我看看";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await flushPromises();
    textarea.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flushPromises();

    expect(document.body.textContent).toContain("网络断开，请重试。");
    expect(document.body.textContent).toContain("重试");
    expect(textarea.value).toBe("请帮我看看");
    wrapper.unmount();
  });

  it("lets a first-time student send through the only available class", async () => {
    helpApi.listHelpChatLines.mockResolvedValue({
      items: [],
      available_classes: [
        { class_id: 12, class_name: "周日班", course_id: 4, course_title: "图形化编程" },
      ],
    });
    helpApi.createHelpRequest.mockResolvedValue({ chat_line_id: 22 });
    helpApi.getHelpChatLine.mockResolvedValue({ id: 22, requests: [] });
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await wrapper.get("button").trigger("click");
    await flushPromises();

    const textarea = document.body.querySelector("textarea");
    expect(textarea).not.toBeNull();
    textarea.value = "第一次提问";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await flushPromises();
    textarea.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flushPromises();

    expect(helpApi.createHelpRequest).toHaveBeenCalledWith(
      { class_id: 12, body: "第一次提问", context_type: "general" },
      { requestKey: "test-key" },
    );
    expect(helpApi.getHelpChatLine).toHaveBeenCalledWith(22);
    wrapper.unmount();
  });

  it("shows the unavailable state only when there is no active class", async () => {
    helpApi.listHelpChatLines.mockResolvedValue({ items: [], available_classes: [] });
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(document.body.textContent).toContain("还没有可用的班级答疑");
    expect(document.body.querySelector("textarea")).toBeNull();
    wrapper.unmount();
  });

  it("requires an explicit class choice when several active classes are available", async () => {
    helpApi.listHelpChatLines.mockResolvedValue({
      items: [],
      available_classes: [
        { class_id: 12, class_name: "周六班", course_id: 4, course_title: "Python" },
        { class_id: 13, class_name: "周日班", course_id: 5, course_title: "Scratch" },
      ],
    });
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(document.body.textContent).toContain("先选择班级");
    expect(document.body.querySelector("textarea")).toBeNull();

    wrapper.findComponent(Select).vm.$emit("update:modelValue", 13);
    await flushPromises();

    expect(document.body.querySelector("textarea")).not.toBeNull();
    wrapper.unmount();
  });

  it("prefers the only active class over an inactive historical line", async () => {
    helpApi.listHelpChatLines.mockResolvedValue({
      items: [{ id: 5, class_id: 8, class_name: "已结束班级" }],
      available_classes: [
        { class_id: 13, class_name: "当前班级", course_id: 5, course_title: "Scratch" },
      ],
    });
    helpApi.createHelpRequest.mockResolvedValue({ chat_line_id: 23 });
    helpApi.getHelpChatLine.mockResolvedValue({ id: 23, requests: [] });
    const wrapper = mount(HelpWidget, { attachTo: document.body });
    await wrapper.get("button").trigger("click");
    await flushPromises();

    const textarea = document.body.querySelector("textarea");
    expect(textarea).not.toBeNull();
    textarea.value = "发给现在的老师";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await flushPromises();
    textarea.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await flushPromises();

    expect(helpApi.createHelpRequest).toHaveBeenCalledWith(
      { class_id: 13, body: "发给现在的老师", context_type: "general" },
      { requestKey: "test-key" },
    );
    wrapper.unmount();
  });
});
