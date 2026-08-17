// @vitest-environment jsdom
// 课时内编程题工作区（形态 B）护栏，对应交接文档 15 §4 与文档 18 §3.1。
//
// 核心断言：
// - 直接复用考试页的 QuestionCoding，不重写双栏工作区；
// - **两条链路分得开**：kind=trial → POST /run（不计分），kind=submit → POST /submit
//   （跑全部测试点、计分、判完写完成度）。这两个的区别是整个课时编程题的核心口径；
// - 提交记录弹窗是考试页独有的（按 attempt 查），课时页 allowHistory=false；
// - 次数用尽时只锁提交、不锁运行——调试是学习的一部分；
// - 代码草稿会自动存（draft-change → PUT /draft），切块不丢。
//
// 2026-08-12 改写：本文件此前钉的是「课时里隐藏提交判题、submit 一律 reject」的旧契约，
// 那正是文档 18 要修的缺陷（当时的注释写"计分依赖 X1"，而 X1 早已落地）。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("../src/services/auth", () => ({ request: vi.fn() }));

import PracticeCoding from "../src/components/lesson/blocks/PracticeCoding.vue";
import QuestionCoding from "../src/components/exam/QuestionCoding.vue";
import { request } from "../src/services/auth";

const CODING_QUESTION = {
  uid: "block-8",
  type: "programming",
  sub_type: "cpp",
  stem: "读入两个整数，输出和。",
  programming: {
    title: "A + B",
    input_format: "两个整数",
    output_format: "一个整数",
    hints: "",
    time_limit_ms: 1000,
    memory_limit_mb: 256,
    pass_condition: "全测试点通过",
    samples: [{ input: "1 2\n", output: "3\n" }],
  },
};

function mountCoding(props = {}) {
  return mount(PracticeCoding, {
    props: { question: CODING_QUESTION, blockId: 8, lessonId: 1, ...props },
  });
}

describe("PracticeCoding 复用考试页工作区", () => {
  beforeEach(() => request.mockReset());

  it("挂的是 QuestionCoding，计分提交开着、提交记录关着", () => {
    const wrapper = mountCoding();
    const coding = wrapper.findComponent(QuestionCoding);
    expect(coding.exists()).toBe(true);
    // 课时里能计分提交（判定写回 lesson_problem_attempts，不经 PaperAttempt）
    expect(coding.props("allowSubmit")).toBe(true);
    // 但没有「提交记录」——那个弹窗按 attempt 查历史，课时侧没有 attempt。
    // 两个开关必须分开：合成一个的话，要么丢掉提交、要么挂一个点了必然报错的按钮。
    expect(coding.props("allowHistory")).toBe(false);
  });

  it("把没有 problem_id_no 的课时 DTO 适配成 QuestionCoding 要的形状", () => {
    const wrapper = mountCoding();
    const passed = wrapper.findComponent(QuestionCoding).props("question");
    // 课时 DTO 按保密红线不下发 problem_id_no，用 uid 兜底（只做切题 watch 键）
    expect(passed.problem_id_no).toBe("block-8");
    expect(passed.programming.samples).toHaveLength(1);
  });

  it("给出「▶ 运行」与「提交判题」，但没有「提交记录」", () => {
    const wrapper = mountCoding();
    const labels = wrapper.findAll("button").map((b) => b.text());
    expect(labels.some((t) => t.includes("运行"))).toBe(true);
    expect(labels.some((t) => t.includes("提交判题"))).toBe(true);
    expect(labels.some((t) => t.includes("提交记录"))).toBe(false);
  });

  it("次数用尽：只禁用提交，运行照常可用", () => {
    const wrapper = mountCoding({ canAnswer: false, triesLeft: 0 });
    expect(wrapper.findComponent(QuestionCoding).props("submitDisabled")).toBe(true);
    const submit = wrapper.findAll("button").find((b) => b.text().includes("提交判题"));
    const run = wrapper.findAll("button").find((b) => b.text().includes("运行"));
    expect(submit.attributes("disabled")).toBeDefined();
    expect(run.attributes("disabled")).toBeUndefined();
    expect(wrapper.text()).toContain("仍可运行调试");
  });

  it("剩余次数写进操作条文案，学员不必去别处数", () => {
    const wrapper = mountCoding({ canAnswer: true, triesLeft: 2 });
    expect(wrapper.text()).toContain("还可提交 2 次");
  });
});

