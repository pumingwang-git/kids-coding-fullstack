// 成绩统计：「组卷 → 发链接 → 看结果」动线的最后一步。
// 三个只读接口（admin_results.py）：
//   GET /api/admin/exam-results             总览（带 source 扩展位：课包作业/练一练落地后并入）
//   GET /api/admin/links/{id}/results       单场明细 + 分布
//   GET /api/admin/attempts/{id}/review     单份答卷逐题回看
// 口径说明：
// - 没有"应到/未交"——链接无名单，系统只知道谁来考过；明细按作答记录列。
// - judge_failed 的题 score 为 null、不计入总分，界面上是"判题异常"，不是 0 分。
import { initLayout } from "./admin-layout.js";
import { adminRequest } from "./admin-api.js";
import { escapeHtml, fmtTime, toast } from "./admin-ui.js";
import { createAttemptReview } from "./admin-attempt-review.js";
import * as charts from "./admin-charts.js";

initLayout();

const $ = (id) => document.getElementById(id);
const SUBJECT_LABEL = { cpp: "C++", python: "Python" };
const SOURCE_LABEL = { exam_link: "考试链接", lesson: "课后练习", practice: "课中练习" };
const PHASE_LABEL = { not_started: "未开始", running: "进行中", ended: "已结束" };
const ATTEMPT_STATUS = { ongoing: ["作答中", ""], submitted: ["已交卷", ""], expired: ["已过期", "gray"] };
const SUBMIT_KIND = { manual: "手动交卷", auto_timeout: "超时收卷", auto_close: "系统收卷" };
// 「哪一次算数」由链接的 score_policy 决定，与学员端候考页、排行榜同一口径。
const SCORE_POLICY = { best: "最好成绩", last: "最后一次", first: "首次成绩" };

// analysis：逐题分析的缓存，一场一份。openDetail 换场次时必须清掉。
const state = { page: 1, size: 20, total: 0, detail: null, analysis: null };
const attemptReview = createAttemptReview({
  mask: $("attemptMask"), title: $("attemptTitle"), body: $("attemptBody"), closeButton: $("attemptClose"),
});

function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

// ==================== 第一层：总览 ====================

async function loadOverview() {
  const params = new URLSearchParams({ page: String(state.page), size: String(state.size) });
  const keyword = $("sKeyword").value.trim();
  if (keyword) params.set("keyword", keyword);
  if ($("sType").value) params.set("paper_type", $("sType").value);
  if ($("sSubject").value) params.set("subject", $("sSubject").value);
  if ($("sSource").value) params.set("source", $("sSource").value);
  const payload = await adminRequest(`/exam-results?${params}`);
  state.total = payload.total;
  renderOverview(payload.items);
  renderPager();
}

function renderOverview(items) {
  // 人数与人次分开报。练习卷允许反复作答，一个学员刷 100 次时只给人次，
  // 看的人会以为来了 100 个学员——这正是运营反馈的那个现象。
  const participants = items.reduce((sum, row) => sum + row.participants, 0);
  const attempts = items.reduce((sum, row) => sum + row.attempts, 0);
  $("overviewStats").innerHTML = `
    <div class="stat"><b>${state.total}</b><span>场次</span></div>
    <div class="stat"><b>${participants}</b><span>参考人数（本页）</span></div>
    <div class="stat"><b>${attempts}</b><span>作答人次（本页）</span></div>
    <div class="stat"><b>${items.filter((row) => row.link.phase === "running").length}</b><span>进行中（本页）</span></div>`;

  $("overviewRows").innerHTML = items.map((row) => {
    const link = row.link;
    const statusTag = link.status === "disabled"
      ? '<span class="tag gray">已停用</span>'
      : `<span class="tag">${PHASE_LABEL[link.phase] || link.phase}</span>`;
    const score = row.score;
    return `<tr>
      <td><b>${escapeHtml(link.name)}</b></td>
      <td>${escapeHtml(row.paper.paper_id_no || "")} · ${escapeHtml(row.paper.title)}</td>
      <td><span class="tag">${escapeHtml(row.paper.paper_type)}</span></td>
      <td><span class="tag">${SUBJECT_LABEL[row.paper.subject] || escapeHtml(row.paper.subject || "")}</span></td>
      <td>${SOURCE_LABEL[row.source] || escapeHtml(row.source)}</td>
      <td>${statusTag}</td>
      <td>${row.participants}${row.attempts > row.participants ? `<span class="muted"> / ${row.attempts} 次</span>` : ""}</td>
      <td>${row.submitted_participants}</td>
      <td>${score ? score.avg : "—"}</td>
      <td>${score ? `${score.min} ~ ${score.max}` : "—"}</td>
      <td>${score && score.pass_rate !== null ? score.pass_rate + "%" : "—"}</td>
      <td><button class="btn-text link" type="button" data-open="${link.id}">查看明细</button></td>
    </tr>`;
  }).join("") || '<tr><td colspan="12"><div class="empty">没有符合条件的场次</div></td></tr>';

  document.querySelectorAll("[data-open]").forEach((btn) =>
    btn.addEventListener("click", () => openDetail(Number(btn.dataset.open))));
}

