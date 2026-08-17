// @vitest-environment jsdom
// 课时页的加载态与预取护栏，对应交接文档 17 §5 批次 2。
//
// 这里护的是三件很容易在后续改动中被"顺手改回去"的事：
// - 加载页是**延迟显示**（250ms 内返回就不出场），不是"最少显示 400ms"；
// - 预取只是提速手段：失败必须被吞掉并退回正常请求，不能让用户看到预取的错；
// - saveData / 2g 下一个预取请求都不许发。
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn(), routerPush: vi.fn() }));

vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { lessonId: "1" } }),
  useRouter: () => ({ push: mocks.routerPush }),
}));
vi.mock("../src/services/auth", () => ({ request: mocks.request }));

import LessonPlayer from "../src/views/LessonPlayer.vue";
import {
  clearBlockPrefetch,
  clearLessonPrefetch,
  prefetchLesson,
  takeLesson,
} from "../src/services/prefetch";

const STUBS = {
  BlockMarkdown: true,
  BlockPractice: true,
  BlockVideo: true,
  BlockMaterials: true,
  BlockHomework: true,
  LessonDrawer: true,
  ImageLightbox: true,
};

/** 首块图文 + 次块单题：图文块不会自己发请求，预取到的就只有次块的题面。 */
function lessonFixture() {
  return {
    id: 1,
    course_id: 9,
    course_title: "单课程",
    title: "第一章节",
    next_lesson_id: null,
    progress: { total: 2, done: 0, percent: 0 },
    blocks: [
      {
        id: 21,
        sort_order: 0,
        block_type: "markdown",
        title: "程序结构",
        content_md: "# 标题",
        completed: false,
        lock_reason: null,
      },
      {
        id: 22,
        sort_order: 1,
        block_type: "practice",
        title: "课中练习",
        completed: false,
        lock_reason: null,
      },
    ],
  };
}

function mountPlayer() {
  return mount(LessonPlayer, { global: { stubs: STUBS } });
}

function setConnection(value) {
  Object.defineProperty(navigator, "connection", { value, configurable: true });
}

/**
 * 只数「课时详情」这一个地址的请求次数。
 *
 * 不能直接断言 mocks.request 的总调用数：idle() 排的块级预热（题面 / 播放令牌）
 * 在 jsdom 里退化成 setTimeout(300)，用例结束时它可能还没烧完，回调会落到**下一条
 * 用例**里再打一次请求——beforeEach 的 clearBlockPrefetch 清得掉缓存、清不掉已经
 * 排好的定时器。按路径过滤后，这类漏进来的预热不会污染计数。
 */
function lessonCalls(lessonId) {
  return mocks.request.mock.calls.filter(([path]) => path === `/api/lessons/${lessonId}`).length;
}

