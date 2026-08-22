// 课时作业成绩：只消费管理端真实接口，作答/计分口径由服务端统一裁决。
//
// 呈现契约（lesson_homework_kinds.py）：表头（columns）、统计卡（stats）、筛选下拉
// （filters）、类型元数据（kinds）与单元格文案（cells）全部由接口下发，页面不持有
// 任何作业类型、状态或交卷方式的取值表。红线见 lesson_homework_kinds.py 文件头
// 第三段：成绩链路（本文件）禁止出现 `if kind == "scratch"` 这类分支——新增一种
// 课时作业 = 服务端加一个 kind，本页一行都不用改。
//
// 动作按 cells.actions[].type 派发，页面不认识动作背后的类型，只认识能力表里的键：
//   open_detail      打开这份作业的成绩详情
//   attempt_review   整卷作业的单次答卷回看（富文本逐题）
//   record_detail    一条提交记录的只读详情（快照与反馈，字段成对下发）
//   scratch_studio   打开提交时刻冻结的 Studio 只读快照
import { initLayout } from "./admin-layout.js";
import { adminRequest } from "./admin-api.js";
import { closeMask, escapeHtml, fmtTime, openMask, toast } from "./admin-ui.js";
import { createAttemptReview } from "./admin-attempt-review.js";
import { studioReviewUrl } from "./admin-scratch-core.js";

initLayout();

const $ = (id) => document.getElementById(id);

const state = {
  courseId: "", sectionId: "", lessonId: "", keyword: "", kind: "", status: "",
  page: 1, size: 100, total: 0, serverNow: null,
  columns: [], filters: [], tree: [], courses: [],
  detail: null, detailPage: 1, detailPageSize: 50, histories: new Map(),
};

const attemptReview = createAttemptReview({
  mask: $("attemptMask"), title: $("attemptTitle"), body: $("attemptBody"), closeButton: $("attemptClose"),
});

// ==================== 单元格渲染 ====================

// 服务端在 cell() 里已把文案成型，但时间仍以 ISO 下发（学员行里的 started_at /
// submitted_at、截止说明里的「截止于 …」）。按《38、UTC与时区规范》由前端落到
// 本地时区显示。服务端改为下发成型时间后，这个替换可以直接删掉。
const ISO_DATETIME = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?/g;
const humanize = (text) => String(text ?? "").replace(ISO_DATETIME, (iso) => fmtTime(iso) || iso);

const toneAttr = (tone) => (tone ? ` class="tone-${escapeHtml(tone)}"` : "");
const alignAttr = (column) => (column.align === "right" ? ' class="col-right"' : "");

function renderBadges(badges) {
  return (badges || [])
    .map((badge) => `<span class="tag${badge.tone ? ` tone-${escapeHtml(badge.tone)}` : ""}">${escapeHtml(humanize(badge.label))}</span>`)
    .join("") || "—";
}

// 动作字段透传：把整个动作对象（source + type 专属字段，如 attempt_id /
// record_id / submission_id）编码进 data-action，派发时统一解码。前端不按列名
// 或作业类型推断动作该带什么参数。
function renderActions(actions, sourceId) {
  return (actions || []).map((action) => {
    const meta = { source: String(sourceId ?? ""), ...action };
    return `<button class="btn-text link" type="button" data-action="${escapeHtml(JSON.stringify(meta))}">${escapeHtml(action.label || "")}</button>`;
  }).join("");
}

function renderCell(cell, sourceId) {
  if (!cell) return "—";
  if (cell.actions) return `<div class="cell-actions">${renderActions(cell.actions, sourceId)}</div>`;
  if (cell.badges) return `<div class="cell-badges">${renderBadges(cell.badges)}</div>`;
  const badge = cell.badge ? ` <span class="tag">${escapeHtml(cell.badge)}</span>` : "";
  const sub = cell.sub ? `<small>${escapeHtml(humanize(cell.sub))}</small>` : "";
  return `<div class="cell"><div class="cell-main"><b${toneAttr(cell.tone)}>${escapeHtml(humanize(cell.text))}</b>${badge}</div>${sub}</div>`;
}

function renderHead(hostId, columns) {
  $(hostId).innerHTML = `<tr>${columns.map((column) =>
    `<th${alignAttr(column)}${column.width ? ` style="width:${escapeHtml(column.width)}"` : ""}>${escapeHtml(column.label)}</th>`
  ).join("")}</tr>`;
}

