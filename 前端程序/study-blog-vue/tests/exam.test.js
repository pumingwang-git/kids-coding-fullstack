// @vitest-environment jsdom
// 学员端考试页的逻辑护栏。组件是薄的，真正会出错的东西都在这三个模块里：
// 时钟（不信本地时间、提醒只弹一次）、自动保存（防抖、切题冲、失败重试）、
// Markdown 渲染（净化 + 空位标记与后台同源）。

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createExamClock, formatDuration } from "../src/composables/useExamClock.js";
import { createAutosave } from "../src/composables/useAutosave.js";
import { renderMarkdown } from "../src/services/markdown.js";

// ==================== 考试时钟 ====================

describe("createExamClock", () => {
  function clockAt(localMs, { serverSkewMs = 0, ...rest } = {}) {
    let now = localMs;
    const clock = createExamClock({
      serverNow: new Date(localMs + serverSkewMs).toISOString(),
      localNow: () => now,
      ...rest,
    });
    return { clock, advance: (ms) => (now += ms) };
  }

  it("按服务端时间起算，忽略本地时钟的偏差", () => {
    const start = Date.parse("2026-08-06T10:00:00Z");
    // 学员把本地时钟拨慢了一小时；剩余时间必须按服务端算。
    const { clock } = clockAt(start, {
      serverSkewMs: 60 * 60 * 1000,
      deadlineAt: new Date(start + 61 * 60 * 1000).toISOString(),
    });
    expect(clock.remainingMs()).toBe(60 * 1000);
  });

  it("本地时钟被往前拨也不会延长考试", () => {
    const start = Date.parse("2026-08-06T10:00:00Z");
    const { clock, advance } = clockAt(start, {
      deadlineAt: new Date(start + 10 * 60 * 1000).toISOString(),
    });
    advance(5 * 60 * 1000);
    expect(clock.remainingMs()).toBe(5 * 60 * 1000);
    // 再"调表"也只是本地时间在走，剩余时间照常减少而不是变多。
    advance(4 * 60 * 1000);
    expect(clock.remainingMs()).toBe(60 * 1000);
  });

  it("sync 用响应里的 server_now 重新对表", () => {
    const start = Date.parse("2026-08-06T10:00:00Z");
    const { clock } = clockAt(start, {
      deadlineAt: new Date(start + 10 * 60 * 1000).toISOString(),
    });
    clock.sync(new Date(start + 9 * 60 * 1000).toISOString());
    expect(clock.remainingMs()).toBe(60 * 1000);
  });

  it("每个提醒点只触发一次", () => {
    const start = Date.parse("2026-08-06T10:00:00Z");
    const fired = [];
    const { clock, advance } = clockAt(start, {
      deadlineAt: new Date(start + 31 * 60 * 1000).toISOString(),
      remindMinutes: "30,10,5",
      onRemind: (minute) => fired.push(minute),
    });
    // 从剩余 31 分逐分钟走到剩余 6 分：30 与 10 两个点被穿过。
    for (let i = 0; i < 26; i += 1) {
      clock.tick();
      advance(60 * 1000);
    }
    expect(fired).toEqual([30, 10]);
    // 现在剩余正好 5 分钟。连续两次 tick 只该弹一次——倒计时抖动会让
    // 同一个阈值反复命中，没有去重集合的话学员会被同一条提醒刷屏。
    clock.tick();
    clock.tick();
    expect(fired).toEqual([30, 10, 5]);
  });

  it("归零时触发一次自动交卷", () => {
    const start = Date.parse("2026-08-06T10:00:00Z");
    const expire = vi.fn();
    const { clock, advance } = clockAt(start, {
      deadlineAt: new Date(start + 1000).toISOString(),
      onExpire: expire,
    });
    clock.tick();
    expect(expire).not.toHaveBeenCalled();
    advance(2000);
    clock.tick();
    clock.tick();
    expect(expire).toHaveBeenCalledTimes(1);
    expect(clock.remainingMs()).toBe(0);
  });

  it("不限时的场次没有倒计时", () => {
    const { clock } = clockAt(Date.now(), { deadlineAt: null, remindMinutes: "10" });
    expect(clock.unlimited).toBe(true);
    expect(clock.remainingMs()).toBeNull();
    expect(clock.tick()).toBeNull();
  });

  it("formatDuration 分秒与时分秒", () => {
    expect(formatDuration(0)).toBe("00:00");
    expect(formatDuration(65 * 1000)).toBe("01:05");
    expect(formatDuration(3661 * 1000)).toBe("01:01:01");
    expect(formatDuration(-5)).toBe("00:00");
  });
});

// ==================== 自动保存 ====================