beforeEach(() => {
  mocks.request.mockReset();
  mocks.routerPush.mockReset();
  // 模块级缓存要在用例之间清干净，否则上一条用例预取的东西会被下一条"命中"
  clearBlockPrefetch();
  clearLessonPrefetch();
  setConnection(undefined);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("加载页：延迟显示，而不是延长显示", () => {
  it("接口很快返回时加载页根本不出场", async () => {
    mocks.request.mockResolvedValue(lessonFixture());
    const wrapper = mountPlayer();
    await flushPromises();

    expect(wrapper.find(".lesson-loading").exists()).toBe(false);
    expect(wrapper.find(".lesson-topbar").exists()).toBe(true);
    wrapper.unmount();
  });

  it("接口慢时才出场，且出场后至少驻留一段时间再撤（防闪）", async () => {
    vi.useFakeTimers();
    let resolveLesson;
    // 只认课时详情那一发的 resolve：上一条用例 idle() 排的块级预热是**真** 300ms
    // 定时器（jsdom 没有 requestIdleCallback），机器一忙就会漏到这条用例里再打一次
    // request——不判路径的话 resolveLesson 会被改写成指向那一发，
    // resolveLesson(...) 解的就不是课时详情，加载页永远撤不掉（间歇性红）。
    mocks.request.mockImplementation(
      (path) =>
        new Promise((resolve) => {
          if (path === "/api/lessons/1") resolveLesson = resolve;
        }),
    );
    const wrapper = mountPlayer();

    // 250ms 的延迟线之前：什么都不显示
    await vi.advanceTimersByTimeAsync(200);
    expect(wrapper.find(".lesson-loading").exists()).toBe(false);

    // 越过延迟线：加载页出场
    await vi.advanceTimersByTimeAsync(100);
    expect(wrapper.find(".lesson-loading").exists()).toBe(true);

    // 数据紧接着就到了，但加载页刚露脸——必须先站满最短驻留时间，不能闪一下就没
    resolveLesson(lessonFixture());
    await flushPromises();
    expect(wrapper.find(".lesson-loading").exists()).toBe(true);

    await vi.advanceTimersByTimeAsync(400);
    expect(wrapper.find(".lesson-loading").exists()).toBe(false);
    expect(wrapper.find(".lesson-topbar").exists()).toBe(true);
    wrapper.unmount();
  });

  it("加载失败时加载页立刻出场，不受延迟线影响", async () => {
    mocks.request.mockRejectedValue(new Error("课时加载失败。"));
    const wrapper = mountPlayer();
    await flushPromises();

    expect(wrapper.find(".lesson-loading").exists()).toBe(true);
    expect(wrapper.text()).toContain("课时加载失败");
    wrapper.unmount();
  });
});

describe("课时详情预取", () => {
  it("目录页 hover 预取过，课时页直接用，不再打第二次", async () => {
    mocks.request.mockResolvedValue(lessonFixture());
    prefetchLesson(1);
    await flushPromises();
    expect(lessonCalls(1)).toBe(1);

    const wrapper = mountPlayer();
    await flushPromises();

    expect(lessonCalls(1)).toBe(1); // 命中，没有第二次
    expect(wrapper.find(".lesson-topbar").exists()).toBe(true);
    wrapper.unmount();
  });

  it("鼠标反复扫过同一节课只预取一次", async () => {
    mocks.request.mockResolvedValue(lessonFixture());
    prefetchLesson(1);
    prefetchLesson(1);
    prefetchLesson(1);
    await flushPromises();

    expect(lessonCalls(1)).toBe(1);
  });

  it("预取失败不把错误带给用户，退回正常请求重来一遍", async () => {
    mocks.request.mockRejectedValueOnce(new Error("预取时网断了"));
    prefetchLesson(1);
    await flushPromises();

    mocks.request.mockResolvedValue(lessonFixture());
    const wrapper = mountPlayer();
    await flushPromises();

    expect(wrapper.find(".lesson-loading").exists()).toBe(false);
    expect(wrapper.find(".lesson-topbar").exists()).toBe(true);
    wrapper.unmount();
  });

  it("P2：取走不删——TTL 内再次 take 命中同一份数据，不重发请求", async () => {
    vi.useFakeTimers();
    mocks.request.mockResolvedValue(lessonFixture());
    prefetchLesson(1);
    await flushPromises();

    const first = takeLesson(1);
    expect(first).not.toBeNull();
    // 缓存保留：第二次 take 返回同一个 promise（站内二次进入同一课时直接复用）
    expect(takeLesson(1)).toBe(first);
    expect(lessonCalls(1)).toBe(1); // 两次 take 只打了一次课时详情请求
  });

  it("P2：数据偏旧（≥10s）时 take 触发后台复核，为下次进入准备新数据", async () => {
    vi.useFakeTimers();
    mocks.request.mockResolvedValue(lessonFixture());
    prefetchLesson(1);
    await vi.advanceTimersByTimeAsync(11_000); // 跨过复核线（10s），仍在 TTL（30s）内

    takeLesson(1);
    // 命中旧数据 + 后台复核各一次：请求数从 1 变 2
    expect(lessonCalls(1)).toBe(2);
  });

  it("P2：复核失败保留旧数据，不把缓存覆盖成 null", async () => {
    vi.useFakeTimers();
    mocks.request.mockResolvedValue(lessonFixture());
    prefetchLesson(1);
    await flushPromises();

    await vi.advanceTimersByTimeAsync(11_000);
    mocks.request.mockRejectedValueOnce(new Error("复核时网断了"));
    const hit = takeLesson(1);
    await flushPromises();
    // 返回的仍是旧数据的 promise，不会被 null 覆盖（下次进入仍命中好数据）
    await expect(hit).resolves.toEqual(lessonFixture());
    expect(lessonCalls(1)).toBe(2);
  });
});

describe("相邻块预热", () => {
  it("停在图文块时把下一块的题面提前取回来", async () => {
    vi.useFakeTimers();
    mocks.request.mockResolvedValue(lessonFixture());
    const wrapper = mountPlayer();
    await flushPromises();

    // jsdom 没有 requestIdleCallback，idle() 退回短 setTimeout
    await vi.advanceTimersByTimeAsync(500);

    expect(mocks.request).toHaveBeenCalledWith("/api/lessons/1/blocks/22/problem");
    wrapper.unmount();
  });
});

describe("预取护栏", () => {
  it("saveData 开启时一个预取请求都不发", async () => {
    setConnection({ saveData: true, effectiveType: "4g" });
    mocks.request.mockResolvedValue(lessonFixture());

    prefetchLesson(2);
    await flushPromises();

    expect(mocks.request).not.toHaveBeenCalled();
  });

  it("2g 网络下不预取", async () => {
    setConnection({ saveData: false, effectiveType: "slow-2g" });
    mocks.request.mockResolvedValue(lessonFixture());

    prefetchLesson(2);
    await flushPromises();

    expect(mocks.request).not.toHaveBeenCalled();
  });

  it("4g 网络照常预取", async () => {
    setConnection({ saveData: false, effectiveType: "4g" });
    mocks.request.mockResolvedValue(lessonFixture());

    prefetchLesson(2);
    await flushPromises();

    expect(mocks.request).toHaveBeenCalledWith("/api/lessons/2");
  });
});
