// @vitest-environment jsdom
// Scratch 自由作品 API 客户端的请求形状护栏。
//
// 与 scratch-studio-csrf.test.js 同构：守的是「写请求必须带对 CSRF 令牌、
// 路径与方法不能拼错」这类只在联调时才会暴露的错。自由作品走学生端令牌
// （csrf_token），与管理端（admin_csrf_token）分流，与闯关保存同一套。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createWork,
  fetchMyWorks,
  fetchWorkContext,
  saveWorkSb3,
  updateWork,
  deleteWork,
  shareWork,
  fetchGallery,
  fetchGalleryWork,
} from "../../scratch-studio/src/api/client.js";

let calls;

function setCookies(pairs) {
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
    calls.push({ url, method: options.method || "GET", headers: options.headers || {}, body: options.body });
    if (url === "/api/auth/csrf") {
      setCookies({ csrf_token: "STUDENT-TOKEN" });
      return jsonResponse({ message: "ok" });
    }
    if (url === "/api/admin/csrf") {
      setCookies({ admin_csrf_token: "ADMIN-TOKEN" });
      return jsonResponse({ message: "ok" });
    }
    if (String(url).includes("works")) {
      return jsonResponse({ id: 7, title: "我的作品", items: [], already_shared: false });
    }
    return jsonResponse({ ok: true });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("自由作品 API 客户端", () => {
  it("createWork 发 POST /api/scratch/works，带学生端 CSRF 头", async () => {
    await createWork("小猫散步");
    const call = calls.find((c) => c.url === "/api/scratch/works");
    expect(call).toBeTruthy();
    expect(call.method).toBe("POST");
    expect(call.headers["X-CSRF-Token"]).toBe("STUDENT-TOKEN");
  });

  it("fetchMyWorks / fetchWorkContext 走 GET，不带 CSRF 头", async () => {
    await fetchMyWorks();
    await fetchWorkContext(7);
    expect(calls.find((c) => c.url === "/api/scratch/works").method).toBe("GET");
    expect(calls.find((c) => c.url === "/api/scratch/works/7").method).toBe("GET");
    for (const c of calls) expect(c.headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("saveWorkSb3 发 PUT multipart 到 /api/scratch/works/{id}", async () => {
    const blob = new Blob(["sb3-bytes"], { type: "application/zip" });
    await saveWorkSb3(7, blob, "manual");
    const call = calls.find((c) => c.url === "/api/scratch/works/7");
    expect(call.method).toBe("PUT");
    expect(call.headers["X-CSRF-Token"]).toBe("STUDENT-TOKEN");
    // FormData 由 fetch 自己序列化，断言它被作为 body 传了即可
    expect(call.body).toBeInstanceOf(FormData);
  });

  it("updateWork 发 PATCH JSON body（标题/公开开关）", async () => {
    await updateWork(7, { title: "新名字", is_public: false });
    const call = calls.find((c) => c.url === "/api/scratch/works/7");
    expect(call.method).toBe("PATCH");
    expect(call.headers["X-CSRF-Token"]).toBe("STUDENT-TOKEN");
    expect(JSON.parse(call.body)).toEqual({ title: "新名字", is_public: false });
  });

  it("deleteWork 发 DELETE", async () => {
    await deleteWork(7);
    const call = calls.find((c) => c.url === "/api/scratch/works/7");
    expect(call.method).toBe("DELETE");
    expect(call.headers["X-CSRF-Token"]).toBe("STUDENT-TOKEN");
  });

  it("shareWork 发 POST /api/scratch/works/share，body 带 project_id", async () => {
    await shareWork(42);
    const call = calls.find((c) => c.url === "/api/scratch/works/share");
    expect(call.method).toBe("POST");
    expect(JSON.parse(call.body)).toEqual({ project_id: 42 });
  });

  it("fetchGallery 把参数拼进查询串", async () => {
    await fetchGallery({ page: 2, size: 12, sort: "popular", keyword: "猫" });
    const call = calls.find((c) => c.url.startsWith("/api/scratch/gallery?"));
    expect(call.url).toContain("page=2");
    expect(call.url).toContain("size=12");
    expect(call.url).toContain("sort=popular");
    expect(call.url).toContain("keyword=" + encodeURIComponent("猫"));
    expect(call.method).toBe("GET");
  });

  it("fetchGalleryWork 发 GET /api/scratch/gallery/{id}", async () => {
    await fetchGalleryWork(7);
    const call = calls.find((c) => c.url === "/api/scratch/gallery/7");
    expect(call).toBeTruthy();
    expect(call.method).toBe("GET");
  });
});