const emptyRow = (columns, text) =>
  `<tr><td colspan="${columns.length || 1}"><div class="empty">${escapeHtml(text)}</div></td></tr>`;

// ==================== 总览 ====================

function renderStatCards(hostId, tiles) {
  $(hostId).innerHTML = (tiles || []).map((tile) =>
    `<div class="stat"><b>${escapeHtml(tile.text)}</b><span>${escapeHtml(tile.label)}</span></div>`).join("");
}

function renderCourseSelect() {
  $("courseSelect").innerHTML = '<option value="">全部课包</option>'
    + state.courses.map((course) => `<option value="${course.id}">${escapeHtml(course.title)}</option>`).join("");
  $("courseSelect").value = state.courseId;
}

function renderLocationFilters() {
  const course = state.tree.find((item) => String(item.id) === state.courseId);
  const sections = course?.sections || [];
  const section = sections.find((item) => String(item.id) === state.sectionId);
  const lessons = section?.lessons || [];

  $("sectionSelect").innerHTML = '<option value="">全部章节</option>'
    + sections.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("");
  $("sectionSelect").value = state.sectionId;
  $("sectionSelect").disabled = !state.courseId || !sections.length;

  $("lessonSelect").innerHTML = '<option value="">全部课时</option>'
    + lessons.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("");
  $("lessonSelect").value = state.lessonId;
  $("lessonSelect").disabled = !state.sectionId || !lessons.length;
}

// 筛选区由接口的 filters 描述生成（作业类型、作业状态各一个下拉），取值表在服务端，
// 页面不编。每次刷新重绘以更新类型计数（count 由服务端按当前筛选范围算）；渲染后
// 把 state 里的值回填，保证换页 / 重载后筛选条件不丢。
function renderFilters() {
  const host = $("filterForm");
  host.querySelectorAll("[data-filter-key]").forEach((node) => node.remove());
  for (const filter of state.filters || []) {
    const key = filter.key;
    const field = document.createElement("div");
    field.className = "field";
    field.dataset.filterKey = key;
    field.innerHTML = `<label for="${escapeHtml(key)}Select">${escapeHtml(filter.label)}</label>`
      + `<select id="${escapeHtml(key)}Select" name="${escapeHtml(key)}" data-filter-select="${escapeHtml(key)}"><option value="">${escapeHtml(filter.placeholder || "全部")}</option>`
      + (filter.options || []).map((option) =>
        `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}${option.count != null ? `（${option.count}）` : ""}</option>`).join("")
      + "</select>";
    host.insertBefore(field, host.querySelector(".search-actions"));
    const select = field.querySelector("select");
    if (select && state[key] !== undefined) select.value = state[key] || "";
  }
}

function activePath() {
  for (const course of state.tree) {
    for (const section of course.sections) {
      const lesson = state.lessonId
        ? section.lessons.find((item) => String(item.id) === state.lessonId)
        : null;
      if (lesson) return `${course.title} / ${section.title} / ${lesson.title}`;
      if (!state.lessonId && String(section.id) === state.sectionId) return `${course.title} / ${section.title}`;
    }
  }
  const course = state.courses.find((item) => String(item.id) === state.courseId);
  return course ? `${course.title} / 全部章节` : "全部课包 / 全部章节";
}

function renderOverviewPager(shown) {
  const pages = Math.max(1, Math.ceil(state.total / state.size));
  const start = state.total ? (state.page - 1) * state.size + 1 : 0;
  const end = start ? start + shown - 1 : 0;
  $("overviewFoot").innerHTML = `<span class="muted">显示第 ${start}–${end} 份 / 共 ${state.total} 份 · 状态由服务端判定${state.serverNow ? `（${fmtTime(state.serverNow)}）` : ""}</span>`
    + '<span class="spacer"></span>'
    + `<button class="btn" type="button" data-page="prev"${state.page === 1 ? " disabled" : ""}>上一页</button>`
    + `<button class="btn" type="button" data-page="next"${state.page >= pages ? " disabled" : ""}>下一页</button>`;
}

