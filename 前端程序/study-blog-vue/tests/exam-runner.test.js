// @vitest-environment jsdom
// 作答页组件层的护栏。这里盯的都是"改 UI 时最容易顺手弄坏、坏了又不会报错"的东西：
// 隐藏测试点的内容有没有漏出去、feedback_mode 三态分不分得清、编译型题会不会
// 还渲染测试点表格、自测有没有把 custom_input 带上。

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import {
  casesVisible,
  firstDiffIndex,
  isCompileOnly,
  metricText,
  splitDiff,
  verdictOf,
} from "../src/services/verdict.js";
import ExamSidebar from "../src/components/exam/ExamSidebar.vue";
import QuestionCoding from "../src/components/exam/QuestionCoding.vue";
import SubmissionDetail from "../src/components/exam/SubmissionDetail.vue";

// jsdom 没有 clipboard，SubmissionDetail 的复制按钮会用到。
if (!navigator.clipboard) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn() }, writable: true });
}
// jsdom 不做排版，CodeMirror 量光标位置时会撞上缺失的 Range.getClientRects。
// 它只影响渲染细节，不影响我们要断言的那些 DOM，补个空实现把噪音压掉。
if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => ({
    length: 0,
    item: () => null,
    [Symbol.iterator]: function* () {},
  });
  Range.prototype.getBoundingClientRect = () => ({
    x: 0,
    y: 0,
    width: 0,
    height: 0,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  });
}

// QuestionCoding 的结果详情通过 Teleport 挂到考试页根容器。组件单测也要提供同样
// 的宿主，否则 Vue 会把缺失目标报告为组件更新异常，掩盖真正的交互断言。
beforeEach(() => {
  document.body.innerHTML = '<div class="qz"></div>';
});
afterEach(() => {
  window.dispatchEvent(new MouseEvent("pointercancel"));
});

// ==================== 判定映射与差异高亮 ====================

describe("verdict 映射", () => {
  it("六种判定各有自己的缩写与横幅类", () => {
    const statuses = [
      "accepted",
      "wrong_answer",
      "time_limit",
      "memory_limit",
      "runtime_error",
      "compile_error",
    ];
    expect(statuses.map((status) => verdictOf(status).abbr)).toEqual([
      "AC",
      "WA",
      "TLE",
      "MLE",
      "RE",
      "CE",
    ]);
    // 横幅类互不相同，否则六种判定会长成一个样
    const banners = statuses.map((status) => verdictOf(status).banner);
    expect(new Set(banners).size).toBe(banners.length);
  });

  it("判题异常不说「答案错误」——那是把系统故障赖给学员", () => {
    expect(verdictOf("judge_failed").text).toBe("判题异常");
    expect(verdictOf("failed").text).toBe("判题异常");
    expect(verdictOf("judge_failed").text).not.toContain("错误");
  });

  it("未知状态不崩，也不冒充成某种判定", () => {
    expect(verdictOf("brand_new_status").abbr).toBe("?");
    expect(verdictOf(undefined).abbr).toBe("?");
  });

  it("null 的时间与内存显示成 --，不能显示 0", () => {
    expect(metricText(null, "ms")).toBe("--");
    expect(metricText(0, "ms")).toBe("0ms");
  });
});

describe("首处差异高亮", () => {
  it("一致时不高亮", () => {
    expect(firstDiffIndex("abc", "abc")).toBe(-1);
    expect(splitDiff("abc", "abc").matched).toBe(true);
  });

  it("指出第一个不同的字符位置", () => {
    expect(firstDiffIndex("dc ba", "ab cd")).toBe(0);
    expect(firstDiffIndex("hello", "hellp")).toBe(4);
    const parts = splitDiff("hello", "hellp");
    expect(parts.head).toBe("hell");
    expect(parts.mark).toBe("p");
  });

  it("实际输出比期望短时用可见占位符，不高亮出一段空白", () => {
    const parts = splitDiff("hello", "hel");
    expect(parts.matched).toBe(false);
    expect(parts.mark).toBe("␣");
  });

  it("隐藏测试点（期望为 null）不参与比对", () => {
    expect(firstDiffIndex(null, null)).toBe(-1);
    expect(splitDiff(null, null).matched).toBe(true);
  });
});

