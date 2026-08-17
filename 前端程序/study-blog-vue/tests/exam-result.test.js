// @vitest-environment jsdom
// 结果页（排行榜 + 编程题代码回看）与考试页隐藏全站导航的验证。
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter, RouterLinkStub } from "vue-router";
import App from "../src/App.vue";
import ExamResult from "../src/components/exam/ExamResult.vue";

const flush = () => new Promise((resolve) => setTimeout(resolve, 30));

function resultPayload({ leaderboard_enabled = true } = {}) {
  return {
    attempt: {
      id: 1, attempt_no: 1, status: "submitted", submitted_at: "2026-08-07T00:00:00+00:00",
      submit_kind: "manual", duration_seconds: 125, total_score: 80,
    },
    paper: { title: "期中卷", paper_type: "测试卷", total_score: 100 },
    show_score: true,
    show_analysis: true,
    leaderboard_enabled,
    questions: [
      {
        sort_order: 0, problem_id_no: "Q1", full_score: 20, missing: false,
        type: "programming", stem: "A+B", score: 20, is_correct: true,
        judge_status: "judged",
        programming: { pass_condition: "全测试点通过" },
        last_submission: {
          id: 9, kind: "submit", language: "python", status: "accepted",
          compile_message: "", created_at: "2026-08-07T00:00:00+00:00",
          cases: [
            { index: 0, status: "accepted", passed: true, time_ms: 1, memory_kb: 100,
              is_sample: true, input: "1 2", expected: "3", actual: "3" },
          ],
          time_ms: 1, memory_kb: 100, score: 20, code: "print(3)",
        },
      },
    ],
    server_now: "2026-08-07T00:01:00+00:00",
  };
}

function leaderboardPayload() {
  return {
    entries: [
      { rank: 1, username: "alice", total_score: 90, duration_seconds: 300 },
      { rank: 2, username: "bob", total_score: 80, duration_seconds: 125 },
    ],
    me: { rank: 2, username: "bob", total_score: 80, duration_seconds: 125 },
    participant_count: 2,
  };
}

