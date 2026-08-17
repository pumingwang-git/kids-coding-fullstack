// 判题结果的呈现规则。抽出来是因为这几条最容易在改 UI 时被顺手改坏，
// 而它们各自都有明确的对错：
//   - 六种判定的缩写与配色必须与 app/judge/base.py 的常量一一对应；
//   - 隐藏测试点的 input/expected/actual 恒为 null，任何渲染路径都不许把它当空串处理；
//   - feedback_mode 裁掉 cases 时，「暂不可见」和「没有测试点」是两回事。
// 纯函数、不依赖 Vue，直接单测。

/** 判题终态 → { 缩写, 测试点徽章类, 横幅类, 中文 }。键与后端常量对齐。 */
export const VERDICT = {
  accepted: { abbr: "AC", badge: "cb-ac", banner: "v-ac", text: "全部通过" },
  wrong_answer: { abbr: "WA", badge: "cb-wa", banner: "v-wa", text: "答案错误" },
  time_limit: { abbr: "TLE", badge: "cb-tle", banner: "v-tle", text: "超出时间限制" },
  memory_limit: { abbr: "MLE", badge: "cb-mle", banner: "v-mle", text: "超出内存限制" },
  runtime_error: { abbr: "RE", badge: "cb-re", banner: "v-re", text: "运行错误" },
  compile_error: { abbr: "CE", badge: "cb-hidden", banner: "v-ce", text: "编译错误" },
  // 判题服务故障。文案绝不能说「答案错误」——那是把系统问题赖给学员（验收手册四级）。
  judge_failed: { abbr: "--", badge: "cb-hidden", banner: "v-failed", text: "判题异常" },
  failed: { abbr: "--", badge: "cb-hidden", banner: "v-failed", text: "判题异常" },
};

const UNKNOWN = { abbr: "?", badge: "cb-hidden", banner: "v-failed", text: "未知状态" };

export function verdictOf(status) {
  return VERDICT[status] || { ...UNKNOWN, text: status || UNKNOWN.text };
}

/** 判题终态。非终态（queued / judging）意味着还得继续轮询，与后端的同名集合对齐。 */
export const TERMINAL_STATUSES = new Set([
  "accepted",
  "wrong_answer",
  "time_limit",
  "memory_limit",
  "runtime_error",
  "compile_error",
  "judge_failed",
  "failed",
]);

export function isPending(submission) {
  return !!submission && !TERMINAL_STATUSES.has(submission.status);
}

/**
 * 逐测试点结果能不能看。
 *
 * 后端在 feedback_mode 为 compile_only / after_close(未到点) 时**整个不下发 cases 键**，
 * 而不是给空数组——「暂不可见」与「这题没有测试点」必须能分开，否则学员会以为判题坏了。
 */
export function casesVisible(submission) {
  return Array.isArray(submission?.cases);
}

/** 满分条件是「编译通过」的题：不跑测试点，只出编译横幅。 */
export function isCompileOnly(question) {
  return question?.programming?.pass_condition === "编译通过";
}

/**
 * 实际输出与期望输出的首处差异位置。
 * 返回 -1 表示两者一致（不该高亮）。expected 为 null（隐藏点）时同样返回 -1。
 */
export function firstDiffIndex(expected, actual) {
  if (expected == null || actual == null) return -1;
  if (expected === actual) return -1;
  let index = 0;
  while (index < actual.length && index < expected.length && actual[index] === expected[index])
    index += 1;
  return index;
}

/**
 * 把实际输出切成 [相同前缀, 首处差异片段, 剩余] 三段，供模板高亮中间那段。
 * 差异片段固定取 8 个字符；实际输出比期望短时（首处差异落在末尾）用 ␣ 占位，
 * 否则「少输出了一个换行」这种情况会高亮出一个看不见的空片段。
 */
export function splitDiff(expected, actual, span = 8) {
  const at = firstDiffIndex(expected, actual);
  if (at < 0) return { head: actual ?? "", mark: "", tail: "", matched: true };
  const text = actual ?? "";
  return {
    head: text.slice(0, at),
    mark: text.slice(at, at + span) || "␣",
    tail: text.slice(at + span),
    matched: false,
  };
}

/** 提交记录里的一行摘要：null 的时间/内存要显示成 --，不能显示 0。 */
export function metricText(value, unit) {
  return value == null ? "--" : `${value}${unit}`;
}