describe("feedback_mode 三态", () => {
  it("cases 键不下发时是「暂不可见」，不是「没有测试点」", () => {
    // 后端在 compile_only / after_close 未到点时整个不给 cases 键
    expect(casesVisible({ status: "accepted" })).toBe(false);
    // 给了空数组才是「真的一个测试点都没有」
    expect(casesVisible({ status: "accepted", cases: [] })).toBe(true);
    expect(casesVisible(null)).toBe(false);
  });

  it("满分条件=编译通过 才算编译型题", () => {
    expect(isCompileOnly({ programming: { pass_condition: "编译通过" } })).toBe(true);
    expect(isCompileOnly({ programming: { pass_condition: "全测试点通过" } })).toBe(false);
    expect(isCompileOnly({})).toBe(false);
  });
});

// ==================== 答题卡 ====================

function makeQuestions(count, type = "choice") {
  return Array.from({ length: count }, (_, index) => ({
    problem_id_no: `Q${index + 1}`,
    type,
    score: 5,
  }));
}

function mountSidebar(questions, { answered = [], marked = [] } = {}) {
  return mount(ExamSidebar, {
    props: {
      questions,
      currentIndex: 0,
      answeredKeys: new Set(answered),
      markedKeys: new Set(marked),
      playful: false,
    },
  });
}

describe("答题卡过滤", () => {
  it("三个开关的计数与实际筛选结果一致", async () => {
    const wrapper = mountSidebar(makeQuestions(5), { answered: ["Q1", "Q2"], marked: ["Q4"] });

    const counts = wrapper.findAll(".filter-btn .cnt").map((node) => node.text());
    expect(counts).toEqual(["5", "3", "1"]); // 全部 5 / 未答 3 / 标记 1
    expect(wrapper.findAll(".qchip")).toHaveLength(5);

    await wrapper.find('[data-filter="unanswered"]').trigger("click");
    expect(wrapper.findAll(".qchip").map((node) => node.text())).toEqual(["3", "4", "5"]);

    await wrapper.find('[data-filter="marked"]').trigger("click");
    expect(wrapper.findAll(".qchip").map((node) => node.text())).toEqual(["4"]);
  });

  it("标记只加角点，不冒充已答", () => {
    const wrapper = mountSidebar(makeQuestions(3), { marked: ["Q2"] });
    const chips = wrapper.findAll(".qchip");
    expect(chips[1].classes()).toContain("is-marked");
    expect(chips[1].classes()).not.toContain("is-done");
  });

  it("超过 20 题切紧凑模式", () => {
    expect(mountSidebar(makeQuestions(20)).find(".card-scroll").classes()).not.toContain(
      "is-compact",
    );
    expect(mountSidebar(makeQuestions(21)).find(".card-scroll").classes()).toContain("is-compact");
  });

  it("题号始终是全卷序号，过滤后也不重排", async () => {
    const wrapper = mountSidebar(makeQuestions(5), { answered: ["Q1", "Q2", "Q3"] });
    await wrapper.find('[data-filter="unanswered"]').trigger("click");
    // 第 4、5 题必须还叫 4、5，否则交卷提示里的题号对不上
    expect(wrapper.findAll(".qchip").map((node) => node.text())).toEqual(["4", "5"]);
  });
});

// ==================== 判定详情 ====================

const SAMPLE_CASES = [
  {
    index: 0,
    status: "accepted",
    passed: true,
    time_ms: 3,
    memory_kb: 1024,
    is_sample: true,
    input: "Hello",
    expected: "olleH",
    actual: "olleH",
  },
  {
    index: 1,
    status: "wrong_answer",
    passed: false,
    time_ms: 2,
    memory_kb: 1050,
    is_sample: false,
    input: null,
    expected: null,
    actual: null,
  },
];

function submission(overrides = {}) {
  return {
    id: 1033,
    kind: "submit",
    language: "cpp",
    status: "wrong_answer",
    compile_message: "",
    created_at: new Date().toISOString(),
    score: 25,
    time_ms: 4,
    memory_kb: 1050,
    cases: SAMPLE_CASES,
    code: "int main(){}",
    ...overrides,
  };
}

