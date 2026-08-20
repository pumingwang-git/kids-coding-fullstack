import { adminRequest } from "./admin-api.js";
import { initLayout } from "./admin-layout.js";

initLayout();

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 10;
const state = { classes: [], classId: null, studentPage: 1, inactiveDays: "" };

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function formatDate(value) {
  if (!value) return "暂无记录";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function formatNumber(value) {
  return value == null ? "名单未知" : String(value);
}

function setPanelState(host, message, kind = "empty") {
  host.innerHTML = `<p class="teaching-inline-state ${kind}">${escapeHtml(message)}</p>`;
}

function requestPath(path, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== "" && value != null) query.set(key, String(value)); });
  return query.size ? `${path}?${query}` : path;
}

function selectedClass() {
  return state.classes.find((item) => Number(item.id) === Number(state.classId));
}

function renderClassOptions() {
  const select = $("classSelect");
  select.innerHTML = state.classes.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name || item.title || `班级 ${item.id}`)}</option>`).join("");
  select.value = String(state.classId);
  select.disabled = !state.classes.length;
}

function insightMetrics(payload) {
  const insight = payload?.insight || payload || {};
  return Object.entries(insight).filter(([, value]) => typeof value === "number");
}

function renderOverview(payload) {
  const metrics = insightMetrics(payload);
  const current = selectedClass();
  $("overviewHint").textContent = current?.course_title || current?.course?.title || "";
  $("overviewMetrics").innerHTML = metrics.map(([key, value]) => `<div class="teaching-metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(key.replace(/_/g, " "))}</span></div>`).join("");
  if (!metrics.length) setPanelState($("overviewMetrics"), "暂未返回可展示的概览数据。");
}

function studentAction(row) {
  const endpoint = row.profile_endpoint || row.student?.profile_endpoint;
  if (!endpoint) return '<span class="muted">—</span>';
  return `<a class="btn-text" href="${escapeHtml(endpoint)}">查看档案</a>`;
}

function renderStudents(payload) {
  const rows = payload.items || [];
  $("studentRows").innerHTML = rows.map((row) => `<tr>
    <td data-label="学员">${escapeHtml(row.student?.username)}</td>
    <td data-label="最近活动">${escapeHtml(formatDate(row.last_activity_at))}</td>
    <td data-label="未学习天数">${row.never_active ? "从未学习" : escapeHtml(row.inactive_days ?? "—")}</td>
    <td data-label="操作">${studentAction(row)}</td>
  </tr>`).join("");
  if (!rows.length) $("studentRows").innerHTML = '<tr><td colspan="4"><p class="teaching-inline-state">当前条件下没有学员记录。</p></td></tr>';
  const total = Number(payload.total || 0);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  $("studentPagination").innerHTML = `<span>共 ${total} 位</span><span class="spacer"></span><button class="btn" type="button" data-student-page="prev" ${state.studentPage <= 1 ? "disabled" : ""}>上一页</button><button class="btn" type="button" data-student-page="next" ${state.studentPage >= pages ? "disabled" : ""}>下一页</button>`;
}

function personList(rows) {
  if (!rows?.length) return "";
  return `<div class="teaching-names">${rows.map((row) => `<span>${escapeHtml(row.student?.username)}</span>`).join("")}</div>`;
}

function taskSummary(row, includeAttempts = false) {
  const details = [
    `名单 ${formatNumber(row.roster_people)}`,
    `已回传 ${formatNumber(row.submitted_people)}`,
    `未提交 ${formatNumber(row.not_submitted_people)}`,
  ];
  if (includeAttempts && row.submitted_attempts != null) details.push(`提交人次 ${row.submitted_attempts}`);
  return details.map((item) => `<span>${escapeHtml(item)}</span>`).join("");
}

function renderHomework(payload) {
  const host = $("homeworkRows");
  const rows = payload.items || [];
  if (!rows.length) return setPanelState(host, "当前班级没有可展示的作业数据。");
  host.innerHTML = rows.map((row, index) => `<details class="teaching-task" ${index === 0 ? "open" : ""}><summary><span>${escapeHtml(row.title || row.name)}</span><span class="teaching-task-meta">${taskSummary(row, true)}</span></summary><div class="teaching-task-body">${personList(row.not_submitted)}<p class="muted">${escapeHtml(row.phase_label || "")}</p></div></details>`).join("");
}

function renderExams(payload) {
  const host = $("examRows");
  const rows = payload.items || [];
  if (!rows.length) return setPanelState(host, "当前班级没有可展示的考试数据。");
  host.innerHTML = rows.map((row) => `<details class="teaching-task"><summary><span>${escapeHtml(row.name || row.title)}</span><span class="teaching-task-meta">${taskSummary(row, true)}</span></summary><div class="teaching-task-body">${personList(row.not_submitted)}<p class="muted">${escapeHtml(row.phase_label || "")}</p></div></details>`).join("");
}