function renderOverview(rows) {
  renderHead("overviewHead", state.columns);
  $("overviewRows").innerHTML = rows.map((row) =>
    `<tr class="data-row">${state.columns.map((column) =>
      `<td data-label="${escapeHtml(column.label)}"${alignAttr(column)}>${renderCell(row.cells?.[column.key], row.source_id)}</td>`
    ).join("")}</tr>`).join("")
    || emptyRow(state.columns, "当前筛选范围内没有课时作业");
  $("activePath").textContent = activePath();
  renderOverviewPager(rows.length);
}

async function loadOverview() {
  // 筛选与分页都在服务端：前端再过滤一次的话，翻到第二页就只筛得到当前这一页。
  const params = new URLSearchParams({ page: String(state.page), size: String(state.size) });
  if (state.kind) params.set("kind", state.kind);
  if (state.status) params.set("status", state.status);
  if (state.keyword) params.set("keyword", state.keyword);
  if (state.courseId) params.set("course_id", state.courseId);
  if (state.sectionId) params.set("section_id", state.sectionId);
  if (state.lessonId) params.set("lesson_id", state.lessonId);
  const payload = await adminRequest(`/lesson-homework-results?${params}`);

  state.columns = payload.columns || [];
  state.filters = payload.filters || [];
  state.total = payload.total || 0;
  state.serverNow = payload.server_now || null;
  // 目录树是服务端按本次结果集生成的：选中某个章节后接口只回这一个章节，直接覆盖会让
  // 侧栏塌成一条、退不回去。所以只在「未选定章节 / 课时」时刷新树。
  if (!state.sectionId && !state.lessonId) {
    state.tree = payload.tree || [];
    if (!state.courseId) state.courses = state.tree;
  }
  renderCourseSelect();
  renderLocationFilters();
  renderFilters();
  renderStatCards("overviewStats", payload.stats);
  renderOverview(payload.items || []);
}

// ==================== 详情 ====================

function visibleStudents() {
  const students = state.detail?.students || [];
  const start = (state.detailPage - 1) * state.detailPageSize;
  return students.slice(start, start + state.detailPageSize);
}

function renderDetailPager() {
  const total = state.detail?.students?.length || 0;
  const pages = Math.max(1, Math.ceil(total / state.detailPageSize));
  const start = total ? (state.detailPage - 1) * state.detailPageSize + 1 : 0;
  const end = Math.min(state.detailPage * state.detailPageSize, total);
  $("detailFoot").innerHTML = `<span class="muted">显示 ${start}–${end} / ${total} 位学员</span>`
    + '<span class="spacer"></span>'
    + `<button class="btn" type="button" data-detail="prev"${state.detailPage === 1 ? " disabled" : ""}>上一页</button>`
    + `<button class="btn" type="button" data-detail="next"${state.detailPage >= pages ? " disabled" : ""}>下一页</button>`;
}

function renderStudents() {
  const columns = state.detail?.columns || [];
  const sourceId = state.detail?.source_id;
  $("attemptRows").innerHTML = visibleStudents().map((student, index) => {
    const rowId = `${state.detailPage}-${index}`;
    // 只有反复作答的学员才给展开器——服务端用 history_endpoint 直接点名，页面不判次数。
    const expander = student.history_endpoint
      ? `<button class="expander" type="button" data-history="${rowId}" data-endpoint="${escapeHtml(student.history_endpoint)}" aria-controls="history-${rowId}" aria-expanded="false" aria-label="展开 ${escapeHtml(student.name || "")} 的作答历史">展开</button>`
      : "";
    const cells = columns.map((column, columnIndex) => {
      const body = renderCell(student.cells?.[column.key], sourceId);
      return `<td data-label="${escapeHtml(column.label)}"${alignAttr(column)}>${
        columnIndex === 0 ? `<div class="expander-cell">${expander}${body}</div>` : body
      }</td>`;
    }).join("");
    return `<tr class="data-row">${cells}</tr>`
      + (student.history_endpoint ? `<tr class="history-host" id="history-${rowId}" hidden><td colspan="${columns.length}"></td></tr>` : "");
  }).join("") || emptyRow(columns, state.detail?.empty_hint || "还没有学员开始这份作业");
  renderDetailPager();
}

