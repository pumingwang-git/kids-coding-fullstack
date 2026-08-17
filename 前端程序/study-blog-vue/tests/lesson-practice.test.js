// @vitest-environment jsdom
// 课中练习块（形态 A · 块内直答）护栏，对应交接文档 15 第三节。
//
// 核心断言：
// - 复用考试页的 QuestionChoice / QuestionFill，题干走 Markdown 管线；
// - 前端**不做任何判分**：判定与解析全部来自服务端响应；
// - 提交后作答区锁死、判定出现、`answered` 事件把进度刷新交回给壳；
// - 次数用完后不再给「再试一次」。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("../src/services/auth", () => ({ request: vi.fn() }));

import BlockPractice from "../src/components/lesson/blocks/BlockPractice.vue";
import { request } from "../src/services/auth";

const settle = () => new Promise((r) => setTimeout(r, 0));

const CHOICE_QUESTION = {
  uid: "block-7",
  type: "choice",
  sub_type: null,
  stem: "C++ 程序从哪里**开始执行**？",
  options: [
    { label: "A", content: "main 函数" },
    { label: "B", content: "第一行 #include" },
  ],
};

function problemResponse(over = {}) {
  return {
    block_id: 7,
    title: "课中练习",
    question: CHOICE_QUESTION,
    display_no: "1",
    score: 10,
    attempt_limit: 2,
    tries: 0,
    tries_left: 2,
    can_answer: true,
    answer: null,
    submitted: false,
    ...over,
  };
}

function mountBlock() {
  return mount(BlockPractice, {
    props: { block: { id: 7, title: "课中练习", block_type: "practice" }, lessonId: 1 },
    global: { stubs: { LessonIcon: true } },
  });
}

describe("BlockPractice 取题与渲染", () => {
  beforeEach(() => request.mockReset());

  it("题干走 Markdown 渲染，选项复用 QuestionChoice", async () => {
    request.mockResolvedValue(problemResponse());
    const wrapper = mountBlock();
    await settle();

    expect(wrapper.find(".practice-stem").html()).toContain("<strong>开始执行</strong>");
    const options = wrapper.findAll(".option");
    expect(options).toHaveLength(2);
    expect(options[0].text()).toContain("main 函数");
    // 未提交时不该有任何判定
    expect(wrapper.find(".practice-verdict").exists()).toBe(false);
  });

  it("容器带 .qz —— 题目样式靠它生效（question.css 两个壳共用）", async () => {
    request.mockResolvedValue(problemResponse());
    const wrapper = mountBlock();
    await settle();
    expect(wrapper.find(".block-practice").classes()).toContain("qz");
  });

  it("未作答时提交按钮禁用", async () => {
    request.mockResolvedValue(problemResponse());
    const wrapper = mountBlock();
    await settle();
    const submit = wrapper.findAll("button").find((b) => b.text().includes("提交答案"));
    expect(submit.attributes("disabled")).toBeDefined();
  });
});

