// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import HelpMessageScroller from "../src/components/help/HelpMessageScroller.vue";

describe("HelpMessageScroller", () => {
  it("loads older messages at the top and compensates the height delta", async () => {
    const loadEarlier = vi.fn(async () => {});
    const wrapper = mount(HelpMessageScroller, {
      props: { messages: [{ id: 2, body: "新消息" }], hasMore: true, loadEarlier },
    });
    const viewport = wrapper.get(".help-message-scroller").element;
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, get: () => (loadEarlier.mock.calls.length ? 340 : 200) },
      scrollTop: { configurable: true, writable: true, value: 20 },
      clientHeight: { configurable: true, value: 180 },
    });
    await wrapper.get(".help-load-earlier").trigger("click");
    await flushPromises();
    expect(loadEarlier).toHaveBeenCalledOnce();
    expect(viewport.scrollTop).toBe(160);
  });

  it("states clearly when there is no further history", () => {
    const wrapper = mount(HelpMessageScroller, {
      props: { messages: [{ id: 1, body: "第一条" }] },
    });
    expect(wrapper.text()).toContain("没有更多了");
  });
});
