// @vitest-environment jsdom
// VideoPlayer.vue 令牌续签护栏（口径 2026-08-09 拍板：短期 Bearer，播放器负责续签）。
// 覆盖三态：临近过期自动续签（保留播放位置）/ 页面恢复可见续签 / 错误后冷却期内不风暴。
// videojs 在 jsdom 无真实媒体能力，这里 mock 掉并用手动派发的事件驱动逻辑。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const playerMock = vi.hoisted(() => ({
  instance: null,
  create() {
    const p = {
      handlers: {},
      on(ev, cb) {
        this.handlers[ev] = cb;
      },
      one(ev, cb) {
        this.handlers[`one:${ev}`] = cb;
      },
      src: vi.fn(),
      play: vi.fn().mockResolvedValue(undefined),
      currentTime: vi.fn(() => 0),
      duration: vi.fn(() => 100),
      // timeupdate 处理器要问「是不是暂停着」——暂停时不上报进度，
      // 否则等于给挂机记账（见 VideoPlayer.vue 的 timeupdate 注释）。
      paused: vi.fn(() => false),
      dispose: vi.fn(),
    };
    playerMock.instance = p;
    return p;
  },
}));

vi.mock("video.js/dist/video.min.js", () => ({ default: () => playerMock.create() }));
vi.mock("video.js/dist/video-js.css", () => ({}));

const requestMock = vi.hoisted(() => vi.fn());
vi.mock("../src/services/auth", () => ({ request: requestMock }));

import VideoPlayer from "../src/components/VideoPlayer.vue";
import DirectVideo from "../src/components/DirectVideo.vue";

const T0 = new Date("2026-01-01T00:00:00Z");

function playPayload(tok) {
  return { master_playlist: `/v/${tok}/1/master.m3u8`, expires_in_seconds: 3600 };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(T0);
  requestMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  playerMock.instance = null;
});

describe("令牌续签", () => {
  it("Scratch 解析播放走专属端点且不复用课时预签", async () => {
    requestMock.mockResolvedValueOnce(playPayload("analysis"));
    const wrapper = mount(VideoPlayer, {
      props: { lessonId: 1, playPath: "/api/scratch/lesson-blocks/7/analysis-play" },
    });
    await flushPromises();
    expect(requestMock).toHaveBeenCalledWith("/api/scratch/lesson-blocks/7/analysis-play", {
      method: "POST",
      body: "{}",
    });
    wrapper.unmount();
  });

  it("timeupdate 报的是播放位置（秒），ended 是独立事件", async () => {
    // 曾经这里报的是百分比、且刻意 Math.min(99,…)——那是为了不让 timeupdate
    // 提前触发「100% = 看完了」的客户端判定。完成度改由服务端账本裁决之后，
    // 那个上限没有意义了：壳要把**真实位置**报上去，片尾那几秒才记得进账。
    requestMock.mockResolvedValueOnce(playPayload("tok1"));
    const wrapper = mount(VideoPlayer, { props: { lessonId: 1 } });
    await flushPromises();
    const player = playerMock.instance;

    player.currentTime.mockReturnValue(100);
    player.handlers.timeupdate();
    expect(wrapper.emitted("progress")?.[0]).toEqual([{ position: 100, duration: 100 }]);

    player.handlers.ended();
    expect(wrapper.emitted("ended")).toHaveLength(1);

    wrapper.unmount();
  });

  it("暂停时不上报进度", async () => {
    // 暂停还继续报等于给挂机记账，与服务端记账的目的正相反。
    requestMock.mockResolvedValueOnce(playPayload("tok1"));
    const wrapper = mount(VideoPlayer, { props: { lessonId: 1 } });
    await flushPromises();
    const player = playerMock.instance;

    player.paused.mockReturnValue(true);
    player.currentTime.mockReturnValue(50);
    player.handlers.timeupdate();
    expect(wrapper.emitted("progress")).toBeUndefined();

    wrapper.unmount();
  });

  it("临近过期自动续签并保留播放位置", async () => {
    requestMock
      .mockResolvedValueOnce(playPayload("tok1"))
      .mockResolvedValueOnce(playPayload("tok2"));
    const wrapper = mount(VideoPlayer, { props: { lessonId: 1 } });
    await flushPromises();

    expect(requestMock).toHaveBeenCalledTimes(1);
    const player = playerMock.instance;
    player.currentTime.mockReturnValue(123);

    // 前进 3590 秒：距过期剩 10s（< 60s 自动线）→ 触发续签
    await vi.advanceTimersByTimeAsync(3_590_000);
    expect(requestMock).toHaveBeenCalledTimes(2);
    expect(player.src).toHaveBeenCalledWith({
      src: "/v/tok2/1/master.m3u8",
      type: "application/vnd.apple.mpegurl",
    });
    // 换源后 loadedmetadata 恢复播放位置
    player.handlers["one:loadedmetadata"]();
    expect(player.currentTime).toHaveBeenCalledWith(123);

    wrapper.unmount();
  });

  it("页面恢复可见且令牌临近过期（未到自动线）→ 立即续签", async () => {
    requestMock
      .mockResolvedValueOnce(playPayload("tok1"))
      .mockResolvedValueOnce(playPayload("tok2"));
    const wrapper = mount(VideoPlayer, { props: { lessonId: 1 } });
    await flushPromises();
    expect(requestMock).toHaveBeenCalledTimes(1);

    // 前进 3510 秒：剩 90s —— 高于 60s 自动线，定时器不会续签
    await vi.advanceTimersByTimeAsync(3_510_000);
    expect(requestMock).toHaveBeenCalledTimes(1);

    // 页面恢复可见 → 立即续签
    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();
    expect(requestMock).toHaveBeenCalledTimes(2);

    wrapper.unmount();
  });

  it("播放错误后续签一次，冷却期内再报错不风暴并落屏", async () => {
    requestMock
      .mockResolvedValueOnce(playPayload("tok1"))
      .mockResolvedValueOnce(playPayload("tok2"));
    const wrapper = mount(VideoPlayer, { props: { lessonId: 1 } });
    await flushPromises();
    const player = playerMock.instance;

    // 第一次 error（HLS 401/加载失败）→ 续签
    player.handlers.error();
    await flushPromises();
    expect(requestMock).toHaveBeenCalledTimes(2);

    // 冷却期内再 error → 不再续签，落屏错误
    player.handlers.error();
    await flushPromises();
    expect(requestMock).toHaveBeenCalledTimes(2);
    expect(wrapper.find(".player-error").exists()).toBe(true);

    wrapper.unmount();
  });
});

describe("直链视频结束事件", () => {
  it("timeupdate 报播放位置，ended 是独立事件（载荷与 VideoPlayer 一字不差）", async () => {
    // 壳只写一套 onVideoProgress，两个播放器的载荷形状必须完全一致。
    const wrapper = mount(DirectVideo, { props: { src: "https://example.com/video.mp4" } });
    await flushPromises();
    const player = playerMock.instance;

    player.currentTime.mockReturnValue(100);
    player.handlers.timeupdate();
    expect(wrapper.emitted("progress")?.[0]).toEqual([{ position: 100, duration: 100 }]);

    player.handlers.ended();
    expect(wrapper.emitted("ended")).toHaveLength(1);

    wrapper.unmount();
  });
});