/** 按 URL 分流：榜单一个响应、成绩一个响应。GET 不需要 CSRF。 */
function mockExamApi({ leaderboardStatus = 200, leaderboardEnabled = true } = {}) {
  vi.stubGlobal("fetch", vi.fn(async (url) => {
    if (String(url).includes("/leaderboard")) {
      const ok = leaderboardStatus < 400;
      return {
        ok, status: leaderboardStatus,
        json: async () => (ok ? leaderboardPayload() : { detail: "本场考试的成绩暂不公布，暂无排行榜。" }),
      };
    }
    return { ok: true, status: 200, json: async () => resultPayload({ leaderboard_enabled: leaderboardEnabled }) };
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("结果页", () => {
  it("成绩排名页签：名次/用户名/分数齐全，自己那行高亮并给出总排名", async () => {
    mockExamApi();
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    const tabs = wrapper.findAll(".result-tabs button");
    expect(tabs.map((b) => b.text())).toEqual(["答题详情", "成绩排名"]);

    // 切到成绩排名页签
    await tabs[1].trigger("click");
    expect(wrapper.text()).toContain("2 人已交卷");
    expect(wrapper.text()).toContain("alice");
    expect(wrapper.text()).toContain("你的排名：第 2 / 2 名");
    const mine = wrapper.find(".board-row.is-me");
    expect(mine.exists()).toBe(true);
    expect(mine.text()).toContain("bob");
  });

  it("成绩未公开（榜单 403）时不渲染排名页签，但成绩本身不受影响", async () => {
    mockExamApi({ leaderboardStatus: 403 });
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    expect(wrapper.find(".result-tabs").exists()).toBe(false);
    expect(wrapper.find(".board-row").exists()).toBe(false);
    expect(wrapper.text()).toContain("80"); // 总分照常显示
  });

  it("不允许公开排名的入口不请求排行榜", async () => {
    mockExamApi({ leaderboardEnabled: false });
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    expect(wrapper.find(".result-tabs").exists()).toBe(false);
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/leaderboard"))).toBe(false);
  });

  it("答题详情页签里有导出成绩单按钮，打印用成绩单只含凭证信息", async () => {
    mockExamApi();
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    expect(wrapper.find(".transcript-actions").text()).toContain("导出成绩单");

    const transcript = wrapper.find(".transcript");
    expect(transcript.exists()).toBe(true);
    expect(transcript.text()).toContain("考试成绩单");
    expect(transcript.text()).toContain("80 / 100 分");
    expect(transcript.text()).toContain("第 2 / 2 名");
    // 成绩单是凭证不是答案纸：解析与代码不能进打印块
    expect(transcript.text()).not.toContain("print(3)");
    expect(wrapper.findAll(".transcript-actions button")).toHaveLength(2);
    expect(wrapper.find(".transcript-detail").exists()).toBe(false);

    await wrapper.findAll(".transcript-actions button")[1].trigger("click");
    expect(wrapper.find(".transcript-detail").exists()).toBe(true);
  });

  it("编程题交卷后能回看自己提交的代码与判题状态", async () => {
    mockExamApi();
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    expect(wrapper.find(".code-view").text()).toBe("print(3)");
    expect(wrapper.find('[data-testid="verdict-abbr"]').text()).toBe("AC"); // 判定摘要
  });
});

// ==================== 我的答案 ====================

/** 客观题 + 填空题各一道，用来验证「我的答案」的渲染。 */
function answersPayload() {
  const payload = resultPayload();
  payload.questions = [
    {
      sort_order: 0, problem_id_no: "Q2", full_score: 10, missing: false,
      type: "choice", stem: "输出用哪个函数？", score: 0, is_correct: false,
      judge_status: "judged",
      options: [
        { label: "A", content: "input()" },
        { label: "B", content: "print()" },
      ],
      answer: { type: "choice", picked: "A" },
      correct: { labels: ["B"] },
    },
    {
      sort_order: 1, problem_id_no: "Q3", full_score: 10, missing: false,
      type: "fill", stem: "填空", score: 5, is_correct: false, judge_status: "judged",
      blank_keys: ["b1", "b2"],
      answer: { type: "fill", blanks: { b1: "0.5", b2: "错的" } },
      detail: { blanks: [{ blank_key: "b1", correct: true }, { blank_key: "b2", correct: false }] },
      correct: { blanks: [{ blank_key: "b1", answer: "1/2" }, { blank_key: "b2", answer: "对的" }] },
    },
  ];
  return payload;
}

describe("结果页的「我的答案」", () => {
  function mockAnswers() {
    vi.stubGlobal("fetch", vi.fn(async (url) => {
      if (String(url).includes("/leaderboard"))
        return { ok: false, status: 403, json: async () => ({ detail: "暂无排行榜。" }) };
      return { ok: true, status: 200, json: async () => answersPayload() };
    }));
  }

  it("选择题显示自己选的那项正文，而不是光秃秃一个字母", async () => {
    mockAnswers();
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    const box = wrapper.findAll(".answer-box")[0];
    expect(box.text()).toContain("我的答案");
    expect(box.text()).toContain("A. input()"); // 自己选的
    expect(box.text()).toContain("B. print()"); // 参考答案
    // 答错了要标出来，否则"我的答案"和"参考答案"两行长得一样，得逐字比对
    expect(box.find(".answer-wrong").exists()).toBe(true);
  });

  it("填空题逐空显示，对错分别标记", async () => {
    mockAnswers();
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    const chips = wrapper.findAll(".answer-box")[1].findAll(".blank-chip");
    expect(chips[0].text()).toContain("0.5");
    expect(chips[0].classes()).toContain("is-right");
    expect(chips[1].text()).toContain("错的");
    expect(chips[1].classes()).toContain("is-wrong");
    // 参考答案也逐空给，不再把多个空糊成 "1/2 / 对的"
    expect(chips[2].text()).toContain("1/2");
  });

  it("没作答的空显示成「未作答」而不是空白", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url) => {
      if (String(url).includes("/leaderboard"))
        return { ok: false, status: 403, json: async () => ({}) };
      const payload = answersPayload();
      payload.questions[1].answer = { type: "fill", blanks: {} };
      payload.questions[0].answer = undefined;
      return { ok: true, status: 200, json: async () => payload };
    }));
    const wrapper = mount(ExamResult, { props: { attemptId: 1 } });
    await flush();

    expect(wrapper.findAll(".answer-box")[0].text()).toContain("未作答");
    expect(wrapper.findAll(".answer-box")[1].findAll(".blank-chip")[0].text()).toContain("未作答");
  });
});

describe("全站导航栏", () => {
  async function mountAppAt(path) {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, status: 200, json: async () => ({}),
    })));
    const dummy = { template: "<div />" };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", name: "blog", component: dummy },
        { path: "/exam/:token", name: "exam", component: dummy },
      ],
    });
    router.push(path);
    await router.isReady();
    return mount(App, {
      global: { plugins: [router], stubs: { RouterLink: RouterLinkStub } },
    });
  }

  it("考试路由下隐藏顶栏，普通页面恢复显示", async () => {
    const onExam = await mountAppAt("/exam/some-token");
    expect(onExam.find(".app-header").exists()).toBe(false);

    const onHome = await mountAppAt("/");
    expect(onHome.find(".app-header").exists()).toBe(true);
  });
});