function renderReview(payload) {
  const host = $("reviewRows");
  const rows = payload.items || [];
  if (!rows.length) return setPanelState(host, "当前没有需要处理的项目。");
  host.innerHTML = rows.map((row) => `<div class="teaching-queue-row"><div><strong>${escapeHtml(row.student?.username || row.student_name || `提交 ${row.submission_id}`)}</strong><span>${escapeHtml(formatDate(row.submitted_at))}</span></div>${row.review_endpoint ? `<a class="btn-text" href="${escapeHtml(row.review_endpoint)}">打开</a>` : ""}</div>`).join("");
}

function percentage(row) {
  const value = row.practice_correct_rate ?? row.paper_score_rate ?? row.score_rate;
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

function renderWeakItems(payload) {
  const host = $("weakRows");
  const rows = payload.items || [];
  host.innerHTML = rows.map((row) => `<tr><td data-label="题目">${escapeHtml(row.title || row.problem_id_no || row.sort_order || "—")}</td><td data-label="来源">${escapeHtml(row.source_title || row.source || "—")}</td><td data-label="正确率">${escapeHtml(percentage(row))}</td></tr>`).join("");
  if (!rows.length) host.innerHTML = '<tr><td colspan="3"><p class="teaching-inline-state">当前没有可分析的题目数据。</p></td></tr>';
}

async function loadStudents() {
  const payload = await adminRequest(requestPath(`/teaching/classes/${state.classId}/students`, { page: state.studentPage, page_size: PAGE_SIZE, inactive_days_gte: state.inactiveDays, sort: "-last_activity_at" }));
  renderStudents(payload);
}

async function loadWorkbench() {
  $("workbench").setAttribute("aria-busy", "true");
  const base = `/teaching/classes/${state.classId}`;
  const results = await Promise.allSettled([
    adminRequest(`${base}/overview`), loadStudents(), adminRequest(`${base}/homework`), adminRequest(`${base}/exams`), adminRequest("/teaching/review-queue"), adminRequest(`${base}/weak-items`),
  ]);
  const renderers = [renderOverview, null, renderHomework, renderExams, renderReview, renderWeakItems];
  const errorHosts = [$("overviewMetrics"), $("studentRows"), $("homeworkRows"), $("examRows"), $("reviewRows"), $("weakRows")];
  results.forEach((result, index) => {
    if (result.status === "fulfilled" && renderers[index]) renderers[index](result.value);
    if (result.status === "rejected") {
      const message = result.reason?.message || "加载失败，请稍后重试。";
      if (index === 1 || index === 5) {
        errorHosts[index].innerHTML = `<tr><td colspan="${index === 1 ? 4 : 3}"><p class="teaching-inline-state">${escapeHtml(message)}</p></td></tr>`;
      } else setPanelState(errorHosts[index], message);
    }
  });
  const failed = results.some((result) => result.status === "rejected");
  if (failed) $("classesState").textContent = "部分数据暂不可用，可稍后刷新重试。";
  else $("classesState").textContent = "";
  $("workbench").removeAttribute("aria-busy");
}

async function loadClasses() {
  try {
    const payload = await adminRequest("/teaching/classes");
    state.classes = payload.items || [];
    if (!state.classes.length) {
      $("classesState").textContent = "当前没有可查看的班级。";
      return;
    }
    state.classId = state.classes[0].id;
    renderClassOptions();
    $("classesState").textContent = "";
    $("workbench").hidden = false;
    await loadWorkbench();
  } catch (error) {
    $("classesState").textContent = `${error.message || "加载失败"} 请刷新页面后重试。`;
  }
}

$("classSelect").addEventListener("change", async (event) => {
  state.classId = Number(event.target.value);
  state.studentPage = 1;
  await loadWorkbench();
});
$("refreshBtn").addEventListener("click", loadWorkbench);
$("studentFilter").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.inactiveDays = $("inactiveDays").value;
  state.studentPage = 1;
  await loadStudents();
});
$("clearStudentFilter").addEventListener("click", async () => {
  $("inactiveDays").value = "";
  state.inactiveDays = "";
  state.studentPage = 1;
  await loadStudents();
});
$("studentPagination").addEventListener("click", async (event) => {
  const direction = event.target.dataset.studentPage;
  if (!direction) return;
  state.studentPage += direction === "next" ? 1 : -1;
  await loadStudents();
});

loadClasses();
