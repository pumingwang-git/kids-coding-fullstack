// @vitest-environment jsdom
// 课时作业的题目列表看板：清单渲染、逐题累计通过状态、开始挑战锚点。
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import HomeworkBoard from "../src/components/exam/HomeworkBoard.vue";

function question(no, overrides = {}) {
  return {
    sort_order: no,
    problem_id_no: `Q9000${no}`,
    score: 10,
    title: `第 ${no} 题`,
    type: "programming",
    difficulty: "普及/提高-",
    source: "第三方",
    knowledge: ["图论算法"],
    answered: false,
    passed: false,
    ...overrides,
  };
}

function entryPayload(overrides = {}) {
  return {
    paper: {
      title: "课后作业",
      paper_type: "作业卷",
      question_count: 2,
      total_score: 20,
      questions: [question(1), question(2)],
    },
    link: { name: "课后练习", close_at: null, notice: "" },
    attempts: {
      used: 1,
      limit: 0,
      ongoing_attempt_id: null,
      history: [
        {
          attempt_id: 7,
          attempt_no: 1,
          status: "submitted",
          started_at: "2026-08-15T01:00:00+00:00",
          submitted_at: "2026-08-15T01:30:00+00:00",
          duration_seconds: 1800,
          total_score: 10,
          counted: true,
        },
      ],
      summary: { count: 1, counted_attempt_id: 7, score_policy: "best", has_more: false },
    },
    phase: "open",
    can_start: true,
    blocked_reason: null,
    ...overrides,
  };
}

describe("课时作业题目列表看板", () => {
  it("渲染题目清单：名称、知识点、难度、分值", () => {
    const wrapper = mount(HomeworkBoard, { props: { entry: entryPayload() } });
    const text = wrapper.text();
    expect(text).toContain("第 1 题");
    expect(text).toContain("图论算法");
    expect(text).toContain("普及/提高-");
    expect(wrapper.findAll(".hw-table tbody tr")).toHaveLength(2);
  });

  it("逐题状态直接读大纲的 passed/answered，进度条同步", () => {
    const entry = entryPayload();
    entry.paper.questions = [
      question(1, { answered: true, passed: true }),
      question(2, { answered: true, passed: false }),
    ];
    const wrapper = mount(HomeworkBoard, { props: { entry } });
    expect(wrapper.text()).toContain("1 / 2");
    expect(wrapper.text()).toContain("✓ 已通过");
    expect(wrapper.text()).toContain("✗ 未通过");
  });

  it("没作答过的题显示 —，不显示 ✗", () => {
    const entry = entryPayload();
    entry.paper.questions = [
      question(1, { answered: true, passed: true }),
      question(2), // answered: false
    ];
    const wrapper = mount(HomeworkBoard, { props: { entry } });
    const statuses = wrapper.findAll(".hw-status");
    expect(statuses[0].text()).toBe("✓ 已通过");
    expect(statuses[1].text()).toBe("—");
  });

  it("成绩不公开（大纲不带 passed 键）时不编造逐题对错", () => {
    const entry = entryPayload();
    entry.paper.questions = [questionWithoutStatus(1), questionWithoutStatus(2)];
    const wrapper = mount(HomeworkBoard, { props: { entry } });
    expect(wrapper.text()).not.toContain("✓ 已通过");
    expect(wrapper.text()).toContain("不公开逐题对错");
  });

  function questionWithoutStatus(no) {
    const q = question(no);
    delete q.answered;
    delete q.passed;
    return q;
  }

  it("开始挑战 emit 该题编号，开始作答 emit null", async () => {
    const wrapper = mount(HomeworkBoard, { props: { entry: entryPayload() } });
    await wrapper.findAll(".hw-challenge")[1].trigger("click");
    expect(wrapper.emitted("start")[0]).toEqual(["Q90002"]);
    const primary = wrapper.findAll(".hw-foot .btn-primary")[0];
    await primary.trigger("click");
    expect(wrapper.emitted("start")[1]).toEqual([null]);
  });

  it("全部通过后进入收尾状态：欢呼语 + 完成练习按钮", async () => {
    const entry = entryPayload();
    entry.paper.questions = [
      question(1, { answered: true, passed: true }),
      question(2, { answered: true, passed: true }),
    ];
    const wrapper = mount(HomeworkBoard, { props: { entry } });
    expect(wrapper.text()).toContain("2 / 2");
    expect(wrapper.text()).toContain("全部通过 🎉");
    const finish = wrapper.find(".hw-finish");
    expect(finish.exists()).toBe(true);
    await finish.trigger("click");
    expect(wrapper.emitted("back")).toBeTruthy();
  });

  it("blocked 时挑战与作答都不可点", () => {
    const wrapper = mount(HomeworkBoard, {
      props: { entry: entryPayload({ can_start: false, blocked_reason: "考试已结束。" }) },
    });
    expect(wrapper.find(".notice-box").text()).toContain("考试已结束");
    for (const btn of wrapper.findAll(".hw-challenge")) {
      expect(btn.attributes("disabled")).toBeDefined();
    }
  });
});
