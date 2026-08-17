// 试卷预设：纯数据表 + 统一填充函数。
//
// 本文件的硬约束（评审给定，改动前必读）：
// - 只放数据表，禁止出现 if (ruleset === ...) / if (paper_type === ...) 之类的分支逻辑；
// - paper_type / ruleset 只记录「从哪个预设填的」，不参与任何判分或校验逻辑——
//   后端同样不读它们（见后端 admin_papers.py 文件头注释）；
// - applyPreset() 对全部预设走同一条代码路径：查表 → 展开 values。将来加新赛制
//   只加一行数据，不动任何代码。
//
// v2 两层模型：一个预设同时填两层——
//   paper 层：判分口径（score_mode），跟着试卷走，所有场次一致；
//   link  层：考试安排（时长/次数/呈现），跟着链接走，每个场次可不同。
// 数据与《3、后台试卷-组卷模块》3.1 的预设表一一对应。

export const PAPER_PRESETS = [
  {
    paper_type: "练习卷",
    ruleset: "IOI",
    paper: { score_mode: "testcase" },
    link: {
      attempt_limit: 0, // 0 = 不限
      shuffle_questions: false,
      duration_minutes: null, // null = 不限时
      show_analysis: "after_submit",
      feedback_mode: "realtime",
      // 考前提醒（《4、后台考试链接-管理模块》5.4）：练习以随时刷为主，不设候考与提醒。
      entry_open_minutes: 0,
      remind_minutes: "",
      notice_ack_required: false,
    },
  },
  {
    paper_type: "测试卷",
    ruleset: "IOI",
    paper: { score_mode: "testcase" },
    link: {
      attempt_limit: 1,
      shuffle_questions: true,
      duration_minutes: 60,
      show_analysis: "after_submit",
      feedback_mode: "realtime",
      entry_open_minutes: 10,
      remind_minutes: "10,5",
      notice_ack_required: false,
    },
  },
  {
    paper_type: "模拟卷",
    ruleset: "IOI",
    paper: { score_mode: "testcase" },
    link: {
      attempt_limit: 1,
      shuffle_questions: true,
      duration_minutes: 210,
      show_analysis: "after_close",
      feedback_mode: "compile_only",
      entry_open_minutes: 15,
      remind_minutes: "30,10,5",
      notice_ack_required: true,
    },
  },
  {
    paper_type: "竞赛卷",
    ruleset: "ACM",
    paper: { score_mode: "all_or_nothing" },
    link: {
      attempt_limit: 1,
      shuffle_questions: false,
      duration_minutes: 300,
      show_analysis: "after_close",
      feedback_mode: "compile_only",
      entry_open_minutes: 20,
      remind_minutes: "60,30,10,5",
      notice_ack_required: true,
    },
  },
  {
    paper_type: "作业卷",
    ruleset: "IOI",
    paper: { score_mode: "testcase" },
    link: {
      attempt_limit: 0,
      shuffle_questions: false,
      duration_minutes: null,
      show_analysis: "after_submit",
      feedback_mode: "realtime",
      entry_open_minutes: 0,
      remind_minutes: "",
      notice_ack_required: false,
    },
  },
];

export function findPreset(paperType) {
  return PAPER_PRESETS.find((preset) => preset.paper_type === paperType) || null;
}

/**
 * 统一填充入口：把预设展开成具体开关值。
 * 对五种预设走同一条路径——差异全部在数据表里，这里没有也不允许有按预设分支的代码。
 * 填充后管理员可逐项调整；ruleset 仅记录来源。
 *
 * @param paperState 试卷层表单状态（必填）
 * @param linkState  链接层表单状态（可选：只建卷、暂不配场次时传 null）
 * @returns 命中的预设（用于界面提示「已按『X』填充」），未命中返回 null。
 */
export function applyPreset(paperState, linkState, paperType) {
  const preset = findPreset(paperType);
  if (!preset) return null;
  Object.assign(paperState, preset.paper);
  paperState.paper_type = preset.paper_type;
  paperState.ruleset = preset.ruleset;
  if (linkState) Object.assign(linkState, preset.link);
  return preset;
}
