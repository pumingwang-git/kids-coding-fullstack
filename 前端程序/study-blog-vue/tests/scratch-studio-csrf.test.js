// @vitest-environment jsdom
// Studio API 客户端的 CSRF 分流护栏。
//
// 测试文件放在 study-blog-vue 而不是 scratch-studio：后者是纯 webpack 子应用，没有
// 测试运行器，为一个模块单独装一套不划算；而这里的 vitest 已经在跨包引用
// public/admin 下的模块了（admin-scratch.test.js），再多一个相对路径不增加复杂度。
//
// 守的是一个真实踩过的 bug：早先客户端对所有写请求一律取 admin_csrf_token，学生
// 保存作品于是把管理端令牌发给学生端接口，后端 require_csrf 比对失败 → 403
// 「CSRF 校验失败。」。两套令牌各校验各的 Cookie，必须按 URL 选。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  saveProjectSb3,
  submitProject,
  uploadChallengeProject,
  fetchLessonBlockContext,
} from "../../scratch-studio/src/api/client.js";

let calls;

function setCookies(pairs) {
  // jsdom 的 document.cookie 是累加的，逐条写
  for (const [k, v] of Object.entries(pairs)) document.cookie = `${k}=${v}`;
}

function clearCookies() {
  for (const chunk of document.cookie.split(";")) {
    const name = chunk.split("=")[0].trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  }
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    clone() {
      return this;
    },
  };
}

beforeEach(() => {
  calls = [];
  clearCookies();
  vi.stubGlobal("fetch", async (url, options = {}) => {
    calls.push({ url, method: options.method || "GET", headers: options.headers || {} });
    // 令牌签发端点：模拟后端下发对应 Cookie
    if (url === "/api/auth/csrf") {
      setCookies({ csrf_token: "STUDENT-TOKEN" });
      return jsonResponse({ message: "ok" });
    }
    if (url === "/api/admin/csrf") {
      setCookies({ admin_csrf_token: "ADMIN-TOKEN" });
      return jsonResponse({ message: "ok" });
    }
    return jsonResponse({ ok: true });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearCookies();
});

const lastWrite = () => calls.filter((c) => c.method !== "GET")[0];

describe("Studio CSRF 令牌按端点分流", () => {
  it("学生保存作品带的是 csrf_token，不是管理端令牌", async () => {
    setCookies({ csrf_token: "STUDENT-TOKEN", admin_csrf_token: "ADMIN-TOKEN" });
    await saveProjectSb3(7, new Blob(["x"]), "manual", 3);
    const write = lastWrite();
    expect(write.url).toBe("/api/scratch/projects/7");
    expect(write.headers["X-CSRF-Token"]).toBe("STUDENT-TOKEN");
  });

  it("学生提交同理", async () => {
    setCookies({ csrf_token: "STUDENT-TOKEN", admin_csrf_token: "ADMIN-TOKEN" });
    await submitProject(34);
    expect(lastWrite().headers["X-CSRF-Token"]).toBe("STUDENT-TOKEN");
  });

  it("教研写回初始/示范项目带的是 admin_csrf_token", async () => {
    setCookies({ csrf_token: "STUDENT-TOKEN", admin_csrf_token: "ADMIN-TOKEN" });
    await uploadChallengeProject(
      "/api/admin/scratch/challenges/1/demo-project",
      new Blob(["x"]),
      "demo.sb3",
    );
    const write = lastWrite();
    expect(write.url).toBe("/api/admin/scratch/challenges/1/demo-project");
    expect(write.headers["X-CSRF-Token"]).toBe("ADMIN-TOKEN");
  });

  it("没有 Cookie 时各自去自己的签发端点取，不会串台", async () => {
    await saveProjectSb3(7, new Blob(["x"]), "manual", 3);
    expect(calls.map((c) => c.url)).toEqual(["/api/auth/csrf", "/api/scratch/projects/7"]);

    calls = [];
    clearCookies();
    await uploadChallengeProject("/api/admin/scratch/challenges/1/starter-project", new Blob(["x"]));
    expect(calls.map((c) => c.url)).toEqual([
      "/api/admin/csrf",
      "/api/admin/scratch/challenges/1/starter-project",
    ]);
  });

  it("令牌过期（403 CSRF 校验失败）时重取一次再试", async () => {
    // Studio 是长时间开着的页面，会话轮换后 Cookie 里的令牌可能已经作废。
    setCookies({ csrf_token: "STALE" });
    let attempt = 0;
    vi.stubGlobal("fetch", async (url, options = {}) => {
      calls.push({ url, method: options.method || "GET", headers: options.headers || {} });
      if (url === "/api/auth/csrf") {
        setCookies({ csrf_token: "FRESH" });
        return jsonResponse({ message: "ok" });
      }
      attempt += 1;
      if (attempt === 1) return jsonResponse({ detail: "CSRF 校验失败。" }, 403);
      return jsonResponse({ project_id: 7, unchanged: false });
    });

    const result = await saveProjectSb3(7, new Blob(["x"]), "manual", 3);
    expect(result).toEqual({ project_id: 7, unchanged: false });
    const writes = calls.filter((c) => c.method === "PUT");
    expect(writes).toHaveLength(2);
    expect(writes[0].headers["X-CSRF-Token"]).toBe("STALE");
    expect(writes[1].headers["X-CSRF-Token"]).toBe("FRESH");
  });

  it("非 CSRF 的 403 不重试，直接抛出服务端文案", async () => {
    setCookies({ csrf_token: "STUDENT-TOKEN" });
    vi.stubGlobal("fetch", async (url, options = {}) => {
      calls.push({ url, method: options.method || "GET", headers: options.headers || {} });
      return jsonResponse({ detail: "该内容尚未对你开放。" }, 403);
    });
    await expect(submitProject(34)).rejects.toThrow("该内容尚未对你开放。");
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
  });

  it("读请求不带令牌，也不会去签发", async () => {
    await fetchLessonBlockContext(34);
    expect(calls).toHaveLength(1);
    expect(calls[0].headers["X-CSRF-Token"]).toBeUndefined();
  });
});
