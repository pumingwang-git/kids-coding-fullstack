// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  routerPush: vi.fn(),
}));

vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { lessonId: "1" } }),
  useRouter: () => ({ push: mocks.routerPush }),
}));

vi.mock("../src/services/auth", () => ({ request: mocks.request }));

import LessonPlayer from "../src/views/LessonPlayer.vue";

const settle = () => new Promise((resolve) => setTimeout(resolve, 520));

function videoLesson({ nextLessonId = 2 } = {}) {
  return {
    id: 1,
    course_id: 9,
    course_title: "单课程",
    title: "第一章节",
    next_lesson_id: nextLessonId,
    prev_lesson_id: null,
    progress: { total: 1, done: 0, percent: 0 },
    blocks: [
      {
        id: 11,
        sort_order: 0,
        block_type: "video",
        title: "章节视频",
        source_type: "platform",
        ready: true,
        // 服务端裁决完成度（courses._student_block_dto 下发）。前端**不自己推**，
        // 只认这个字段——ledger 的块交给心跳记账，manual 的块才允许手动确认。
        completion_mode: "ledger",
        duration_seconds: 600,
        completed: false,
        lock_reason: null,
      },
    ],
  };
}

const DONE = {
  completed: true,
  progress: { total: 1, done: 1, percent: 100 },
  unlocked_block_ids: [],
};