describe("createAutosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("同一题连续修改只发最后一次", async () => {
    const save = vi.fn().mockResolvedValue({});
    const autosave = createAutosave({ save, delay: 1500 });
    autosave.schedule("Q1", { type: "fill", blanks: { b1: "p" } });
    autosave.schedule("Q1", { type: "fill", blanks: { b1: "pr" } });
    autosave.schedule("Q1", { type: "fill", blanks: { b1: "print" } });
    await vi.advanceTimersByTimeAsync(1600);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("Q1", { type: "fill", blanks: { b1: "print" } });
  });

  it("immediate 绕过防抖（选项类立刻存）", async () => {
    const save = vi.fn().mockResolvedValue({});
    const autosave = createAutosave({ save });
    await autosave.schedule("Q1", { type: "choice", picked: "B" }, { immediate: true });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("flushAll 把挂起的都冲出去——切题时用", async () => {
    const save = vi.fn().mockResolvedValue({});
    const autosave = createAutosave({ save, delay: 5000 });
    autosave.schedule("Q1", { type: "choice", picked: "A" });
    autosave.schedule("Q2", { type: "choice", picked: "B" });
    expect(autosave.hasPending()).toBe(true);
    await autosave.flushAll();
    expect(save).toHaveBeenCalledTimes(2);
    expect(autosave.hasPending()).toBe(false);
  });

  it("失败后退避重试，最终成功", async () => {
    const save = vi
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue({});
    const autosave = createAutosave({ save, retries: 3, retryBase: 100 });
    const done = autosave.flushOne("Q1");
    autosave.schedule("Q1", { type: "choice", picked: "A" }, { immediate: true });
    await vi.advanceTimersByTimeAsync(1000);
    await done;
    expect(save).toHaveBeenCalledTimes(3);
    expect(autosave.status.value).toBe("saved");
  });

  it("重试用尽后报错，并保留内容不清空", async () => {
    const save = vi.fn().mockRejectedValue(new Error("network"));
    const autosave = createAutosave({ save, retries: 1, retryBase: 10 });
    const attempt = autosave.schedule("Q1", { type: "choice", picked: "A" }, { immediate: true });
    const settled = attempt.catch((error) => error);
    await vi.advanceTimersByTimeAsync(200);
    expect(await settled).toBeInstanceOf(Error);
    expect(autosave.status.value).toBe("error");
    expect(autosave.hasPending()).toBe(true); // 内容还在，等下一次 flush
  });

  it("409 不重试——考试已结束，重试多少次都一样", async () => {
    const error = Object.assign(new Error("本次作答已交卷。"), { status: 409 });
    const save = vi.fn().mockRejectedValue(error);
    const autosave = createAutosave({ save, retries: 3, retryBase: 10 });
    const settled = autosave
      .schedule("Q1", { type: "choice", picked: "A" }, { immediate: true })
      .catch((caught) => caught);
    await vi.advanceTimersByTimeAsync(200);
    expect((await settled).status).toBe(409);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("cancelAll 之后不再发请求", async () => {
    const save = vi.fn().mockResolvedValue({});
    const autosave = createAutosave({ save, delay: 500 });
    autosave.schedule("Q1", { type: "choice", picked: "A" });
    autosave.cancelAll();
    await vi.advanceTimersByTimeAsync(1000);
    expect(save).not.toHaveBeenCalled();
  });
});

// ==================== Markdown 渲染 ====================

describe("renderMarkdown", () => {
  it("渲染基本 Markdown", () => {
    expect(renderMarkdown("**粗体**")).toContain("<strong>粗体</strong>");
  });

  it("剥掉脚本与事件处理器", () => {
    const html = renderMarkdown('<script>alert(1)<\/script><img src=x onerror="alert(2)">');
    expect(html).not.toContain("<script");
    expect(html).not.toContain("onerror");
  });

  it("代码块里的尖括号原样保留——题干常见 #include <iostream>", () => {
    const html = renderMarkdown("```cpp\n#include <iostream>\n```");
    expect(html).toContain("&lt;iostream&gt;");
  });

  it("空位标记渲染成可见填空条并带上 key", () => {
    const html = renderMarkdown("输出用 \\placeholder[b1]{} 函数。");
    expect(html).toContain('class="blank-mark"');
    expect(html).toContain('data-key="b1"');
  });

  it("代码块里的下划线不会被当成空位", () => {
    const html = renderMarkdown("```py\n___ = 1\n```");
    expect(html).not.toContain("blank-mark");
  });

  it("空输入不炸", () => {
    expect(renderMarkdown("")).toBe("");
    expect(renderMarkdown(null)).toBe("");
    expect(renderMarkdown(undefined)).toBe("");
  });
});