async function toggleHistory(button) {
  const host = $(`history-${button.dataset.history}`);
  if (button.getAttribute("aria-expanded") === "true") {
    host.hidden = true;
    button.textContent = "展开";
    button.setAttribute("aria-expanded", "false");
    return;
  }
  const endpoint = button.dataset.endpoint;
  let history = state.histories.get(endpoint);
  if (!history) {
    button.disabled = true;
    button.textContent = "加载中";
    try {
      history = await adminRequest(endpoint);
      state.histories.set(endpoint, history);
    } finally {
      button.disabled = false;
    }
  }
  const columns = history.columns || [];
  const sourceId = state.detail?.source_id;
  host.querySelector("td").innerHTML = '<div class="table-wrap history-wrap"><table class="history-table">'
    + `<thead><tr>${columns.map((column) => `<th${alignAttr(column)}>${escapeHtml(column.label)}</th>`).join("")}</tr></thead>`
    + `<tbody>${(history.rows || []).map((row) => `<tr>${columns.map((column, index) => {
      const body = renderCell(row.cells?.[column.key], sourceId);
      return `<td${alignAttr(column)}>${
        index === 0 ? `<div class="expander-cell">${body}${row.counted ? '<span class="tag">计分</span>' : ""}</div>` : body
      }</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>`;
  host.hidden = false;
  button.textContent = "收起";
  button.setAttribute("aria-expanded", "true");
}

async function openDetail(blockId) {
  const payload = await adminRequest(`/lesson-homework/${blockId}/results`);
  state.detail = payload;
  state.detailPage = 1;
  state.histories = new Map();
  $("overviewView").hidden = true;
  $("detailView").hidden = false;
  $("detailPath").textContent = `${payload.course.title} / ${payload.section.title} / ${payload.lesson.title}`;
  $("detailTitle").textContent = payload.homework.title;
  $("detailTags").innerHTML = (payload.tags || []).map((tag) =>
    `<span class="tag${tag.tone ? ` tone-${escapeHtml(tag.tone)}` : ""}">${escapeHtml(humanize(tag.label))}</span>`).join("");
  // 口径说明与类型名都是类型知识，由服务端下发，页面不拼。
  $("detailKind").textContent = payload.kind_label || "课时作业";
  $("detailInsight").textContent = payload.insight || "";
  renderStatCards("detailStats", payload.stats);
  renderHead("detailHead", payload.columns || []);
  renderStudents();
}

// ==================== 记录详情弹窗 ====================

// 通用记录详情：服务端给 { title, note, fields: [{ label, value, tone? }] }，
// 这里只排版，不认识「快照 / 判定 / 反馈」这些概念。
const recordModal = {
  releaseFocus: null,
  returnFocus: null,
  open(payload, trigger) {
    this.returnFocus = trigger;
    $("recordTitle").textContent = payload.title || "记录详情";
    $("recordFields").innerHTML = (payload.fields || []).map((field) =>
      `<div class="record-field"><dt>${escapeHtml(field.label)}</dt><dd${field.tone ? ` class="tone-${escapeHtml(field.tone)}"` : ""}>${escapeHtml(humanize(field.value))}</dd></div>`).join("");
    $("recordNote").textContent = payload.note || "";
    this.releaseFocus = openMask($("recordMask"), { focusSelector: "#recordClose" });
  },
  close() {
    if (!this.releaseFocus) return;
    closeMask($("recordMask"), this.releaseFocus);
    this.releaseFocus = null;
    this.returnFocus?.focus?.();
    this.returnFocus = null;
  },
};

$("recordClose").addEventListener("click", () => recordModal.close());
$("recordOk").addEventListener("click", () => recordModal.close());
$("recordMask").addEventListener("click", (event) => { if (event.target === $("recordMask")) recordModal.close(); });
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("recordMask").hidden) recordModal.close();
});

async function openRecord(blockId, recordId, trigger) {
  const payload = await adminRequest(`/lesson-homework/${blockId}/records/${recordId}`);
  recordModal.open(payload, trigger);
}

// ==================== 导出 ====================

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function cellText(cell) {
  if (!cell) return "";
  if (cell.badges) return (cell.badges || []).map((badge) => badge.label).join(" / ");
  if (cell.actions) return "";
  const main = cell.text === "—" ? "" : humanize(cell.text);
  return cell.sub ? `${main}（${humanize(cell.sub)}）` : main;
}

