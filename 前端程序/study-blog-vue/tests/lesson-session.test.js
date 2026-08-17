// @vitest-environment jsdom
// 学员端主客户端（services/auth.js）的 401 续期。
//
// 背景：这里的 retryOnUnauthorized 默认值曾经是 false，于是 9 个业务调用点全部漏传，
// access_token 只活 15 分钟而课时页是长驻页面——"看完视频点练习"必然弹「登录已过期」，
// 手动刷新才好（整页重载走 getCurrentUser，那是当时唯一传了 true 的调用）。
// 漏传要等 15 分钟才现形，人工测不出来，所以这组用例钉住默认值和白名单两件事。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { login, request, resetSessionState } from "../src/services/auth";

beforeEach(() => {
  document.cookie = "csrf_token=tk"; // csrfToken() 从 cookie 里取，写操作要用
  // 闩锁是模块级状态，同一个测试文件里所有用例共享。上一条用例把会话刷死了，
  // 下一条就再也刷不动了——用例之间必须解闩。
  resetSessionState();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** 业务接口先 401，续期之后放行。返回调用记录供断言顺序。 */
function mockExpiredThenRefreshed({ refreshOk = true } = {}) {
  const calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, options = {}) => {
      const path = String(url);
      calls.push(path);
      if (path.includes("/api/auth/refresh")) {
        if (!refreshOk)
          return { ok: false, status: 401, json: async () => ({ detail: "登录已失效，请重新登录。" }) };
        // 服务端续期成功会 Set-Cookie 轮换 csrf_token，这里如实模拟——
        // 重放写请求时读到的必须是轮换后的新值，否则重试撞 403。
        document.cookie = "csrf_token=tk2";
        return { ok: true, status: 200, json: async () => ({ message: "ok" }) };
      }
      if (path.includes("/api/auth/csrf")) {
        document.cookie = "csrf_token=tk2";
        return { ok: true, status: 200, json: async () => ({}) };
      }
      const refreshed = calls.some((item) => item.includes("/api/auth/refresh"));
      if (!refreshed)
        return { ok: false, status: 401, json: async () => ({ detail: "登录已过期，请重新登录。" }) };
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true, method: options.method, csrf: options.headers?.["X-CSRF-Token"] }),
      };
    }),
  );
  return calls;
}

describe("课时接口的 401 续期", () => {
  it("读接口不传第三个参数也会续期——默认必须是开的", async () => {
    const calls = mockExpiredThenRefreshed();
    // 用户实测报错的那一条：GET /api/lessons/1/blocks/12/problem
    await expect(request("/api/lessons/1/blocks/12/problem")).resolves.toMatchObject({ ok: true });
    expect(calls.filter((item) => item.includes("/api/auth/refresh"))).toHaveLength(1);
    expect(calls.filter((item) => item.includes("/blocks/12/problem"))).toHaveLength(2); // 原始 + 重试
  });

  it("写接口：续期后重新取 CSRF 再重试——续期会轮换 csrf cookie", async () => {
    mockExpiredThenRefreshed();
    const result = await request("/api/lessons/1/blocks/12/answer", {
      method: "POST",
      body: JSON.stringify({ answer: { picked: "A" } }),
    });
    expect(result).toMatchObject({ method: "POST", csrf: "tk2" }); // 用的是轮换后的新 token
  });

  it("并发 401 只发一次 /refresh——各刷各的会被服务端判定为令牌重放并吊销会话族", async () => {
    const calls = mockExpiredThenRefreshed();
    await Promise.all([
      request("/api/lessons/1"),
      request("/api/lessons/1/blocks/12/problem"),
      request("/api/courses/3"),
    ]);
    expect(calls.filter((item) => item.includes("/api/auth/refresh"))).toHaveLength(1);
  });

  it("会话真被吊销时保留原始 401 文案，不吞掉", async () => {
    mockExpiredThenRefreshed({ refreshOk: false });
    await expect(request("/api/lessons/1")).rejects.toThrow("登录已过期，请重新登录。");
  });
});

