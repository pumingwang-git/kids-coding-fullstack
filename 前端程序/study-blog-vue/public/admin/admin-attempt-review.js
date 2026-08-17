import { adminRequest } from "./admin-api.js";
import { closeMask, escapeHtml, openMask } from "./admin-ui.js";
import { renderMarkdown } from "./admin-markdown.js";

const TYPE_LABEL = { choice: "单选题", multi_choice: "多选题", judge: "判断题", fill: "填空题", programming: "编程题" };
const JUDGE_LABEL = {
  accepted: "通过", wrong_answer: "答案错误", compile_error: "编译错误",
  runtime_error: "运行错误", time_limit: "超出时间限制",
  memory_limit: "超出内存限制", judge_failed: "判题异常",
  queued: "等待判题", running: "判题中",
};

function scoreTagOf(question) {
  if (question.judge_status === "failed") return '<span class="tag danger">判题异常 · 不计分</span>';
  if (question.score === null || question.score === undefined) return '<span class="tag gray">未判分</span>';
  return `<span class="tag">${question.score} / ${question.full_score} 分</span>`;
}

function answerTextOf(question) {
  const answer = question.answer || {};
  if (question.type === "multi_choice") return (answer.picked || []).join("、") || "（未作答）";
  if (question.type === "fill") {
    return Object.entries(answer.blanks || {}).map(([key, value]) => `${key}：${value || "（空）"}`).join("；") || "（未作答）";
  }
  return answer.picked || "（未作答）";
}

function programmingCasesOf(submission) {
  const cases = Array.isArray(submission.detail) ? submission.detail : [];
  if (!cases.length) return "";
  return `<div class="review-cases"><strong>测试点结果</strong><div class="table-wrap"><table class="review-case-table"><thead><tr><th>测试点</th><th>结果</th><th>耗时</th><th>内存</th></tr></thead><tbody>${cases.map((item) => `<tr><td>#${item.index ?? "—"}${item.is_sample ? " · 样例" : ""}</td><td>${escapeHtml(JUDGE_LABEL[item.status] || item.status || "—")}</td><td>${item.time_ms == null ? "—" : `${item.time_ms} ms`}</td><td>${item.memory_kb == null ? "—" : `${item.memory_kb} KB`}</td></tr>`).join("")}</tbody></table></div></div>`;
}

function questionBodyOf(question) {
  if (question.missing) return '<dl class="q-compare"><dt>状态</dt><dd>题目已被删除，本题记 0 分。</dd></dl>';
  if (question.type === "programming") {
    const submissions = question.submissions || [];
    const last = submissions.at(-1);
    if (!last) return '<dl class="q-compare"><dt>提交</dt><dd>没有计分提交。</dd></dl>';
    return `<dl class="q-compare"><dt>提交次数</dt><dd>${submissions.length} 次（成绩以最后一次为准）</dd><dt>判题结果</dt><dd>${escapeHtml(JUDGE_LABEL[last.status] || last.status || "—")}${last.score != null ? ` · ${last.score} 分` : ""}</dd>${last.language ? `<dt>语言</dt><dd>${escapeHtml(last.language)}</dd>` : ""}${last.compile_message ? `<dt>编译信息</dt><dd class="wrap-anywhere">${escapeHtml(last.compile_message)}</dd>` : ""}</dl><pre class="code"><code>${escapeHtml(last.code || "")}</code></pre>${programmingCasesOf(last)}`;
  }
  if (question.type === "fill") {
    const blanks = (question.blanks || []).map((blank) => `${blank.blank_key}：${blank.answers.join(" / ")}`).join("；");
    return `<dl class="q-compare"><dt>学员答案</dt><dd>${escapeHtml(answerTextOf(question))}</dd><dt>参考答案</dt><dd>${escapeHtml(blanks || "—")}</dd></dl>`;
  }
  const options = (question.options || []).map((option, index) => {
    const picked = question.type === "multi_choice"
      ? (question.answer?.picked || []).includes(option.option_label)
      : question.answer?.picked === option.option_label;
    const classes = [option.is_correct ? "is-key" : "", picked ? "is-picked" : ""].filter(Boolean).join(" ");
    return `<li class="${classes}"><span class="opt-mark">${option.is_correct ? "正确" : ""}</span><span class="opt-label">${escapeHtml(option.option_label)}.</span><span class="opt-body"><span class="md-slot" data-md-slot="option:${index}"></span></span>${picked ? '<span class="opt-picked">学员选择</span>' : ""}</li>`;
  }).join("");
  return `<ul class="opts">${options}</ul><dl class="q-compare"><dt>学员答案</dt><dd>${escapeHtml(answerTextOf(question))}</dd></dl>`;
}

async function renderQuestionMarkdown(node, question) {
  const slots = { stem: question.stem || "" };
  (question.options || []).forEach((option, index) => { slots[`option:${index}`] = option.content || ""; });
  for (const slot of node.querySelectorAll(".md-slot")) {
    const key = slot.dataset.mdSlot;
    if (key in slots) await renderMarkdown(slot, slots[key]);
  }
  for (const blank of question.blanks || []) {
    for (const mark of node.querySelectorAll(".blank-mark")) {
      if (mark.dataset.key === String(blank.blank_key)) {
        mark.textContent = (blank.answers || [])[0] || "";
        mark.classList.add("filled");
      }
    }
  }
}

export function createAttemptReview({ mask, title, body, closeButton }) {
  let releaseFocus = null;
  let returnFocus = null;
  let requestSequence = 0;

  function close() {
    requestSequence += 1;
    closeMask(mask, releaseFocus);
    releaseFocus = null;
    returnFocus?.focus?.();
    returnFocus = null;
  }

  closeButton.addEventListener("click", close);
  mask.addEventListener("click", (event) => { if (event.target === mask) close(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !mask.hidden) close();
  });

  async function open(attemptId, trigger = document.activeElement) {
    const sequence = ++requestSequence;
    returnFocus = trigger;
    title.textContent = "正在加载答卷…";
    body.innerHTML = '<div class="review-loading" role="status">正在读取逐题作答与判题结果…</div>';
    releaseFocus = openMask(mask, { focusSelector: "[data-attempt-review-close]" });
    try {
      const payload = await adminRequest(`/attempts/${attemptId}/review`);
      if (sequence !== requestSequence) return;
      const attempt = payload.attempt;
      title.textContent = `${payload.user.username} · 第 ${attempt.attempt_no} 次 · 总分 ${attempt.total_score ?? "—"} / ${payload.full_score}`;
      body.innerHTML = payload.questions.length ? payload.questions.map((question) => `<article class="answer-item"><div class="q-head"><b>第 ${question.sort_order} 题</b><span class="tag">${question.missing ? "题目已删除" : (TYPE_LABEL[question.type] || escapeHtml(question.type || "未知题型"))}</span>${scoreTagOf(question)}</div><div class="q-stem"><span class="md-slot" data-md-slot="stem"></span></div>${questionBodyOf(question)}</article>`).join("") : '<div class="review-empty">这份答卷没有可回看的题目。</div>';
      body.scrollTop = 0;
      const cards = [...body.querySelectorAll(".answer-item")];
      await Promise.all(payload.questions.map((question, index) => cards[index] ? renderQuestionMarkdown(cards[index], question) : null));
    } catch (error) {
      if (sequence !== requestSequence) return;
      close();
      throw error;
    }
  }

  return { open, close };
}
