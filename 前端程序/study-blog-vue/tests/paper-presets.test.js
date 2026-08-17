// @vitest-environment jsdom
// paper-presets.js 护栏：评审硬性约束——
//   1) 只放纯数据表，五种预设的填充走同一条代码路径，禁止 if (ruleset === ...) 分支；
//   2) 数据与《3、后台试卷-组卷模块》3.1 预设表一致。
// 加新赛制 = 加一行数据；若有人把分支逻辑写进填充函数，这里的用例会报警。
//
// v2 两层模型：一个预设同时填两层——paper 层是判分口径（所有场次必须一致），
// link 层是考试安排（每个场次可不同）。属性串层是本文件重点防的退化路径。
import { describe, expect, it } from "vitest";
import { PAPER_PRESETS, applyPreset, findPreset } from "../public/admin/paper-presets.js";

// 与《3、后台试卷-组卷模块》3.1 +《4、后台考试链接-管理模块》5.4 的表格逐格对齐。改这里之前先改文档。
const DOC_TABLE = {
  练习卷: { ruleset: "IOI", paper: { score_mode: "testcase" },
    link: { attempt_limit: 0, shuffle_questions: false, duration_minutes: null, show_analysis: "after_submit", feedback_mode: "realtime",
      entry_open_minutes: 0, remind_minutes: "", notice_ack_required: false } },
  测试卷: { ruleset: "IOI", paper: { score_mode: "testcase" },
    link: { attempt_limit: 1, shuffle_questions: true, duration_minutes: 60, show_analysis: "after_submit", feedback_mode: "realtime",
      entry_open_minutes: 10, remind_minutes: "10,5", notice_ack_required: false } },
  模拟卷: { ruleset: "IOI", paper: { score_mode: "testcase" },
    link: { attempt_limit: 1, shuffle_questions: true, duration_minutes: 210, show_analysis: "after_close", feedback_mode: "compile_only",
      entry_open_minutes: 15, remind_minutes: "30,10,5", notice_ack_required: true } },
  竞赛卷: { ruleset: "ACM", paper: { score_mode: "all_or_nothing" },
    link: { attempt_limit: 1, shuffle_questions: false, duration_minutes: 300, show_analysis: "after_close", feedback_mode: "compile_only",
      entry_open_minutes: 20, remind_minutes: "60,30,10,5", notice_ack_required: true } },
  作业卷: { ruleset: "IOI", paper: { score_mode: "testcase" },
    link: { attempt_limit: 0, shuffle_questions: false, duration_minutes: null, show_analysis: "after_submit", feedback_mode: "realtime",
      entry_open_minutes: 0, remind_minutes: "", notice_ack_required: false } },
};

describe("paper-presets.js 预设数据表", () => {
  it("恰有五种预设，与文档 3.1 一一对应", () => {
    expect(PAPER_PRESETS.map((p) => [p.paper_type, p.ruleset])).toEqual(
      Object.entries(DOC_TABLE).map(([type, row]) => [type, row.ruleset]),
    );
  });

  it("每行预设的两层填充值与文档 3.1 表格一致", () => {
    for (const preset of PAPER_PRESETS) {
      const expected = DOC_TABLE[preset.paper_type];
      expect(preset.paper, preset.paper_type).toEqual(expected.paper);
      expect(preset.link, preset.paper_type).toEqual(expected.link);
    }
  });

  it("属性归属不串层：时间/次数/呈现只能在 link，判分口径只能在 paper", () => {
    const LINK_ONLY = ["attempt_limit", "duration_minutes", "shuffle_questions", "show_analysis", "feedback_mode"];
    for (const preset of PAPER_PRESETS) {
      for (const key of LINK_ONLY) {
        expect(preset.paper, `${preset.paper_type} 的 paper 层不该有 ${key}`).not.toHaveProperty(key);
      }
      // 判分口径必须对所有场次一致，因此只能在卷层。
      expect(preset.link, preset.paper_type).not.toHaveProperty("score_mode");
    }
  });

  it("预设只含展示用字段，不含内容语义字段（题目/分值/及格分）", () => {
    for (const preset of PAPER_PRESETS) {
      expect(Object.keys(preset).sort()).toEqual(["link", "paper", "paper_type", "ruleset"]);
      const merged = { ...preset.paper, ...preset.link };
      for (const key of ["pass_score", "questions", "title", "total_score"]) {
        expect(merged, preset.paper_type).not.toHaveProperty(key);
      }
    }
  });

  it("考前提醒三键齐全且 notice 不进预设（须知因卷而异，模板文字只会被整段重写）", () => {
    for (const preset of PAPER_PRESETS) {
      expect(preset.link, preset.paper_type).toHaveProperty("entry_open_minutes");
      expect(preset.link, preset.paper_type).toHaveProperty("remind_minutes");
      expect(preset.link, preset.paper_type).toHaveProperty("notice_ack_required");
      expect(preset.link, preset.paper_type).not.toHaveProperty("notice");
    }
  });
});

describe("applyPreset 统一填充路径", () => {
  it("五种预设走同一条路径：查表 → 展开两层 + 记录来源", () => {
    for (const preset of PAPER_PRESETS) {
      const paperState = {};
      const linkState = {};
      const hit = applyPreset(paperState, linkState, preset.paper_type);
      expect(hit).toBe(preset);
      expect(paperState).toEqual({ ...preset.paper, paper_type: preset.paper_type, ruleset: preset.ruleset });
      expect(linkState).toEqual(preset.link);
    }
  });

  it("linkState 可省略：只建卷、暂不配场次时不该报错", () => {
    const paperState = {};
    expect(() => applyPreset(paperState, null, "模拟卷")).not.toThrow();
    expect(paperState.ruleset).toBe("IOI");
    expect(paperState.score_mode).toBe("testcase");
  });

  it("未知类型返回 null 且不改动任何状态", () => {
    const paperState = { paper_type: "练习卷" };
    const linkState = { attempt_limit: 7 };
    expect(applyPreset(paperState, linkState, "不存在的卷")).toBeNull();
    expect(paperState).toEqual({ paper_type: "练习卷" });
    expect(linkState).toEqual({ attempt_limit: 7 });
    expect(findPreset("不存在的卷")).toBeNull();
  });

  it("填充不污染预设表（表单拿到的是展开值，不是表内引用）", () => {
    const before = JSON.stringify(PAPER_PRESETS);
    const paperState = {};
    const linkState = {};
    applyPreset(paperState, linkState, "竞赛卷");
    paperState.score_mode = "被改坏了";
    linkState.attempt_limit = 999;
    expect(JSON.stringify(PAPER_PRESETS)).toBe(before);
    expect(findPreset("竞赛卷").paper.score_mode).toBe("all_or_nothing");
    expect(findPreset("竞赛卷").link.attempt_limit).toBe(1);
  });
});