function renderPager() {
  const pages = Math.max(Math.ceil(state.total / state.size), 1);
  $("overviewFoot").innerHTML = `
    <span class="muted">共 ${state.total} 条</span><span class="spacer"></span>
    <button class="btn" id="prevPage" type="button" ${state.page <= 1 ? "disabled" : ""}>上一页</button>
    <span>${state.page} / ${pages}</span>
    <button class="btn" id="nextPage" type="button" ${state.page >= pages ? "disabled" : ""}>下一页</button>`;
  $("prevPage")?.addEventListener("click", () => { state.page -= 1; loadOverview().catch(onError); });
  $("nextPage")?.addEventListener("click", () => { state.page += 1; loadOverview().catch(onError); });
}

// ==================== 第二层：单场明细 ====================

async function openDetail(linkId) {
  const payload = await adminRequest(`/links/${linkId}/results`);
  state.detail = payload;
  $("overviewView").hidden = true;
  $("detailView").hidden = false;
  $("detailTitle").textContent = payload.link.name;
  $("detailTags").innerHTML =
    `<span class="tag">${escapeHtml(payload.paper.paper_type)}</span> ` +
    `<span class="tag">${SUBJECT_LABEL[payload.paper.subject] || escapeHtml(payload.paper.subject || "")}</span> ` +
    `<span class="tag gray">满分 ${payload.full_score}${payload.pass_score !== null ? ` / 及格 ${payload.pass_score}` : ""}</span>`;

  const s = payload.summary;
  // 平均分/区间/及格率的分母是**人数**（每人取算数的那一次），不是人次。
  // 副标题把口径写在脸上，省得有人拿它跟"作答人次"对不上而怀疑数据。
  $("detailStats").innerHTML = `
    <div class="stat"><b>${s.participants}</b><span>参考人数</span></div>
    <div class="stat"><b>${s.attempts}</b><span>作答人次</span></div>
    <div class="stat"><b>${s.submitted_participants}</b><span>已交人数</span></div>
    <div class="stat"><b>${s.avg ?? "—"}</b><span>平均分（按人）</span></div>
    <div class="stat"><b>${s.avg === null ? "—" : `${s.min} ~ ${s.max}`}</b><span>分数区间</span></div>
    <div class="stat"><b>${s.pass_rate === null ? "—" : s.pass_rate + "%"}</b><span>及格率（按人）</span></div>`;

  // 换一场就把上一场的逐题分析缓存丢掉，否则切到「逐题得分率」看到的是别人的卷
  state.analysis = null;
  // 不 await：分数分布用的是手上这份 payload，没有请求要等；catch 是因为 showView
  // 是 async，它的拒绝不会被 openDetail 的调用方接住。
  showView("dist").catch(onError);

  // 计分口径写进表头。链接可以配 best/last/first，不标出来的话，老师看到的分数
  // 与学员端候考页/排行榜显示的一致性无从判断。
  $("countedPolicyTip").textContent =
    `本场按${SCORE_POLICY[payload.link.score_policy] || payload.link.score_policy}计分`;
  renderStudents(payload.students);
}

// ==================== 四个分析视图 ====================
// 视图 1、4 用 openDetail 已经拿到的 payload，切换零延迟；
// 视图 2、3 共用 /links/{id}/item-analysis，**首次点进去才请求**，之后缓存在 state.analysis。
//
// 人少到画不出分布形状时，**换一种画法而不是不画**：一人一个点的点带图。
// 「样本过少，暂不展示」对老师是个坏答复——他手上明明有 8 个真实成绩想看。
// 12 是配合后端 _distribution_bins 的下界（4 桶）定的：再少每桶摊不到 3 个人。
// 分组那边的阈值一律以后端返回的 grouping 为准，前端不另定一个。
const MIN_FOR_HISTOGRAM = 12;

const VIEW_NOTE = {
  dist: "每人只计「算数的那一次」，与平均分、及格率同一批作答。",
  items: "按卷内顺序排，不按得分率排序——讲评是顺着卷子走的。",
  disc: "按总分前 / 后 27% 分组。区分度为负 = 低分组反而答得更好，多半是答案配错了。",
  time: "一个点一个学员，取算数的那一次。",
};

