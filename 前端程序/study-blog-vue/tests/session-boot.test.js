// @vitest-environment jsdom
// 整页刷新时的身份加载（P1-3）。
//
// 背景：路由守卫在 router.install() 里就开始拉 /me，App.vue 的 onMounted 也要拉一次。
// 两次调用**通常不重叠**——App.vue 那次排在自己的 getCsrf() 之后，那时守卫的 /me
// 多半已经回来了——所以 auth.js 里"共享 in-flight promise"的单飞挡不住第二发。
// 收口只能按 session.loaded 做（stores/session.ensureSession）。
//
// 这组用例钉住三件事：串行调用只打一次、并发调用只打一次、会话过期后必须重新拉。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ensureSession, session } from "../src/stores/session";

function stubMe(user = { id: 1, username: "student" }) {
  const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => user }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** 只数 /me，不受 csrf 等其它请求干扰。 */
function meCalls(fetchMock) {
  return fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/auth/me")).length;
}

beforeEach(() => {
  // session 是模块级 reactive，用例之间必须复位，否则上一条的 loaded=true 会让下一条直接命中
  session.user = null;
  session.loaded = false;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("整页刷新只加载一次身份", () => {
  it("守卫先拉完、App.vue 随后再要（串行）：第二次直接命中，不再发请求", async () => {
    const fetchMock = stubMe();

    await ensureSession(); // 路由守卫
    expect(meCalls(fetchMock)).toBe(1);
    expect(session.user).toEqual({ id: 1, username: "student" });

    await ensureSession(); // App.vue onMounted，此时守卫那发已经 settle
    expect(meCalls(fetchMock)).toBe(1); // 关键断言：没有第二次 /me
    expect(session.loaded).toBe(true);
  });

  it("守卫与 App.vue 真撞在一起（并发）：共享同一个 in-flight，只打一次", async () => {
    const fetchMock = stubMe();

    await Promise.all([ensureSession(), ensureSession(), ensureSession()]);

    expect(meCalls(fetchMock)).toBe(1);
    expect(session.user).toEqual({ id: 1, username: "student" });
  });

  it("未登录时落 null 且标记已加载，不把错误抛给守卫", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 401,
        json: async () => ({ detail: "登录已过期，请重新登录。" }),
      })),
    );

    await expect(ensureSession()).resolves.toBeUndefined(); // 守卫不需要 try/catch
    expect(session.user).toBeNull();
    expect(session.loaded).toBe(true);
  });

  it("会话过期后 loaded 置回 false：下次必须重新校验，不能复用旧身份", async () => {
    const fetchMock = stubMe();
    await ensureSession();
    expect(meCalls(fetchMock)).toBe(1);

    // App.vue 的 onSessionExpired 干的事：清用户 + 让下次重新拉
    session.user = null;
    session.loaded = false;

    await ensureSession();
    expect(meCalls(fetchMock)).toBe(2); // 缓存绝不能盖过"重新校验"的信号
  });
});
