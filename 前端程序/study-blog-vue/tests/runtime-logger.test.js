import { beforeEach, describe, expect, it, vi } from "vitest";

import { beginRequest, completeRequest, failRequest } from "../src/services/runtimeLogger";

describe("runtimeLogger", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("记录请求时只保留 pathname，不泄漏 query 参数", () => {
    const debug = vi.spyOn(console, "debug").mockImplementation(() => {});
    const context = beginRequest("/api/auth/me?access_token=should-not-appear");
    completeRequest(context, "/api/auth/me?access_token=should-not-appear", 200);

    expect(debug).toHaveBeenCalled();
    const output = JSON.stringify(debug.mock.calls);
    expect(output).toContain("/api/auth/me");
    expect(output).not.toContain("access_token");
    expect(output).not.toContain("should-not-appear");
  });

  it("失败事件保留 request_id、状态码和错误码", () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});
    const context = beginRequest("/api/exam/abc");
    failRequest(context, "/api/exam/abc?token=hidden", { status: 409, code: "judge_pending" });

    const output = JSON.stringify(errorLog.mock.calls);
    expect(output).toContain(context.id);
    expect(output).toContain("judge_pending");
    expect(output).not.toContain("hidden");
  });
});
