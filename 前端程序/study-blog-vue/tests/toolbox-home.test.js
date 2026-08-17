// @vitest-environment jsdom
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import ToolboxHome from "../src/views/ToolboxHome.vue";

describe("工具箱独立应用入口", () => {
  afterEach(() => vi.restoreAllMocks());

  it("在新标签页打开数学星球", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const wrapper = mount(ToolboxHome);
    const mathCard = wrapper.findAll(".tool-card").find((card) => card.text().includes("数学星球"));

    expect(mathCard).toBeTruthy();
    await mathCard.trigger("click");

    expect(open).toHaveBeenCalledOnce();
    expect(open).toHaveBeenCalledWith("/math-studio/", "_blank");
  });
});