describe("视频节点自动续播", () => {
  beforeEach(() => {
    mocks.request.mockReset();
    mocks.routerPush.mockReset();
    mocks.request.mockImplementation(async (url) => {
      if (url === "/api/lessons/1") return videoLesson();
      // 账本裁决的块走 /watch（心跳记账），不再走 /complete
      if (url === "/api/lessons/1/blocks/11/watch") return DONE;
      if (url === "/api/lessons/1/blocks/11/complete") return DONE;
      throw new Error(`unexpected request: ${url}`);
    });
  });

  it("视频播放完毕后完成当前节点并进入下一章节", async () => {
    const wrapper = mount(LessonPlayer, {
      global: {
        stubs: {
          BlockVideo: {
            emits: ["ended", "progress"],
            template:
              '<button class="fake-video" type="button" @click="$emit(\'ended\')">结束视频</button>',
          },
        },
      },
    });

    await settle();
    await wrapper.find(".fake-video").trigger("click");
    await flushPromises();

    // 播完补最后一拍心跳（force），完成与否由服务端账本回答
    expect(mocks.request).toHaveBeenCalledWith(
      "/api/lessons/1/blocks/11/watch",
      expect.objectContaining({ method: "POST" }),
    );
    expect(mocks.routerPush).toHaveBeenCalledWith({
      name: "lesson-player",
      params: { lessonId: 2 },
    });

    wrapper.unmount();
  });

  it("课程最后一节完成后返回课程目录", async () => {
    mocks.request.mockImplementation(async (url) => {
      if (url === "/api/lessons/1") return videoLesson({ nextLessonId: null });
      if (url === "/api/lessons/1/blocks/11/watch") return DONE;
      if (url === "/api/lessons/1/blocks/11/complete") return DONE;
      throw new Error(`unexpected request: ${url}`);
    });
    const wrapper = mount(LessonPlayer, {
      global: {
        stubs: {
          BlockVideo: {
            emits: ["ended"],
            template:
              '<button class="fake-video" type="button" @click="$emit(\'ended\')">结束视频</button>',
          },
        },
      },
    });

    await settle();
    await wrapper.find(".fake-video").trigger("click");
    await flushPromises();

    expect(mocks.routerPush).toHaveBeenCalledWith({
      name: "course-detail",
      params: { courseId: 9 },
    });
    wrapper.unmount();
  });

  // 视频块后面再挂一块图文，这样视频块不是最后一块，脚注按钮才是「完成，继续下一块」
  function videoThenText({ sourceType = "platform", ready = true } = {}) {
    const lesson = videoLesson();
    lesson.progress = { total: 2, done: 0, percent: 0 };
    // completion_mode 由服务端算（video_watch.completion_mode）：只有 platform +
    // 时长已知才进账本裁决，embed / direct 一律降级成手动确认。
    const mode = sourceType === "platform" && ready ? "ledger" : "manual";
    Object.assign(lesson.blocks[0], { source_type: sourceType, ready, completion_mode: mode });
    if (sourceType !== "platform") lesson.blocks[0].video_url = "https://example.com/v";
    lesson.blocks.push({
      id: 12, sort_order: 1, block_type: "markdown", title: "图文",
      content_md: "正文", completed: false, lock_reason: null,
    });
    return lesson;
  }

  const BLOCK_STUBS = {
    BlockVideo: { emits: ["ended", "progress"], template: "<div />" },
    BlockMarkdown: { template: "<div />" },
  };

  const clickNext = async (wrapper) => {
    const next = wrapper.findAll("button").find((b) => b.text().includes("继续下一块"));
    expect(next, "没找到「完成，继续下一块」按钮").toBeTruthy();
    await next.trigger("click");
    await flushPromises();
  };

  it("没看完就点「继续下一块」，不得把视频块上报成已完成", async () => {
    // 这里原本会带着默认的 progress_percent=100 补一刀 complete()——于是点一下
    // "下一步"就把视频标成看完了，服务端 lesson_video_blocks.completion_percent
    // 根本挡不住（它只能相信客户端报上来的进度）。有播放器可读进度的块
    // （platform+ready / direct）一律交给 reportVideo 按真实进度上报。
    mocks.request.mockImplementation(async (url) => {
      if (url === "/api/lessons/1") return videoThenText();
      throw new Error(`unexpected request: ${url}`);
    });
    const wrapper = mount(LessonPlayer, { global: { stubs: BLOCK_STUBS } });

    await settle();
    await clickNext(wrapper); // 一眼没看，直接点「完成，继续下一块」

    const reported = mocks.request.mock.calls.filter(([url]) => url.endsWith("/complete"));
    expect(reported, "未观看的视频块被上报成已完成").toEqual([]);
    wrapper.unmount();
  });

  it("播放进度上报的是位置秒数，不是百分比", async () => {
    // 服务端靠**位置差**算「看了多少秒」；报百分比丢掉了"从第几秒到第几秒"，
    // 记账就无从谈起。这条钉住 /watch 的载荷契约。
    const bodies = [];
    mocks.request.mockImplementation(async (url, options) => {
      if (url === "/api/lessons/1") return videoThenText();
      if (url.endsWith("/watch")) {
        bodies.push(JSON.parse(options.body));
        return { completed: false, watched_seconds: 30, required_seconds: 480 };
      }
      throw new Error(`unexpected request: ${url}`);
    });
    const wrapper = mount(LessonPlayer, {
      global: {
        stubs: {
          ...BLOCK_STUBS,
          BlockVideo: {
            emits: ["ended", "progress"],
            template:
              '<button class="fake-tick" type="button" '
              + '@click="$emit(\'progress\', { position: 137.4, duration: 600 })">tick</button>',
          },
        },
      },
    });

    await settle();
    await wrapper.find(".fake-tick").trigger("click");
    await flushPromises();

    expect(bodies).toEqual([{ position_seconds: 137 }]);
    wrapper.unmount();
  });

  it("心跳按时间节流：连打多拍只发一次", async () => {
    // 记账要的是均匀采样。timeupdate 每秒触发 4 次，不节流就是每秒 4 个请求。
    let beats = 0;
    mocks.request.mockImplementation(async (url) => {
      if (url === "/api/lessons/1") return videoThenText();
      if (url.endsWith("/watch")) {
        beats += 1;
        return { completed: false, watched_seconds: 30, required_seconds: 480 };
      }
      throw new Error(`unexpected request: ${url}`);
    });
    const wrapper = mount(LessonPlayer, {
      global: {
        stubs: {
          ...BLOCK_STUBS,
          BlockVideo: {
            emits: ["ended", "progress"],
            template:
              '<button class="fake-tick" type="button" '
              + '@click="$emit(\'progress\', { position: 10, duration: 600 })">tick</button>',
          },
        },
      },
    });

    await settle();
    for (let i = 0; i < 8; i += 1) {
      await wrapper.find(".fake-tick").trigger("click");
    }
    await flushPromises();

    expect(beats).toBe(1);
    wrapper.unmount();
  });

  it("embed 视频没有进度通道，仍允许手动确认完成", async () => {
    // embed 是个裸 iframe，第三方站点的播放进度我们拿不到。这类块如果也不许手动
    // 上报，学生会永远卡在这一块过不去——阈值在这里本来就无从谈起。
    const seen = [];
    mocks.request.mockImplementation(async (url, options) => {
      if (url === "/api/lessons/1") return videoThenText({ sourceType: "embed", ready: undefined });
      if (url.endsWith("/complete")) {
        seen.push(url);
        return {
          completed: true,
          progress: { total: 2, done: 1, percent: 50 },
          unlocked_block_ids: [],
        };
      }
      throw new Error(`unexpected request: ${url}`);
    });
    const wrapper = mount(LessonPlayer, { global: { stubs: BLOCK_STUBS } });

    await settle();
    await clickNext(wrapper);

    expect(seen, "embed 视频块无法完成，学生会卡在这一块").toEqual([
      "/api/lessons/1/blocks/11/complete",
    ]);
    wrapper.unmount();
  });
});