function exportDetailCsv() {
  const detail = state.detail;
  if (!detail) {
    toast("请先打开一份作业成绩后再导出。", "error");
    return;
  }
  const columns = (detail.columns || []).filter((column) => column.key !== "actions");
  const rows = [
    ["课程", detail.course.title],
    ["章节", detail.section.title],
    ["课时", detail.lesson.title],
    ["作业", detail.homework.title],
    ["作业来源", `${detail.kind_label || ""} · ${detail.subtitle || ""}`],
    [],
    columns.map((column) => column.label),
    ...(detail.students || []).map((student) => columns.map((column) => cellText(student.cells?.[column.key]))),
  ];
  const csv = `﻿${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${String(detail.homework.title || "课时作业成绩").replace(/[\\/:*?"<>|]/g, "_")}-成绩.csv`;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  toast(`已导出 ${detail.students?.length || 0} 位学员的成绩。`);
}

// ==================== 事件 ====================

function onError(error) { toast(error?.message || "请求失败，请稍后再试。", "error"); }

function onLoadError(error) {
  onError(error);
  $("overviewErrorText").textContent = error?.message || "列表加载失败。";
  $("overviewError").hidden = false;
}

function reload() {
  $("overviewError").hidden = true;
  loadOverview().catch(onLoadError);
}

function dispatchAction(button) {
  let action;
  try {
    action = JSON.parse(button.dataset.action || "{}");
  } catch {
    toast("操作数据无效，请刷新页面重试。", "error");
    return;
  }
  const type = action.type;
  if (type === "open_detail") { openDetail(Number(action.source)).catch(onError); return; }
  if (type === "attempt_review") { attemptReview.open(Number(action.attempt_id), button).catch(onError); return; }
  if (type === "record_detail") { openRecord(Number(action.source), Number(action.record_id), button).catch(onError); return; }
  if (type === "scratch_studio") { openScratchStudio(action); return; }
  toast(`尚未支持的操作：${type || "未知"}`, "error");
}

function openScratchStudio(action) {
  const submissionId = Number(action.submission_id);
  if (!submissionId) {
    toast("缺少提交编号，无法打开 Studio 快照。", "error");
    return;
  }
  // 按提交 id 打开「提交时冻结的那一版」只读快照（admin_review），不是挑战当前初始项目。
  window.open(studioReviewUrl(submissionId), "_blank", "noopener");
}

for (const host of [$("overviewRows"), $("attemptRows")]) {
  host.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]");
    if (action) { dispatchAction(action); return; }
    const history = event.target.closest("[data-history]");
    if (history) toggleHistory(history).catch(onError);
  });
}

$("courseSelect").addEventListener("change", (event) => {
  state.courseId = event.target.value;
  state.sectionId = ""; state.lessonId = ""; state.page = 1;
  reload();
});

$("sectionSelect").addEventListener("change", (event) => {
  state.sectionId = event.target.value;
  state.lessonId = ""; state.page = 1;
  reload();
});

$("lessonSelect").addEventListener("change", (event) => {
  state.lessonId = event.target.value;
  state.page = 1;
  reload();
});

// 「筛选」是 <form> 里的 submit 按钮：不拦下来会整页刷新，筛选条件反而丢了。
$("filterForm").addEventListener("submit", (event) => {
  event.preventDefault();
  state.keyword = $("keywordInput").value.trim();
  for (const select of $("filterForm").querySelectorAll("[data-filter-select]")) {
    const key = select.dataset.filterSelect;
    if (key in state) state[key] = select.value;
  }
  state.page = 1;
  reload();
});

$("overviewFoot").addEventListener("click", (event) => {
  const button = event.target.closest("[data-page]");
  if (!button) return;
  state.page += button.dataset.page === "next" ? 1 : -1;
  reload();
});

$("detailFoot").addEventListener("click", (event) => {
  const button = event.target.closest("[data-detail]");
  if (!button) return;
  state.detailPage += button.dataset.detail === "next" ? 1 : -1;
  renderStudents();
});

$("overviewRetry").addEventListener("click", reload);
$("backBtn").addEventListener("click", () => { $("detailView").hidden = true; $("overviewView").hidden = false; });
$("exportBtn").addEventListener("click", exportDetailCsv);

reload();