/** 全线 401：会话真死的样子。 */
function mockAllUnauthorized() {
  const calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      calls.push(String(url));
      return { ok: false, status: 401, json: async () => ({ detail: "登录已失效，请重新登录。" }) };
    }),
  );
  return calls;
}

describe("续期失败后的两道闸", () => {
  it("/refresh 回 401 = 会话真死 → 上闩，后续请求不再打 /refresh", async () => {
    const calls = mockAllUnauthorized();
    await expect(request("/api/lessons/1")).rejects.toThrow();
    await expect(request("/api/lessons/1/blocks/12/problem")).rejects.toThrow();
    await expect(request("/api/courses/3")).rejects.toThrow();
    // 三个请求只刷了一次。没有闩锁就是 3 次，而 /refresh 每次都要上行锁。
    expect(calls.filter((item) => item.includes("/api/auth/refresh"))).toHaveLength(1);
  });

  it("重新登录会解闩，否则这个页面到刷新为止都续不了期", async () => {
    mockAllUnauthorized();
    await expect(request("/api/lessons/1")).rejects.toThrow(); // 上闩

    // 换一套：登录通了，之后业务请求首次 401 → 续期 → 重放
    const calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        const path = String(url);
        calls.push(path);
        if (path.includes("/api/auth/login") || path.includes("/api/auth/refresh"))
          return { ok: true, status: 200, json: async () => ({ message: "ok" }) };
        return calls.some((item) => item.includes("/api/auth/refresh"))
          ? { ok: true, status: 200, json: async () => ({ ok: true }) }
          : { ok: false, status: 401, json: async () => ({ detail: "登录已过期，请重新登录。" }) };
      }),
    );
    await login({ identifier: "a", password: "b" });
    await expect(request("/api/lessons/1")).resolves.toMatchObject({ ok: true });
    expect(calls.filter((item) => item.includes("/api/auth/refresh"))).toHaveLength(1);
  });

  it("网络错误只上冷却期，不上闩——网抖一下不该把人锁到刷新页面为止", async () => {
    let clock = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => clock);
    const calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        const path = String(url);
        calls.push(path);
        if (path.includes("/api/auth/refresh")) throw new TypeError("Failed to fetch");
        return { ok: false, status: 401, json: async () => ({ detail: "登录已过期，请重新登录。" }) };
      }),
    );
    const refreshCount = () => calls.filter((item) => item.includes("/api/auth/refresh")).length;

    await expect(request("/api/lessons/1")).rejects.toThrow();
    expect(refreshCount()).toBe(1);

    await expect(request("/api/lessons/1")).rejects.toThrow(); // 冷却期内：不打网络
    expect(refreshCount()).toBe(1);

    clock += 5001; // 冷却期过
    await expect(request("/api/lessons/1")).rejects.toThrow();
    expect(refreshCount()).toBe(2); // 允许再试，没有被永久锁死
  });
});

describe("白名单：凭据类接口的 401 不触发续期", () => {
  it("登录失败不去刷新会话——那是密码错了，续期救不回来", async () => {
    const calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        calls.push(String(url));
        return {
          ok: false,
          status: 401,
          json: async () => ({ detail: "用户名或密码错误。" }),
        };
      }),
    );
    await expect(login({ identifier: "a", password: "b" })).rejects.toThrow("用户名或密码错误。");
    expect(calls.some((item) => item.includes("/api/auth/refresh"))).toBe(false);
    expect(calls.filter((item) => item.includes("/api/auth/login"))).toHaveLength(1); // 没有重放
  });

  it("/refresh 自己 401 时不递归续期", async () => {
    const calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        calls.push(String(url));
        return { ok: false, status: 401, json: async () => ({ detail: "登录已失效，请重新登录。" }) };
      }),
    );
    await expect(request("/api/lessons/1")).rejects.toThrow("登录已失效，请重新登录。");
    // 业务请求 1 次（重放没发生，因为续期失败）+ /refresh 1 次，绝不能是无限递归
    expect(calls.filter((item) => item.includes("/api/auth/refresh"))).toHaveLength(1);
  });
});
