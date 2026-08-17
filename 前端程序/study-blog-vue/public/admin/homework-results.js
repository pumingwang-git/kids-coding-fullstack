// 课时作业成绩：只消费管理端真实接口，作答/计分口径由服务端统一裁决。
import { initLayout } from "./admin-layout.js";
import { adminRequest } from "./admin-api.js";
import { escapeHtml, fmtTime, toast } from "./admin-ui.js";
import { createAttemptReview } from "./admin-attempt-review.js";

initLayout();

const $ = (id) => document.getElementById(id);
const SCORE_POLICY = { best: "最佳成绩", last: "最后一次", first: "首次成绩" };
const ATTEMPT_STATUS = { submitted: "已交卷", ongoing: "作答中", expired: "已过期" };
const SUBMIT_KIND = { manual: "手动交卷", auto_timeout: "超时收卷", auto_close: "系统收卷" };
const state = { courseId: "", sectionId: "", lessonId: "", page: 1, size: 100, rows: [], tree: [], courses: [], total: 0, detail: null, detailBlockId: null, detailPage: 1, detailPageSize: 50, histories: new Map(), serverNow: null };
const attemptReview = createAttemptReview({
  mask: $("attemptMask"), title: $("attemptTitle"), body: $("attemptBody"), closeButton: $("attemptClose"),
});

function formatDuration(seconds) {
  if (seconds == null) return "—";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function studentStatus(student) {
  const labels = [];
  if (!student.counted) labels.push("未交卷");
  if (student.ongoing) labels.push("作答中");
  if (student.has_judge_failed) labels.push("判题异常");
  return labels.join(" / ") || "已交卷";
}

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
  $("detailFoot").innerHTML = `<span class="muted">显示 ${start}–${end} / ${total} 位学员</span><span class="spacer"></span><button class="btn" type="button" data-detail-prev ${state.detailPage === 1 ? "disabled" : ""}>上一页</button><button class="btn" type="button" data-detail-next ${state.detailPage >= pages ? "disabled" : ""}>下一页</button>`;
  $("detailFoot").querySelector("[data-detail-prev]")?.addEventListener("click", () => {
    state.detailPage -= 1;
    renderStudents(visibleStudents());
  });
  $("detailFoot").querySelector("[data-detail-next]")?.addEventListener("click", () => {
    state.detailPage += 1;
    renderStudents(visibleStudents());
  });
}