describe("PracticeCoding 的运行适配", () => {
  beforeEach(() => request.mockReset());

  it("run 走课时侧接口；一次返回终态就不再轮询", async () => {
    request.mockResolvedValue({ run_id: 9, status: "accepted", done: true, cases: [] });
    const wrapper = mountCoding();
    const resolved = [];
    await wrapper.findComponent(QuestionCoding).vm.$emit("run", {
      kind: "trial",
      language: "cpp",
      code: "int main(){}",
      resolve: (v) => resolved.push(v),
      reject: () => {},
    });
    await new Promise((r) => setTimeout(r, 0));

    expect(request).toHaveBeenCalledTimes(1);
    const [url, opts] = request.mock.calls[0];
    expect(url).toBe("/api/lessons/1/blocks/8/run");
    expect(opts.method).toBe("POST");
    expect(JSON.parse(opts.body)).toMatchObject({ scope: "samples", language: "cpp" });
    expect(resolved[0].status).toBe("accepted");
  });

  it("自定义输入走 scope=custom", async () => {
    request.mockResolvedValue({ run_id: 9, status: "accepted", done: true, cases: [] });
    const wrapper = mountCoding();
    await wrapper.findComponent(QuestionCoding).vm.$emit("run", {
      kind: "trial",
      language: "cpp",
      code: "x",
      customInput: "5 6\n",
      resolve: () => {},
      reject: () => {},
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(JSON.parse(request.mock.calls[0][1].body)).toMatchObject({
      scope: "custom",
      custom_input: "5 6\n",
    });
  });

  it("计分提交走 /submit（不是 /run），判完向上 emit graded", async () => {
    request.mockResolvedValue({
      run_id: 11,
      status: "accepted",
      done: true,
      scored: true,
      score: 20,
      is_correct: true,
      cases: [],
    });
    const wrapper = mountCoding();
    const resolved = [];
    await wrapper.findComponent(QuestionCoding).vm.$emit("run", {
      kind: "submit",
      language: "cpp",
      code: "cout<<1;",
      resolve: (v) => resolved.push(v),
      reject: () => {},
    });
    await new Promise((r) => setTimeout(r, 0));

    const submitCall = request.mock.calls.find(([url]) => url.endsWith("/submit"));
    expect(submitCall).toBeTruthy();
    expect(submitCall[0]).toBe("/api/lessons/1/blocks/8/submit");
    expect(submitCall[1].method).toBe("POST");
    // 提交体里不带 scope：跑哪些测试点由服务端定，前端说了不算
    expect(JSON.parse(submitCall[1].body)).toEqual({ language: "cpp", code: "cout<<1;" });
    expect(resolved[0].score).toBe(20);
    // 成绩、次数、完成度、后续块解锁都在这一刻变，壳要靠这个事件去刷
    expect(wrapper.emitted("graded")).toBeTruthy();
  });

  it("提交失败照原样 reject，不吞掉——工作区要出中性告警横幅", async () => {
    // Once 而不是 mockRejectedValue：后者让**每一次** request 都返回一个新的被拒
    // promise，组件里那些故意 fire-and-forget 的调用（草稿暂存等）会变成未处理拒绝，
    // 测试失败的原因就不再是被测行为本身了。
    request.mockRejectedValueOnce(new Error("本题作答次数已用完。"));
    const wrapper = mountCoding();
    let rejected = null;
    await wrapper.findComponent(QuestionCoding).vm.$emit("run", {
      kind: "submit",
      language: "cpp",
      code: "x",
      resolve: () => {},
      reject: (e) => {
        rejected = e;
      },
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(rejected?.message).toContain("次数已用完");
    expect(wrapper.emitted("graded")).toBeFalsy();
  });
});

describe("PracticeCoding 的代码草稿", () => {
  beforeEach(() => request.mockReset());

  it("draft-change 会防抖存到服务端——切块销毁编辑器也不丢代码", async () => {
    vi.useFakeTimers();
    request.mockResolvedValue({ saved: true });
    const wrapper = mountCoding();
    await wrapper
      .findComponent(QuestionCoding)
      .vm.$emit("draft-change", { language: "cpp", code: "写到一半" });

    // 防抖窗口内不该发请求（狂敲键盘时每个字符一次请求是不可接受的）
    expect(request).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1600);

    const draftCall = request.mock.calls.find(([url]) => url.endsWith("/draft"));
    expect(draftCall).toBeTruthy();
    expect(draftCall[1].method).toBe("PUT");
    expect(JSON.parse(draftCall[1].body)).toMatchObject({ code: "写到一半" });
    vi.useRealTimers();
  });
});