describe("BlockPractice 提交与判定", () => {
  beforeEach(() => request.mockReset());

  it("判定与解析完全来自服务端，前端不判分", async () => {
    request.mockResolvedValueOnce(problemResponse());
    const wrapper = mountBlock();
    await settle();

    // 选 B（客观上错），但服务端说对——前端必须照服务端的说
    request.mockResolvedValueOnce({
      ...problemResponse({ tries: 1, tries_left: 1, submitted: true }),
      verdict: { score: 10, is_correct: true, detail: {}, analysis: "服务端下发的解析" },
    });
    await wrapper.findAll(".option")[1].trigger("click");
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("提交答案"))
      .trigger("click");
    await settle();

    const verdict = wrapper.find(".practice-verdict");
    expect(verdict.exists()).toBe(true);
    expect(verdict.classes()).not.toContain("is-bad");
    expect(verdict.text()).toContain("回答正确 +10 分");
    expect(wrapper.find(".practice-analysis").html()).toContain("服务端下发的解析");
    // 提交成功要通知壳刷新进度
    expect(wrapper.emitted("answered")).toHaveLength(1);
  });

  it("提交后作答区锁死，防止学生以为还能改", async () => {
    request.mockResolvedValueOnce(problemResponse());
    const wrapper = mountBlock();
    await settle();
    request.mockResolvedValueOnce({
      ...problemResponse({ tries: 1, tries_left: 1, submitted: true }),
      verdict: { score: 0, is_correct: false, detail: {} },
    });
    await wrapper.findAll(".option")[0].trigger("click");
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("提交答案"))
      .trigger("click");
    await settle();

    expect(wrapper.find(".practice-answer").classes()).toContain("is-locked");
    expect(wrapper.find(".practice-verdict").classes()).toContain("is-bad");
  });

  // 2026-08-12（文档 18 §2.4）：「再试一次」换成「重做本题」。
  // 旧按钮只在**答错且有余次**时出现，而且只清本地 submitted——次数与作答都在服务端，
  // 刷新一次就打回"已提交"，是个不起作用的按钮。新的走 POST …/reset。
  it("交过就给「重做本题」——答对的人也要能复习", async () => {
    request.mockResolvedValueOnce(problemResponse());
    const wrapper = mountBlock();
    await settle();

    request.mockResolvedValueOnce({
      ...problemResponse({ tries: 1, tries_left: 1, submitted: true, can_answer: true }),
      verdict: { score: 10, is_correct: true, detail: {} },
    });
    await wrapper.findAll(".option")[0].trigger("click");
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("提交答案"))
      .trigger("click");
    await settle();
    expect(wrapper.text()).toContain("重做本题");
    expect(wrapper.text()).toContain("重做不消耗次数");
  });

  it("次数用完仍能重做，但文案说明不计分——复习和刷分是两件事", async () => {
    request.mockResolvedValue({
      ...problemResponse({ tries: 2, tries_left: 0, submitted: true, can_answer: false }),
      verdict: { score: 0, is_correct: false, detail: {} },
    });
    const wrapper = mountBlock();
    await settle();
    expect(wrapper.text()).toContain("重做本题（不计分）");
    expect(wrapper.text()).toContain("成绩不再更新");
  });

  it("重做要点两次才生效，且走服务端 reset 而不是只清本地", async () => {
    request.mockResolvedValueOnce({
      ...problemResponse({ tries: 1, tries_left: 1, submitted: true, can_answer: true }),
      verdict: { score: 0, is_correct: false, detail: {} },
    });
    const wrapper = mountBlock();
    await settle();

    const resetBtn = () =>
      wrapper.findAll("button").find((b) => /重做本题|再点一次/.test(b.text()));
    await resetBtn().trigger("click");
    await settle();
    // 第一下只进确认态，绝不能直接把作答清掉
    expect(resetBtn().text()).toContain("再点一次");
    expect(request.mock.calls.some(([url]) => url.endsWith("/reset"))).toBe(false);

    request.mockResolvedValueOnce(
      problemResponse({ tries: 1, tries_left: 1, submitted: false, answer: null }),
    );
    await resetBtn().trigger("click");
    await settle();

    const call = request.mock.calls.find(([url]) => url.endsWith("/reset"));
    expect(call).toBeTruthy();
    expect(call[1].method).toBe("POST");
    expect(wrapper.find(".practice-verdict").exists()).toBe(false);
    expect(wrapper.find(".practice-answer").classes()).not.toContain("is-locked");
  });

  it("自测态给「查看解析」，默认收起——点开才看得到", async () => {
    // 次数用尽 + 已重做：submitted=false、can_answer=false，服务端补下发 self_test 与
    // analysis。没有这个出口的话，学生答完既提交不了也对不了答案，重做就是条死路。
    request.mockResolvedValue(
      problemResponse({
        tries: 2,
        tries_left: 0,
        submitted: false,
        can_answer: false,
        self_test: true,
        analysis: "自测参考：入口是 main。",
      }),
    );
    const wrapper = mountBlock();
    await settle();

    // 一进来先不摊开——否则学生还没作答就看到答案，自测就变回了看答案
    expect(wrapper.text()).not.toContain("自测参考：入口是 main。");
    const btn = wrapper.findAll("button").find((b) => b.text() === "查看解析");
    expect(btn).toBeTruthy();

    await btn.trigger("click");
    expect(wrapper.find(".practice-verdict.is-selftest").exists()).toBe(true);
    expect(wrapper.text()).toContain("自测参考：入口是 main。");
    // 自测态没有判定：不能出现"回答正确/错误"那套对错信号
    expect(wrapper.text()).not.toContain("回答正确");
    expect(wrapper.text()).not.toContain("回答错误");
  });

  it("服务端没给解析时，自测态不摆一个点不出东西的按钮", async () => {
    // show_analysis=false 的题，服务端不下发 self_test/analysis。
    // 前端若只看 can_answer 就摆按钮，点开会是一片空白。
    request.mockResolvedValue(
      problemResponse({ tries: 2, tries_left: 0, submitted: false, can_answer: false }),
    );
    const wrapper = mountBlock();
    await settle();
    expect(wrapper.findAll("button").some((b) => b.text() === "查看解析")).toBe(false);
    expect(wrapper.text()).toContain("次数已用完，现在作答仅供自测，不计分");
  });

  it("已答过的题重新进来，带回上次作答与判定", async () => {
    request.mockResolvedValue({
      ...problemResponse({ tries: 1, tries_left: 1, submitted: true, answer: { picked: "B" } }),
      verdict: { score: 0, is_correct: false, detail: {} },
    });
    const wrapper = mountBlock();
    await settle();
    expect(wrapper.find(".practice-verdict").exists()).toBe(true);
    expect(wrapper.findAll(".option")[1].classes()).toContain("is-picked");
  });
});
