// @vitest-environment jsdom
// 候考页的历史作答区：摘要 + 最近几条 + 按需分页。
// 这一区的存在意义是"一百次记录也能看"，所以每条断言都围绕"多"来写。
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import ExamLobby from "../src/components/exam/ExamLobby.vue";

const flush = () => new Promise((resolve) => setTimeout(resolve, 20));

function attempt(no, { score = 0, counted = false, status = "submitted" } = {}) {
  return {
    attempt_id: no,
    attempt_no: no,
    status,
    started_at: "2026-08-07T01:00:00+00:00",
    submitted_at: status === "submitted" ? "2026-08-07T01:30:00+00:00" : null,
    duration_seconds: 1800,
    counted,
    ...(status === "submitted" ? { total_score: score } : {}),
  };
}

/** 100 次作答的候考页：服务端只发最近 5 条 + 计分那次。 */
function entryPayload(overrides = {}) {
  return {
    paper: {
      title: "练习卷",
      description: "",
      paper_type: "练习卷",
      subject: "python",
      question_count: 5,
      total_score: 100,
      type_breakdown: { choice: 5 },
    },
    link: {
      name: "默认场次",
      open_at: null,
      close_at: null,
      duration_minutes: 60,
      attempt_limit: 0,
      late_start_policy: "truncate",
      notice: "",
      score_policy: "best",
      notice_ack_required: false,
      entry_open_minutes: 0,
      remind_minutes: "",
      warn_unanswered: true,
    },
    attempts: {
      used: 100,
      limit: 0,
      ongoing_attempt_id: null,
      history: [
        attempt(100, { score: 60 }),
        attempt(99, { score: 55 }),
        attempt(98, { score: 70 }),
        attempt(97, { score: 40 }),
        attempt(96, { score: 65 }),
        attempt(71, { score: 92, counted: true }),
      ],
      summary: {
        count: 100,
        score_policy: "best",
        counted_attempt_id: 71,
        has_more: true,
        best: attempt(71, { score: 92, counted: true }),
        last: attempt(100, { score: 60 }),
      },
    },
    phase: "open",
    can_start: true,
    blocked_reason: null,
    server_now: "2026-08-07T02:00:00+00:00",
    ...overrides,
  };
}

function historyPage(page = 1) {
  const start = 100 - (page - 1) * 20;
  return {
    items: Array.from({ length: 20 }, (_, index) => attempt(start - index, { score: 50 })),
    page,
    size: 20,
    total: 100,
    counted_attempt_id: 71,
    score_policy: "best",
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("候考页 · 历史作答", () => {
  it("一百次记录只铺最近 5 条 + 计分那次，不是全部", async () => {
    const wrapper = mount(ExamLobby, { props: { entry: entryPayload(), token: "tk" } });
    const rows = wrapper.findAll(".history-row");
    expect(rows).toHaveLength(6);
    expect(rows[0].text()).toContain("第 100 次"); // 倒序：最近一次在最上面
    expect(rows[5].text()).toContain("第 71 次");
  });

  it("摘要给出最好/最近/次数，并说清哪一次算数", async () => {
    const wrapper = mount(ExamLobby, { props: { entry: entryPayload(), token: "tk" } });
    const summary = wrapper.find(".history-summary").text();
    expect(summary).toContain("92 分");
    expect(summary).toContain("最好成绩");
    expect(summary).toContain("60 分");
    expect(summary).toContain("100 次");
    expect(wrapper.find(".history-policy").text()).toContain("最好成绩");
    // 计分那行要标出来，否则摘要说 92 分、列表里认不出是哪次
    const counted = wrapper.find(".history-row.is-counted");
    expect(counted.text()).toContain("第 71 次");
    expect(counted.find(".history-flag").text()).toBe("计分");
  });

  it("score_policy=last 时文案跟着变", async () => {
    const entry = entryPayload();
    entry.link.score_policy = "last";
    entry.attempts.summary.score_policy = "last";
    const wrapper = mount(ExamLobby, { props: { entry, token: "tk" } });
    expect(wrapper.find(".history-policy").text()).toContain("最后一次");
  });

  it("「查看全部」点开才拉数据，并且是分页拉的", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => historyPage(1),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(ExamLobby, { props: { entry: entryPayload(), token: "tk" } });

    expect(fetchMock).not.toHaveBeenCalled(); // 没点开就不该发请求
    const more = wrapper.findAll("button").find((b) => b.text().includes("查看全部 100 次"));
    expect(more).toBeTruthy();
    await more.trigger("click");
    await flush();

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/api/exam/tk/attempts");
    expect(url).toContain("page=1");
    expect(url).toContain("size=20");
    expect(wrapper.find(".history-all").findAll(".history-row")).toHaveLength(20);
    expect(wrapper.find(".history-pager").text()).toContain("1 / 5");
  });

  it("翻页请求下一页，不是前端切片", async () => {
    let requested = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        requested = Number(new URL(String(url), "http://x").searchParams.get("page"));
        return { ok: true, status: 200, json: async () => historyPage(requested) };
      }),
    );
    const wrapper = mount(ExamLobby, { props: { entry: entryPayload(), token: "tk" } });
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("查看全部"))
      .trigger("click");
    await flush();

    await wrapper.findAll(".history-pager button").at(1).trigger("click");
    await flush();
    expect(requested).toBe(2);
    expect(wrapper.find(".history-pager").text()).toContain("2 / 5");
  });

  it("成绩未公开时不显示分数，也不指认哪次最好", async () => {
    const entry = entryPayload();
    entry.attempts.summary.best = null;
    entry.attempts.summary.counted_attempt_id = null;
    entry.attempts.history = entry.attempts.history.map(({ total_score, ...rest }) => ({
      ...rest,
      counted: false,
    }));
    const wrapper = mount(ExamLobby, { props: { entry, token: "tk" } });

    expect(wrapper.find(".history-summary").text()).not.toContain("最好成绩");
    expect(wrapper.find(".history-row").text()).toContain("已完成");
    expect(wrapper.find(".history-flag").exists()).toBe(false);
  });

  it("进行中的那次置顶且不给「查看」按钮", async () => {
    const entry = entryPayload();
    entry.attempts.ongoing_attempt_id = 101;
    entry.attempts.history = [attempt(101, { status: "ongoing" }), ...entry.attempts.history];
    const wrapper = mount(ExamLobby, { props: { entry, token: "tk" } });

    const first = wrapper.findAll(".history-row")[0];
    expect(first.classes()).toContain("is-ongoing");
    expect(first.text()).toContain("进行中");
    expect(first.find("button").exists()).toBe(false);
  });
});
