import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveSession } from "../src/platform/session";

describe("数学星球会话解析", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("网络失败时允许已登录学生离线继续", async () => {
    localStorage.setItem("math-studio:last-user", JSON.stringify({ id: 9, username: "小林" }));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const session = await resolveSession();
    expect(session).toEqual({ user: { id: 9, username: "小林" }, reason: "offline" });
  });

  it("明确未登录时要求跳转登录页", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401, ok: false }));
    const session = await resolveSession();
    expect(session).toEqual({ user: null, reason: "unauthenticated" });
  });
});
