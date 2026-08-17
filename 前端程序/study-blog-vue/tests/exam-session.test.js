// @vitest-environment jsdom
// 考试接口的会话续期。
//
// 背景：access_token 的 cookie max-age 只有 15 分钟，而一场考试可以有 90 分钟，
// 考试页内部又没有任何路由导航会触发续期。所以"不做 401 续期"必然导致第 15 分钟
// 集体 401——自动保存报错、交卷失败。这组用例钉住修好之后的行为。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { fetchEntry, saveAnswer } from "../src/services/exam";
import { resetSessionState } from "../src/services/auth";
// 静态导入：ExamView 拖着作答页那一整串组件，放进用例里加载会把 5s 超时吃满
import ExamView from "../src/views/ExamView.vue";

beforeEach(() => {
  // csrfToken() 从 cookie 里取，写操作要用
  document.cookie = "csrf_token=tk";
  // auth.js 的 sessionDead 是模块级状态，跨用例残留会让 refreshSession 直接 reject
  // 不进 catch、不发 session:expired 事件——必须每条用例前解闩
  resetSessionState();
});
afterEach(() => vi.unstubAllGlobals());

/** 第一次 401，续期之后放行。返回调用记录供断言顺序。 */
function mockExpiredThenRefreshed({ refreshOk = true } = {}) {
  const calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, options = {}) => {
      const path = String(url);
      calls.push(path);
      if (path.includes("/api/auth/refresh")) {
        return refreshOk
          ? { ok: true, status: 200, json: async () => ({ message: "ok" }) }
          : { ok: false, status: 401, json: async () => ({ detail: "登录已失效，请重新登录。" }) };
      }
      if (path.includes("/api/auth/csrf")) {
        document.cookie = "csrf_token=tk2";
        return { ok: true, status: 200, json: async () => ({}) };
      }
      // 考试接口：续期之前 401，之后 200
      const refreshed = calls.some((item) => item.includes("/api/auth/refresh"));
      if (!refreshed)
        return {
          ok: false,
          status: 401,
          json: async () => ({ detail: "登录已过期，请重新登录。" }),
        };
      return { ok: true, status: 200, json: async () => ({ ok: true, method: options.method }) };
    }),
  );
  return calls;
}

describe("考试接口的 401 续期", () => {
  it("读接口：401 之后续期一次并重试，调用方拿到正常结果", async () => {
    const calls = mockExpiredThenRefreshed();
    await expect(fetchEntry("tk0")).resolves.toEqual({ ok: true, method: undefined });
    expect(calls.filter((item) => item.includes("/api/auth/refresh"))).toHaveLength(1);
    expect(calls.filter((item) => item.includes("/api/exam/tk0"))).toHaveLength(2); // 原始 + 重试
  });

  it("写接口：续期后重新取 CSRF 再重试——续期会轮换 csrf cookie", async () => {
    const calls = mockExpiredThenRefreshed();
    await expect(saveAnswer(7, "Q1", { type: "choice", picked: "A" })).resolves.toMatchObject({
      method: "PUT",
    });
    // 续期之后必须再要一次 csrf，否则重试撞 403
    const csrfAfterRefresh = calls.slice(calls.indexOf("/api/auth/refresh") + 1);
    expect(csrfAfterRefresh.some((item) => item.includes("/api/auth/csrf"))).toBe(true);
  });

  it("会话真被吊销时保留原始 401，不吞掉", async () => {
    mockExpiredThenRefreshed({ refreshOk: false });
    await expect(fetchEntry("tk0")).rejects.toMatchObject({
      name: "ExamError",
      status: 401,
    });
  });
});

describe("考试页在会话失效时跳登录", () => {
  async function mountExamAt(token, { status = 401 } = {}) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        const path = String(url);
        if (path.includes("/api/auth/refresh") || path.includes("/api/auth/csrf"))
          return { ok: false, status: 401, json: async () => ({}) };
        return { ok: false, status, json: async () => ({ detail: "登录已过期，请重新登录。" }) };
      }),
    );
    const dummy = { template: "<div />" };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/auth", name: "auth", component: dummy },
        { path: "/courses", name: "courses", component: dummy },
        { path: "/exam/:token", name: "exam", component: ExamView },
      ],
    });
    router.push(`/exam/${token}`);
    await router.isReady();
    const wrapper = mount({ template: "<router-view />" }, { global: { plugins: [router] } });
    await new Promise((resolve) => setTimeout(resolve, 30));
    return { wrapper, router };
  }

  it("401：触发 session:expired 事件，由 App.vue 全局接管跳登录（P2 收归）", async () => {
    // ExamView 不再自己跳 /auth（P2 收归 App.vue 全局监听 session:expired）。
    // 这里只验证事件被触发——跳转由 App.vue 负责，不在 ExamView 单元测试覆盖范围。
    const events = [];
    const handler = () => events.push("expired");
    window.addEventListener("session:expired", handler);
    await mountExamAt("abc123");
    await new Promise((r) => setTimeout(r, 10)); // 等 refreshSession 异步链走完
    window.removeEventListener("session:expired", handler);
    expect(events).toContain("expired");
  });

  it("非 401（链接失效）仍然停在考试页显示原因，不跳登录", async () => {
    const { router, wrapper } = await mountExamAt("abc123", { status: 404 });
    expect(router.currentRoute.value.path).toBe("/exam/abc123");
    expect(wrapper.text()).toContain("无法进入考试");
  });
});