describe("判定详情弹窗", () => {
  it("隐藏测试点只出状态，输入输出一个字都不渲染", () => {
    const wrapper = mount(SubmissionDetail, { props: { submission: submission() } });
    const cards = wrapper.findAll(".case-card");
    expect(cards).toHaveLength(2);
    expect(cards[1].classes()).toContain("is-hidden"); // 虚线框
    expect(cards[1].text()).toContain("WA");
    // 后端的 index 从 0 起，给人看的编号必须 +1，否则出现「样例 0」
    expect(cards[0].text()).toContain("样例 1");
    expect(cards[1].text()).toContain("隐藏点 2");
    // 隐藏点的三个字段恒为 null，任何渲染路径都不该把它们变成可见文本
    expect(wrapper.text()).not.toContain("Hello");
    expect(wrapper.text()).not.toContain("olleH");
  });

  it("六种判定各出对应缩写", () => {
    for (const [status, abbr] of [
      ["accepted", "AC"],
      ["wrong_answer", "WA"],
      ["time_limit", "TLE"],
      ["memory_limit", "MLE"],
      ["runtime_error", "RE"],
      ["compile_error", "CE"],
    ]) {
      const wrapper = mount(SubmissionDetail, { props: { submission: submission({ status }) } });
      expect(wrapper.get('[data-testid="verdict-abbr"]').text()).toBe(abbr);
    }
  });

  it("feedback_mode 裁掉 cases 时给出「暂不可见」而不是空表格", () => {
    const payload = submission();
    delete payload.cases;
    const wrapper = mount(SubmissionDetail, { props: { submission: payload } });
    expect(wrapper.find('[data-testid="cases-hidden"]').exists()).toBe(true);
    expect(wrapper.findAll(".case-card")).toHaveLength(0);
  });

  it("编译型题只出编译横幅，不渲染测试点", () => {
    const wrapper = mount(SubmissionDetail, {
      props: { submission: submission({ status: "accepted" }), compileOnly: true },
    });
    expect(wrapper.text()).toContain("编译通过");
    expect(wrapper.findAll(".case-card")).toHaveLength(0);
  });

  it("编译错误展示 compile_message", () => {
    const wrapper = mount(SubmissionDetail, {
      props: {
        submission: submission({ status: "compile_error", compile_message: "error: 'swp' 未声明" }),
      },
    });
    expect(wrapper.get(".compile-msg").text()).toContain("swp");
    expect(wrapper.findAll(".case-card")).toHaveLength(0);
  });

  it("成绩被裁掉时显示 —，不显示 0 分", () => {
    const payload = submission();
    delete payload.score;
    const wrapper = mount(SubmissionDetail, { props: { submission: payload } });
    expect(wrapper.text()).not.toContain("0 分");
  });
});

// ==================== 编程题工作区 ====================

function codingQuestion(overrides = {}) {
  return {
    problem_id_no: "P1",
    type: "programming",
    sub_type: "cpp",
    score: 50,
    stem: "反转字符串",
    programming: {
      title: "反转字符数组",
      input_format: "一个字符串",
      output_format: "反转后的结果",
      hints: "无",
      pass_condition: "全测试点通过",
      time_limit_ms: 1000,
      memory_limit_mb: 256,
      samples: [{ input: "Hello World", output: "dlroW olleH" }],
    },
    last_code: "int main(){}",
    ...overrides,
  };
}

function tabs(wrapper) {
  return wrapper.findAll(".ctab");
}