/** 每人一个点，取「算数的那一次」。点带图与用时散点共用同一批人，口径不能各取各的。 */
function countedPoints(payload) {
  return payload.students
    .filter((s) => s.counted && s.counted.total_score != null)
    .map((s) => ({
      name: s.user.username,
      score: s.counted.total_score,
      minutes: s.counted.duration_seconds == null
        ? null : Math.round(s.counted.duration_seconds / 60),
      // submit_kind 有 manual / auto_timeout / auto_close 三种，图上只分「手动」与「自动」
      submitKind: s.counted.submit_kind === "manual" ? "manual" : "auto",
    }));
}

async function showView(view) {
  document.querySelectorAll("#viewTabs button").forEach((btn) =>
    btn.classList.toggle("is-active", btn.dataset.view === view));
  const body = $("viewBody");
  const payload = state.detail;
  if (!payload) return;
  $("viewNote").textContent = VIEW_NOTE[view] || "";
  const people = payload.summary.submitted_participants;

  if (view === "dist") {
    if (!people) {
      charts.emptyState(body, "还没有人交卷，暂无分数分布。");
      return;
    }
    const shared = {
      fullScore: payload.full_score,
      passScore: payload.pass_score,
      avg: payload.summary.avg,
    };
    if (people < MIN_FOR_HISTOGRAM) {
      charts.renderScoreStrip(body, { ...shared, points: countedPoints(payload) });
      return;
    }
    charts.renderDistribution(body, {
      ...shared, distribution: payload.distribution, participants: people,
    });
    return;
  }

  if (view === "time") {
    charts.renderDurationScatter(body, {
      points: countedPoints(payload).filter((p) => p.minutes != null),
      fullScore: payload.full_score,
      passScore: payload.pass_score,
      durationMinutes: payload.link.duration_minutes,
    });
    return;
  }

  // ---- 视图 2 / 3：按需拉一次聚合 ----
  body.innerHTML = '<div class="chart-empty">正在统计…</div>';
  try {
    if (!state.analysis) state.analysis = await adminRequest(`/links/${payload.link.id}/item-analysis`);
  } catch (error) {
    charts.emptyState(body, error.message || "逐题分析加载失败。");
    return;
  }
  const analysis = state.analysis;
  if (!analysis.items.length) {
    charts.emptyState(body, "这张卷还没有题目。");
    return;
  }
  if (view === "items") {
    charts.renderItemRates(body, { items: analysis.items });
    return;
  }
  const grouping = analysis.grouping;
  if (!grouping.enabled) {
    charts.emptyState(
      body,
      `已交卷 ${grouping.participants} 人，不足 ${grouping.min_participants} 人。` +
      "前 / 后 27% 分组后每组不到 5 人，单个学员就能把区分度拉动 0.5——" +
      "这种规模下算出来的是噪声，不是统计量。",
    );
    return;
  }
  charts.renderDiscrimination(body, { items: analysis.items, grouping });
  // 20–36 人：图照画，但必须标明是参考值。每组不足 10 人时单个学员能把 D 拉动 0.3，
  // 不标出来老师会拿它当准数用——那比不给这张图更糟。
  if (!grouping.stable) {
    $("viewNote").textContent =
      `${VIEW_NOTE.disc} 已交卷 ${grouping.participants} 人（每组 ${grouping.group_size} 人），` +
      `不足 ${grouping.stable_participants} 人，区分度仅供参考：单个学员的影响约 ±0.3。`;
  }
}

// 一学员一行；有多次作答的行可展开看历史，每条历史再点进逐题回看。
function renderStudents(students) {
  $("attemptRows").innerHTML = students.map((student, index) => {
    const counted = student.counted;
    const failed = student.has_judge_failed ? ' <span class="tag danger">判题异常</span>' : "";
    const ongoing = student.ongoing ? ' <span class="tag">作答中</span>' : "";
    const repeated = student.attempt_count > 1;
    return `<tr class="student-row" data-student="${index}">
      <td>${repeated ? `<button class="expander" type="button" data-toggle="${index}" aria-expanded="false">▸</button>` : ""}${escapeHtml(student.user.username)}</td>
      <td>${student.attempt_count}${repeated ? ` <span class="muted">次</span>` : ""}</td>
      <td>${counted ? "" : '<span class="tag gray">未交卷</span>'}${failed}${ongoing}</td>
      <td>${counted ? `<span class="score-num">${counted.total_score}</span>` : "—"}</td>
      <td>${counted ? fmtDuration(counted.duration_seconds) : "—"}</td>
      <td>${counted ? (SUBMIT_KIND[counted.submit_kind] || "—") : "—"}</td>
      <td>${counted ? fmtTime(counted.started_at) : "—"}</td>
      <td>${counted ? (fmtTime(counted.submitted_at) || "—") : "—"}</td>
      <td>${counted ? `<button class="btn-text link" type="button" data-review="${counted.attempt_id}">答卷回看</button>` : ""}</td>
    </tr>` + (repeated ? historyRow(student, index) : "");
  }).join("") || '<tr><td colspan="9"><div class="empty">还没有人进过这场考试</div></td></tr>';

  document.querySelectorAll("[data-toggle]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const host = $(`history-${btn.dataset.toggle}`);
      const open = host.hidden;
      host.hidden = !open;
      btn.textContent = open ? "▾" : "▸";
      btn.setAttribute("aria-expanded", String(open));
    }));
  document.querySelectorAll("[data-review]").forEach((btn) =>
    btn.addEventListener("click", () => attemptReview.open(Number(btn.dataset.review), btn).catch(onError)));
}