function exportDetailCsv() {
  const detail = state.detail;
  if (!detail) {
    toast("请先打开一份作业成绩后再导出。", "error");
    return;
  }
  const rows = [
    ["课程", detail.course.title],
    ["章节", detail.section.title],
    ["课时", detail.lesson.title],
    ["作业", detail.homework.title],
    ["试卷", `${detail.paper.paper_id_no || ""} · ${detail.paper.title}`],
    [],
    ["学员", "作答次数", "已交次数", "状态", "计分成绩", "用时", "交卷方式", "开始时间", "交卷时间"],
    ...(detail.students || []).map((student) => {
      const counted = student.counted;
      return [
        student.user.username,
        student.attempt_count,
        student.submitted_count,
        studentStatus(student),
        counted?.total_score ?? "",
        counted ? formatDuration(counted.duration_seconds) : "",
        counted ? (SUBMIT_KIND[counted.submit_kind] || "") : "",
        counted ? fmtTime(counted.started_at) : "",
        counted ? fmtTime(counted.submitted_at) : "",
      ];
    }),
  ];
  const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const safeTitle = String(detail.homework.title || "课时作业成绩").replace(/[\\/:*?"<>|]/g, "_");
  link.href = url;
  link.download = `${safeTitle}-成绩.csv`;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  toast(`已导出 ${detail.students?.length || 0} 位学员的成绩。`);
}

function isClosed(row) {
  return row.homework?.status === "closed";
}

function deadlinePresentation(homework) {
  if (!homework?.due_at) {
    return { label: "长期有效", detail: "未设置作业截止时间", className: "due-open" };
  }
  if (homework.status === "closed") {
    return { label: "已截止", detail: `截止于 ${fmtTime(homework.due_at)}`, className: "due-closed" };
  }
  return { label: "进行中", detail: `截止于 ${fmtTime(homework.due_at)}`, className: "due-open" };
}

function filteredRows() {
  const keyword = $("keywordInput").value.trim().toLocaleLowerCase();
  const status = $("statusSelect").value;
  return state.rows.filter((row) => {
    const matchesSection = !state.sectionId || row.section.id === Number(state.sectionId);
    const matchesLesson = !state.lessonId || row.lesson.id === Number(state.lessonId);
    const matchesStatus = !status || (status === "closed" ? isClosed(row) : !isClosed(row));
    const haystack = `${row.homework.title} ${row.lesson.title} ${row.paper.title} ${row.paper.paper_id_no || ""}`.toLocaleLowerCase();
    return matchesSection && matchesLesson && matchesStatus && (!keyword || haystack.includes(keyword));
  });
}

function renderCourseSelect() {
  const options = state.courses.map((course) => `<option value="${course.id}">${escapeHtml(course.title)}</option>`);
  $("courseSelect").innerHTML = '<option value="">全部课包</option>' + options.join("");
  $("courseSelect").value = state.courseId;
}

function renderTree() {
  const courses = state.courseId ? state.tree.filter((course) => course.id === Number(state.courseId)) : state.tree;
  $("courseTree").innerHTML = courses.flatMap((course) => course.sections.map((section) => `
    <li class="tree-section${state.sectionId === String(section.id) && !state.lessonId ? " is-active" : ""}">
      <button type="button" data-section="${section.id}"><span>${escapeHtml(section.title)}</span><small>${section.lessons.reduce((sum, lesson) => sum + lesson.homework_count, 0)} 份作业</small></button>
      <ul class="tree-lessons">${section.lessons.map((lesson) => `
        <li><button class="tree-lesson${state.lessonId === String(lesson.id) ? " is-active" : ""}" type="button" data-lesson="${lesson.id}" data-section="${section.id}">
          ${escapeHtml(lesson.title)}<span class="homework-count">${lesson.homework_count}</span>
        </button></li>`).join("")}</ul>
    </li>`)).join("") || '<li><div class="empty">没有可查看的课时作业</div></li>';
  document.querySelectorAll("[data-section]").forEach((button) => button.addEventListener("click", () => {
    state.sectionId = button.dataset.section;
    state.lessonId = button.dataset.lesson || "";
    renderAll();
  }));
}

function renderStats(rows) {
  const participants = rows.reduce((sum, row) => sum + row.participants, 0);
  const submitted = rows.reduce((sum, row) => sum + row.submitted_participants, 0);
  const attempts = rows.reduce((sum, row) => sum + row.attempts, 0);
  $("overviewStats").innerHTML = `
    <div class="stat"><b>${rows.length}</b><span>课时作业</span></div>
    <div class="stat"><b>${participants}</b><span>参与人数（当前范围）</span></div>
    <div class="stat"><b>${submitted}</b><span>已交人数（当前范围）</span></div>
    <div class="stat"><b>${attempts}</b><span>作答人次（当前范围）</span></div>`;
}

function renderOverview() {
  const rows = filteredRows();
  renderStats(rows);
  const selected = state.lessonId ? rows[0]?.lesson : state.sectionId ? rows[0]?.section : null;
  $("activePath").textContent = selected
    ? `${rows[0]?.course.title || ""} / ${state.sectionId ? rows[0]?.section.title || "" : ""}${state.lessonId ? ` / ${selected.title}` : ""}`
    : "全部课包 / 全部章节";
  $("overviewRows").innerHTML = rows.map((row) => {
    const deadline = deadlinePresentation(row.homework);
    const score = row.score;
    return `<tr>
      <td><div class="homework-name"><b>${escapeHtml(row.homework.title)}</b><small>${escapeHtml(row.paper.paper_id_no || "")} · ${escapeHtml(row.paper.title)}</small></div></td>
      <td class="path-cell">${escapeHtml(row.section.title)}<br>${escapeHtml(row.lesson.title)}</td>
      <td><div class="deadline-cell"><strong class="${deadline.className}">${deadline.label}</strong><small>${deadline.detail}</small></div></td>
      <td>${row.participants} / ${row.submitted_participants}</td><td>${row.attempts}</td>
      <td>${score?.avg ?? "—"}</td><td>${score?.pass_rate == null ? "—" : `${score.pass_rate}%`}</td>
      <td><button class="btn-text link" type="button" data-open="${row.source_id}">查看成绩</button></td>
    </tr>`;
  }).join("") || '<tr><td colspan="8"><div class="empty">当前筛选范围内没有课时作业</div></td></tr>';
  $("overviewFoot").innerHTML = `<span class="muted">接口返回 ${state.total} 份可查看作业；当前显示 ${rows.length} 份 · 状态由服务端判定${state.serverNow ? `（${fmtTime(state.serverNow)}）` : ""}</span>`;
  document.querySelectorAll("[data-open]").forEach((button) => button.addEventListener("click", () => openDetail(Number(button.dataset.open)).catch(onError)));
}

function renderAll() { renderTree(); renderOverview(); }

async function loadOverview() {
  const params = new URLSearchParams({ page: String(state.page), size: String(state.size) });
  if (state.courseId) params.set("course_id", state.courseId);
  const payload = await adminRequest(`/lesson-homework-results?${params}`);
  state.rows = payload.items || [];
  state.tree = payload.tree || [];
  if (!state.courseId) state.courses = state.tree;
  state.total = payload.total || 0;
  state.serverNow = payload.server_now || null;
  renderCourseSelect();
  renderAll();
}

function historyTable(attempts, counted) {
  return `<div class="table-wrap history-wrap"><table class="history-table"><thead><tr><th>次数</th><th>状态</th><th>成绩</th><th>用时</th><th>开始</th><th>提交</th><th>操作</th></tr></thead><tbody>${attempts.map((attempt) => `<tr><td>第 ${attempt.attempt_no} 次${counted?.attempt_id === attempt.attempt_id ? ' <span class="tag">计分</span>' : ""}</td><td>${ATTEMPT_STATUS[attempt.status] || attempt.status}</td><td>${attempt.total_score ?? "—"}</td><td>${formatDuration(attempt.duration_seconds)}</td><td>${fmtTime(attempt.started_at)}</td><td>${fmtTime(attempt.submitted_at)}</td><td>${attempt.status === "submitted" ? `<button class="btn-text link" type="button" data-review="${attempt.attempt_id}">答题详情</button>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
}

async function toggleStudentHistory(button) {
  const host = $(`history-${button.dataset.toggle}`);
  const expanded = button.getAttribute("aria-expanded") === "true";
  if (expanded) {
    host.hidden = true;
    button.textContent = "展开";
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", `展开 ${button.dataset.student} 的作答历史`);
    return;
  }
  const userId = Number(button.dataset.userId);
  let history = state.histories.get(userId);
  if (!history) {
    button.disabled = true;
    button.textContent = "加载中";
    try {
      const payload = await adminRequest(`/lesson-homework/${state.detailBlockId}/students/${userId}/attempts`);
      history = payload.student;
      state.histories.set(userId, history);
    } finally {
      button.disabled = false;
    }
  }
  host.querySelector("td").innerHTML = historyTable(history.attempts, history.counted);
  host.hidden = false;
  button.textContent = "收起";
  button.setAttribute("aria-expanded", "true");
  button.setAttribute("aria-label", `收起 ${button.dataset.student} 的作答历史`);
  host.querySelectorAll("[data-review]").forEach((review) => review.addEventListener("click", () => attemptReview.open(Number(review.dataset.review), review).catch(onError)));
}

function renderStudents(students) {
  $("attemptRows").innerHTML = students.map((student, index) => {
    const counted = student.counted;
    const repeated = student.attempt_count > 1;
    const stateTags = `${student.has_judge_failed ? ' <span class="tag danger">判题异常</span>' : ""}${student.ongoing ? ' <span class="tag gray">作答中</span>' : ""}`;
    const rowId = `${state.detailPage}-${index}`;
    return `<tr class="student-row">
      <td data-label="学员">${repeated ? `<button class="expander" type="button" data-toggle="${rowId}" data-user-id="${student.user.id}" data-student="${escapeHtml(student.user.username)}" aria-controls="history-${rowId}" aria-expanded="false" aria-label="展开 ${escapeHtml(student.user.username)} 的作答历史">展开</button>` : ""}<span class="student-name">${escapeHtml(student.user.username)}</span></td>
      <td data-label="作答次数">${student.attempt_count}</td><td data-label="状态">${counted ? "" : '<span class="tag gray">未交卷</span>'}${stateTags}</td>
      <td data-label="计分成绩">${counted ? `<b>${counted.total_score}</b>` : "—"}</td><td data-label="用时">${counted ? formatDuration(counted.duration_seconds) : "—"}</td>
      <td data-label="交卷方式">${counted ? (SUBMIT_KIND[counted.submit_kind] || "—") : "—"}</td><td data-label="开始时间">${counted ? fmtTime(counted.started_at) : "—"}</td>
      <td data-label="交卷时间">${counted ? fmtTime(counted.submitted_at) : "—"}</td><td data-label="操作">${counted ? `<button class="btn-text link" type="button" data-review="${counted.attempt_id}">答卷回看</button>` : ""}</td>
    </tr>${repeated ? `<tr class="history-host" id="history-${rowId}" hidden><td colspan="9"></td></tr>` : ""}`;
  }).join("") || '<tr><td colspan="9"><div class="empty">还没有学员开始这份作业</div></td></tr>';
  document.querySelectorAll("[data-toggle]").forEach((button) => button.addEventListener("click", () => toggleStudentHistory(button).catch(onError)));
  document.querySelectorAll("[data-review]").forEach((button) => button.addEventListener("click", () => attemptReview.open(Number(button.dataset.review), button).catch(onError)));
  renderDetailPager();
}

async function openDetail(blockId) {
  const payload = await adminRequest(`/lesson-homework/${blockId}/results`);
  state.detail = payload;
  state.detailBlockId = blockId;
  state.histories = new Map();
  state.detailPage = 1;
  $("overviewView").hidden = true; $("detailView").hidden = false;
  $("detailPath").textContent = `${payload.course.title} / ${payload.section.title} / ${payload.lesson.title}`;
  $("detailTitle").textContent = payload.homework.title;
  const deadline = deadlinePresentation(payload.homework);
  $("detailTags").innerHTML = `<span class="tag">课时作业</span><span class="tag">${escapeHtml(payload.paper.paper_id_no || "")} · ${escapeHtml(payload.paper.title)}</span><span class="tag ${deadline.className}">${deadline.label}</span><span class="tag gray">${deadline.detail}</span><span class="tag gray">满分 ${payload.full_score}${payload.pass_score == null ? "" : ` / 及格 ${payload.pass_score}`}</span>`;
  const summary = payload.summary;
  $("detailStats").innerHTML = `<div class="stat"><b>${summary.participants}</b><span>参与人数</span></div><div class="stat"><b>${summary.attempts}</b><span>作答人次</span></div><div class="stat"><b>${summary.submitted_participants}</b><span>已交人数</span></div><div class="stat"><b>${summary.avg ?? "—"}</b><span>平均分（按人）</span></div><div class="stat"><b>${summary.min == null ? "—" : `${summary.min} ~ ${summary.max}`}</b><span>分数区间</span></div><div class="stat"><b>${summary.pass_rate == null ? "—" : `${summary.pass_rate}%`}</b><span>及格率（按人）</span></div>`;
  document.querySelector(".homework-insight strong").textContent = `统计按每位学员的${SCORE_POLICY[payload.homework.score_policy] || payload.homework.score_policy}已交成绩计算`;
  renderStudents(visibleStudents());
}

function onError(error) { toast(error?.message || "请求失败，请稍后再试。", "error"); }

$("courseSelect").addEventListener("change", (event) => {
  state.courseId = event.target.value; state.sectionId = ""; state.lessonId = ""; loadOverview().catch(onError);
});
$("searchBtn").addEventListener("click", renderOverview);
$("backBtn").addEventListener("click", () => { $("detailView").hidden = true; $("overviewView").hidden = false; });
$("exportBtn").addEventListener("click", exportDetailCsv);
loadOverview().catch(onError);