describe("编程题工作区", () => {
  it("两个控制台页签 + 一个运行按钮，操作条带提交记录计数", () => {
    const wrapper = mount(QuestionCoding, {
      props: { question: codingQuestion(), submissionCount: 3 },
    });
    // 样例试跑与自测已合并成「运行结果」，两个"跑"按钮也合成了一个
    expect(tabs(wrapper).map((node) => node.text())).toEqual(["运行结果", "判题结果"]);
    expect(wrapper.findAll(".prog-actions .btn").map((node) => node.text())).toEqual([
      "▶ 运行",
      "提交判题",
      "提交记录 (3)",
    ]);
  });

  it("输入源默认样例，此时运行不带 customInput", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    expect(wrapper.get('[data-source="sample"]').classes()).toContain("is-on");
    // 样例模式下没有 stdin 框，省出来的高度全给输出
    expect(wrapper.find("#custom-stdin").exists()).toBe(false);

    await wrapper.findAll(".prog-actions .btn")[0].trigger("click");
    const payload = wrapper.emitted("run").at(-1)[0];
    expect(payload.kind).toBe("trial");
    expect("customInput" in payload).toBe(false);
    payload.reject(new Error("stop"));
  });

  it("切到自定义输入源后，同一个运行按钮带上 customInput；空输入也放行", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.get('[data-source="custom"]').trigger("click");
    expect(wrapper.find("#custom-stdin").exists()).toBe(true);
    const run = () => wrapper.findAll(".prog-actions .btn")[0];

    await wrapper.get("#custom-stdin").setValue("");
    await run().trigger("click");
    let payload = wrapper.emitted("run").at(-1)[0];
    expect(payload.kind).toBe("trial");
    expect(payload.customInput).toBe(""); // 键存在且为空串 = 用空输入跑一次
    payload.reject(new Error("stop"));

    await wrapper.get("#custom-stdin").setValue("Hello World");
    await run().trigger("click");
    payload = wrapper.emitted("run").at(-1)[0];
    expect(payload.customInput).toBe("Hello World");
    payload.reject(new Error("stop"));
  });

  it("「填入样例 1」把样例输入灌进 stdin", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.get('[data-source="custom"]').trigger("click");
    await wrapper.get(".custom-run .copy-btn").trigger("click");
    expect(wrapper.get("#custom-stdin").element.value).toBe("Hello World");
  });

  it("提交判题永远不带 customInput，哪怕输入源停在自定义上", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.get('[data-source="custom"]').trigger("click");
    await wrapper.get("#custom-stdin").setValue("噪声");

    await wrapper.findAll(".prog-actions .btn")[1].trigger("click");
    const payload = wrapper.emitted("run").at(-1)[0];
    expect(payload.kind).toBe("submit");
    expect("customInput" in payload).toBe(false);
    payload.reject(new Error("stop"));
  });

  it("样例运行：没过的样例当场给期望/实际并高亮首处差异", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.findAll(".prog-actions .btn")[0].trigger("click");
    wrapper
      .emitted("run")
      .at(-1)[0]
      .resolve({
        id: 9,
        kind: "trial",
        status: "wrong_answer",
        compile_message: "",
        time_ms: 2,
        memory_kb: 1024,
        cases: [
          {
            index: 0,
            status: "accepted",
            passed: true,
            time_ms: 1,
            memory_kb: 1024,
            is_sample: true,
            input: "a",
            expected: "a",
            actual: "a",
          },
          {
            index: 1,
            status: "wrong_answer",
            passed: false,
            time_ms: 1,
            memory_kb: 1024,
            is_sample: true,
            input: "ab cd",
            expected: "dc ba",
            actual: "ab cd",
          },
        ],
      });
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();

    const table = wrapper.get('[data-testid="sample-run-table"]');
    expect(table.text()).toContain("✓ 通过");
    expect(table.text()).toContain("✗ WA");
    // 样例是公开的，没过就直接摆出对照，不必再点一次展开
    const diff = wrapper.get(".inline-diff");
    expect(diff.text()).toContain("dc ba");
    expect(wrapper.find('[data-testid="diff-mark"]').exists()).toBe(true);
    // 通过的那条不该也挂一份对照
    expect(wrapper.findAll(".inline-diff")).toHaveLength(1);
  });

  it("排队/判题中给进度，不把上一次的结果晾在那儿冒充本次", async () => {
    const wrapper = mount(QuestionCoding, {
      props: { question: codingQuestion({ last_submission: submission() }) },
    });
    await wrapper.findAll(".prog-actions .btn")[1].trigger("click"); // 提交判题
    const call = wrapper.emitted("run").at(-1)[0];

    // 后端异步：先回 queued，再变 judging，最后才是终态
    call.onProgress({ id: 9, status: "queued", queue_position: 3 });
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[data-testid="judge-pending"]').text()).toContain("前面还有 3 个");

    call.onProgress({ id: 9, status: "queued", queue_position: 0 });
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[data-testid="judge-pending"]').text()).toContain("排队中");

    call.onProgress({ id: 9, status: "judging" });
    await wrapper.vm.$nextTick();
    expect(wrapper.get('[data-testid="judge-pending"]').text()).toContain("判题中");

    call.resolve(submission({ status: "accepted" }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="judge-pending"]').exists()).toBe(false);
  });

  it("运行也带 signal 与 onProgress——切题时得能掐断轮询", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.findAll(".prog-actions .btn")[0].trigger("click");
    const call = wrapper.emitted("run").at(-1)[0];
    expect(typeof call.onProgress).toBe("function");
    expect(call.signal).toBeInstanceOf(AbortSignal);
    expect(call.signal.aborted).toBe(false);

    // 换一道题，上一次的轮询必须被取消
    await wrapper.setProps({ question: codingQuestion({ problem_id_no: "P2" }) });
    expect(call.signal.aborted).toBe(true);
    call.reject(new Error("已取消。"));
  });

  it("轮询到 judge_failed 是终态，不是异常——只 catch 不看终态会把故障演成判定", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.findAll(".prog-actions .btn")[1].trigger("click");
    // 判题服务挂了的时候，HTTP 是 200 queued，故障是轮询出来的终态
    wrapper
      .emitted("run")
      .at(-1)[0]
      .resolve(
        submission({ status: "judge_failed", compile_message: "判题服务暂时不可用，请稍后重试。" }),
      );
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();

    const banner = wrapper.get('[data-testid="judge-error"]');
    expect(banner.text()).toContain("判题服务暂时不可用");
    expect(banner.classes()).toContain("v-failed");
    expect(wrapper.text()).not.toContain("答案错误");
  });

  it("取消（切题/卸载）不该在界面上留错误", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.findAll(".prog-actions .btn")[1].trigger("click");
    wrapper.emitted("run").at(-1)[0].reject(new Error("已取消。"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="judge-error"]').exists()).toBe(false);
  });

  it("判题服务不可用：留下中性告警，绝不说成「答案错误」", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.findAll(".prog-actions .btn")[1].trigger("click"); // 提交判题
    wrapper.emitted("run").at(-1)[0].reject(new Error("判题服务暂时不可用，请稍后重试。"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();

    const banner = wrapper.get('[data-testid="judge-error"]');
    expect(banner.text()).toContain("判题服务暂时不可用");
    expect(banner.classes()).toContain("v-failed");
    expect(banner.classes()).not.toContain("v-wa");
    // 学员最怕的是"是不是已经按 0 分算了"——必须明说没记成绩
    expect(wrapper.text()).toContain("不是 0 分");
    expect(wrapper.text()).not.toContain("答案错误");
    // 控制台里不该同时还挂着「尚未提交判题，点击下方…」
    // （工具条上的"尚未提交判题"是另一回事，那句说的是历史上没有过成功提交，属实）
    expect(wrapper.get(".console-body").text()).not.toContain("点击下方");
  });

  it("判题失败但有旧结果时，写明底下那块是上一次的", async () => {
    // 这是最容易误读的一屏：「⚠ 判题未完成」和上一次的「✗ 答案错误 25 分」叠在一起，
    // 不加说明的话学员只会读到后面那条。
    const wrapper = mount(QuestionCoding, {
      props: { question: codingQuestion({ last_submission: submission() }) },
    });
    await wrapper.findAll(".prog-actions .btn")[1].trigger("click");
    wrapper.emitted("run").at(-1)[0].reject(new Error("判题服务暂时不可用，请稍后重试。"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();

    expect(wrapper.find('[data-testid="judge-error"]').exists()).toBe(true);
    const note = wrapper.get('[data-testid="stale-note"]');
    expect(note.text()).toContain("上一次成功判题");
    // 说明必须排在旧横幅之前，排后面就等于没说
    const body = wrapper.get(".console-body").html();
    expect(body.indexOf("stale-note")).toBeLessThan(body.indexOf("verdict-banner v-wa"));
  });

  it("判题成功后清掉上一次的失败告警", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.findAll(".prog-actions .btn")[1].trigger("click");
    wrapper.emitted("run").at(-1)[0].reject(new Error("判题服务暂时不可用，请稍后重试。"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="judge-error"]').exists()).toBe(true);

    await wrapper.findAll(".prog-actions .btn")[1].trigger("click");
    wrapper
      .emitted("run")
      .at(-1)[0]
      .resolve(submission({ status: "accepted" }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="judge-error"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="stale-note"]').exists()).toBe(false);
  });

  it("提交记录按钮把事件抛给上层", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    await wrapper.findAll(".prog-actions .btn")[2].trigger("click");
    expect(wrapper.emitted("history")).toHaveLength(1);
  });

  it("判题结果页签：六种判定各出对应横幅类", async () => {
    for (const [status, banner] of [
      ["accepted", "v-ac"],
      ["wrong_answer", "v-wa"],
      ["time_limit", "v-tle"],
      ["memory_limit", "v-mle"],
      ["runtime_error", "v-re"],
      ["compile_error", "v-ce"],
    ]) {
      const wrapper = mount(QuestionCoding, {
        props: { question: codingQuestion({ last_submission: submission({ status }) }) },
      });
      await tabs(wrapper)[1].trigger("click");
      expect(wrapper.get('[data-testid="verdict-banner"]').classes()).toContain(banner);
    }
  });

  it("隐藏测试点行只有状态，展开箭头都不给", async () => {
    const wrapper = mount(QuestionCoding, {
      props: { question: codingQuestion({ last_submission: submission() }) },
    });
    await tabs(wrapper)[1].trigger("click");
    const rows = wrapper.findAll('[data-testid="case-table"] tbody tr');
    expect(rows).toHaveLength(2);
    expect(rows[1].classes()).not.toContain("sample-row");
    expect(rows[1].text()).toContain("隐藏");
    // 点它也展不开，因为隐藏点根本没有内容
    await rows[1].trigger("click");
    expect(wrapper.findAll(".case-expand")).toHaveLength(0);
  });

  it("样例行展开后出现三栏对比，输出不一致时高亮首处差异", async () => {
    const mismatched = submission({
      cases: [
        {
          index: 0,
          status: "wrong_answer",
          passed: false,
          time_ms: 1,
          memory_kb: 100,
          is_sample: true,
          input: "ab cd",
          expected: "dc ba",
          actual: "ab cd",
        },
      ],
    });
    const wrapper = mount(QuestionCoding, {
      props: { question: codingQuestion({ last_submission: mismatched }) },
    });
    await tabs(wrapper)[1].trigger("click");
    await wrapper.get(".sample-row").trigger("click");

    const expand = wrapper.get(".case-expand");
    expect(expand.text()).toContain("期望输出");
    expect(expand.text()).toContain("实际输出");
    expect(wrapper.find('[data-testid="diff-mark"]').exists()).toBe(true);
  });

  it("样例通过时不高亮差异", async () => {
    const wrapper = mount(QuestionCoding, {
      props: { question: codingQuestion({ last_submission: submission() }) },
    });
    await tabs(wrapper)[1].trigger("click");
    await wrapper.get(".sample-row").trigger("click");
    expect(wrapper.find('[data-testid="diff-mark"]').exists()).toBe(false);
  });

  it("feedback_mode 裁掉 cases 时不渲染测试点表格", async () => {
    const payload = submission();
    delete payload.cases;
    const wrapper = mount(QuestionCoding, {
      props: { question: codingQuestion({ last_submission: payload }) },
    });
    await tabs(wrapper)[1].trigger("click");
    expect(wrapper.find('[data-testid="case-table"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="cases-hidden"]').exists()).toBe(true);
  });

  it("编译型题：挂满分条件徽章、不渲染测试点表格", async () => {
    const question = codingQuestion({
      programming: { ...codingQuestion().programming, pass_condition: "编译通过" },
      last_submission: submission({ status: "accepted" }),
    });
    const wrapper = mount(QuestionCoding, { props: { question } });
    expect(wrapper.get(".pass-cond").text()).toBe("满分条件：编译通过");
    expect(wrapper.text()).toContain("本题以编译通过为满分条件");

    await tabs(wrapper)[1].trigger("click");
    expect(wrapper.find('[data-testid="case-table"]').exists()).toBe(false);
  });

  it("编译型题横幅只说编译过没过，不照抄判题器的 wrong_answer", async () => {
    const compileOnly = { ...codingQuestion().programming, pass_condition: "编译通过" };
    // 编译通过但测试点没过：后端存的 status 就是 wrong_answer，而这题该判满分
    const passed = mount(QuestionCoding, {
      props: {
        question: codingQuestion({
          programming: compileOnly,
          last_submission: submission({ status: "wrong_answer" }),
        }),
      },
    });
    await tabs(passed)[1].trigger("click");
    const banner = passed.get('[data-testid="verdict-banner"]');
    expect(banner.text()).toContain("编译通过");
    expect(banner.text()).not.toContain("答案错误");
    expect(banner.classes()).toContain("v-ac");

    const failed = mount(QuestionCoding, {
      props: {
        question: codingQuestion({
          programming: compileOnly,
          last_submission: submission({ status: "compile_error" }),
        }),
      },
    });
    await tabs(failed)[1].trigger("click");
    expect(failed.get('[data-testid="verdict-banner"]').text()).toContain("编译失败");
    expect(failed.get('[data-testid="verdict-banner"]').classes()).toContain("v-ce");
  });

  it("专注模式只留编辑器：题面与控制台都收起，退出口和操作条还在", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const focus = () => wrapper.findAll(".tool-btn").find((node) => node.text().includes("专注"));
    expect(wrapper.get(".prog-wrap").classes()).not.toContain("is-focus");

    await focus().trigger("click");
    expect(wrapper.get(".prog-wrap").classes()).toContain("is-focus");
    expect(focus().attributes("aria-pressed")).toBe("true");
    // 编辑器、工具条（唯一退出口）、操作条（不留就没法提交）必须还在
    expect(wrapper.find(".editor-host").exists()).toBe(true);
    expect(wrapper.find(".prog-actions").exists()).toBe(true);

    await focus().trigger("click");
    expect(wrapper.get(".prog-wrap").classes()).not.toContain("is-focus");
  });

  it("专注模式下开跑会自动退出，否则输出写进看不见的控制台", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const focus = () => wrapper.findAll(".tool-btn").find((node) => node.text().includes("专注"));
    await focus().trigger("click");
    expect(wrapper.get(".prog-wrap").classes()).toContain("is-focus");

    await wrapper.findAll(".prog-actions .btn")[0].trigger("click"); // ▶ 运行
    expect(wrapper.get(".prog-wrap").classes()).not.toContain("is-focus");
    wrapper.emitted("run").at(-1)[0].reject(new Error("stop"));
  });

  it("字号三档到头就禁用，并记进 localStorage", async () => {
    localStorage.clear();
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const [minus, plus] = wrapper.findAll(".tool-btn");
    expect(minus.attributes("disabled")).toBeUndefined(); // 默认在中档

    await minus.trigger("click");
    expect(localStorage.getItem("exam.editor.fontIndex")).toBe("0");
    expect(minus.attributes("disabled")).toBeDefined(); // 到底了

    await plus.trigger("click");
    await plus.trigger("click");
    expect(localStorage.getItem("exam.editor.fontIndex")).toBe("2");
    expect(plus.attributes("disabled")).toBeDefined(); // 到顶了
  });

  // 拖拽走的是 Pointer Events 而不是 mouse*（2026-08-12）：后者在触屏上完全不触发，
  // 平板与二合一设备上这两条分隔条等于不存在。
  //
  // jsdom 没有 PointerEvent 构造器，VTU 的 trigger("pointerdown") 会当场报错；
  // 直接用 MouseEvent 派发 pointer* 即可——监听器只认事件类型和 clientX/Y。
  const pointerDown = (handle, init) =>
    handle.element.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, ...init }));

  it("题面↔编辑器有可拖分隔条：拖动改列宽、夹在上下限内、双击复位", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const handle = wrapper.get('[data-testid="divider-col"]');
    const cols = () => wrapper.get(".prog-wrap").attributes("style") || "";
    // jsdom 不做布局；给工作区一个接近桌面端的真实宽度，避免把“未布局的 0px”
    // 误当成可用宽度并让最大值退化到 220px。
    vi.spyOn(wrapper.get(".prog-wrap").element, "getBoundingClientRect").mockReturnValue({
      width: 887,
      height: 600,
      top: 0,
      right: 887,
      bottom: 600,
      left: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    // 没拖过时不挂内联列宽，走 CSS 的 fr 比例，窄屏才好自适应
    expect(cols()).not.toContain("grid-template-columns");

    // 题面本身在 jsdom 中仍量不出宽度，拖动基准会落在 220px 下限上。
    pointerDown(handle, { clientX: 0 });
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 60 }));
    await wrapper.vm.$nextTick();
    expect(cols()).toContain("280px"); // 220 下限 + 60
    window.dispatchEvent(new MouseEvent("pointerup"));

    // 往右拖过头要被夹在上限
    pointerDown(handle, { clientX: 0 });
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 5000 }));
    await wrapper.vm.$nextTick();
    expect(cols()).toContain("560px");
    window.dispatchEvent(new MouseEvent("pointerup"));

    // 往左拖过头夹在下限
    pointerDown(handle, { clientX: 0 });
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: -5000 }));
    await wrapper.vm.$nextTick();
    expect(cols()).toContain("220px");
    window.dispatchEvent(new MouseEvent("pointerup"));

    await handle.trigger("dblclick");
    expect(cols()).not.toContain("grid-template-columns");
  });

  it("松开鼠标后不再跟着动——监听必须拆干净", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const handle = wrapper.get('[data-testid="divider-col"]');
    pointerDown(handle, { clientX: 0 });
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 60 }));
    window.dispatchEvent(new MouseEvent("pointerup"));
    await wrapper.vm.$nextTick();
    const frozen = wrapper.get(".prog-wrap").attributes("style");

    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 400 }));
    await wrapper.vm.$nextTick();
    expect(wrapper.get(".prog-wrap").attributes("style")).toBe(frozen);
  });

  it("专注模式下不挂固定列宽，否则内联样式会盖掉单列布局", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const handle = wrapper.get('[data-testid="divider-col"]');
    pointerDown(handle, { clientX: 0 });
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 100 }));
    window.dispatchEvent(new MouseEvent("pointerup"));
    await wrapper.vm.$nextTick();
    expect(wrapper.get(".prog-wrap").attributes("style")).toContain("grid-template-columns");

    const focus = wrapper.findAll(".tool-btn").find((node) => node.text().includes("专注"));
    await focus.trigger("click");
    // 内联样式优先级高于 .is-focus 那条类规则，专注时必须整个摘掉
    expect(wrapper.get(".prog-wrap").attributes("style") || "").not.toContain(
      "grid-template-columns",
    );
  });

  it("控制台分隔条仍然独立可拖", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const handle = wrapper.get('[data-testid="divider-row"]');
    pointerDown(handle, { clientY: 300 });
    window.dispatchEvent(new MouseEvent("pointermove", { clientY: 240 })); // 往上拖 60
    await wrapper.vm.$nextTick();
    expect(wrapper.get(".console").attributes("style")).toContain("250px"); // 190 + 60
    window.dispatchEvent(new MouseEvent("pointerup"));
  });

  it("控制台可折叠成一条", async () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    expect(wrapper.get(".console").classes()).not.toContain("is-collapsed");
    await wrapper.get(".console-fold").trigger("click");
    expect(wrapper.get(".console").classes()).toContain("is-collapsed");
    // 切页签会顺手展开——收起状态下点页签什么都不显示，那是个死角
    await tabs(wrapper)[1].trigger("click");
    expect(wrapper.get(".console").classes()).not.toContain("is-collapsed");
  });

  it("限制条：无逐点范围时显示题目级单值", () => {
    const wrapper = mount(QuestionCoding, { props: { question: codingQuestion() } });
    const chips = wrapper.get(".limit-chips").text();
    expect(chips).toContain("限时 1000 ms");
    expect(chips).toContain("内存 256 MB");
  });

  it("限制条：max ≠ min 时渲染成范围，相等时仍是单值", () => {
    const ranged = codingQuestion({
      programming: {
        title: "反转字符串数组",
        input_format: "",
        output_format: "",
        hints: "无",
        pass_condition: "全测试点通过",
        time_limit_ms: 1000,
        memory_limit_mb: 256,
        time_limit_range: [1000, 3000],
        memory_limit_range: [64, 256],
        samples: [],
      },
    });
    const wrapper = mount(QuestionCoding, { props: { question: ranged } });
    const chips = wrapper.get(".limit-chips").text();
    expect(chips).toContain("限时 1000–3000 ms");
    expect(chips).toContain("内存 64–256 MB");

    const equal = codingQuestion({
      programming: {
        title: "反转字符串数组",
        input_format: "",
        output_format: "",
        hints: "无",
        pass_condition: "全测试点通过",
        time_limit_ms: 1000,
        memory_limit_mb: 256,
        time_limit_range: [1000, 1000],
        memory_limit_range: [256, 256],
        samples: [],
      },
    });
    const equalWrapper = mount(QuestionCoding, { props: { question: equal } });
    const equalChips = equalWrapper.get(".limit-chips").text();
    expect(equalChips).toContain("限时 1000 ms");
    expect(equalChips).toContain("内存 256 MB");
  });
});