function historyRow(student, index) {
  const rows = student.attempts.map((a) => {
    const [statusLabel, tone] = ATTEMPT_STATUS[a.status] || [a.status, ""];
    // 标出"算数的那一次"：不标的话，7 次记录里哪一次进了统计全靠猜
    const isCounted = student.counted && a.attempt_id === student.counted.attempt_id;
    return `<tr${isCounted ? ' class="is-counted"' : ""}>
      <td>第 ${a.attempt_no} 次${isCounted ? ' <span class="tag">计分</span>' : ""}</td>
      <td><span class="tag ${tone}">${statusLabel}</span>${a.has_judge_failed ? ' <span class="tag danger">判题异常</span>' : ""}</td>
      <td>${a.total_score === null ? "—" : a.total_score}</td>
      <td>${fmtDuration(a.duration_seconds)}</td>
      <td>${fmtTime(a.started_at)}</td>
      <td>${fmtTime(a.submitted_at) || "—"}</td>
      <td>${a.status === "submitted"
        ? `<button class="btn-text link" type="button" data-review="${a.attempt_id}">答题详情</button>` : ""}</td>
    </tr>`;
  }).join("");
  return `<tr class="history-host" id="history-${index}" hidden><td colspan="9">
    <table class="history-table"><thead><tr>
      <th>次序</th><th>状态</th><th>得分</th><th>用时</th><th>开考</th><th>交卷</th><th></th>
    </tr></thead><tbody>${rows}</tbody></table>
  </td></tr>`;
}

// ==================== 导出 CSV ====================

function exportCsv() {
  const d = state.detail;
  if (!d) return;
  // 导出每一次作答（不是只导代表成绩）：老师拿 CSV 多半就是要看某人练了几次、
  // 分数怎么变的。"是否计分"一列标出哪一行进了统计。
  const head = ["学员", "第几次", "是否计分", "状态", "总分", "用时(秒)", "交卷方式",
                "开考时间", "交卷时间", "备注"];
  const lines = d.students.flatMap((student) =>
    student.attempts.map((a) => [
      student.user.username, a.attempt_no,
      student.counted && a.attempt_id === student.counted.attempt_id ? "计分" : "",
      (ATTEMPT_STATUS[a.status] || [a.status])[0],
      a.total_score ?? "", a.duration_seconds ?? "", SUBMIT_KIND[a.submit_kind] || "",
      fmtTime(a.started_at), fmtTime(a.submitted_at),
      a.has_judge_failed ? "判题异常（部分题未计分）" : "",
    ]));
  const csv = "﻿" + [head, ...lines]
    .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
    .join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  link.download = `${d.link.name}-成绩.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// ==================== 事件与入口 ====================

function onError(error) {
  toast(error?.message || "请求失败，请稍后再试。", "error");
}

$("searchBtn").addEventListener("click", () => { state.page = 1; loadOverview().catch(onError); });
$("backBtn").addEventListener("click", () => {
  state.detail = null;
  state.analysis = null;
  charts.hideTip();   // 提示框挂在 body 上，返回总览时不会跟着面板一起消失
  $("detailView").hidden = true;
  $("overviewView").hidden = false;
  history.replaceState(null, "", "reports.html");
});
// 事件委托挂在容器上，不逐个绑按钮——四个 tab 是静态节点，但委托一行搞定
$("viewTabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-view]");
  if (button) showView(button.dataset.view).catch(onError);
});
$("exportBtn").addEventListener("click", exportCsv);

// 从考试链接页带 ?link_id= 跳入时直接展开单场明细。
const entryLinkId = Number(new URLSearchParams(location.search).get("link_id"));
if (entryLinkId) openDetail(entryLinkId).catch(onError);
else loadOverview().catch(onError);
