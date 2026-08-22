import { initLayout } from "./admin-layout.js";
import { adminRequest } from "./admin-api.js";
import { confirmDialog, escapeHtml, fmtTime, toast } from "./admin-ui.js";
import { mountStudentPicker } from "./student-picker.js";

initLayout();
const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 20;
let state = { page: 1, status: "", student: null, result: null };

function isoFromLocal(value) { return value ? new Date(value).toISOString() : null; }
function windowText(row) { return `${fmtTime(row.opened_at) || "立即"} - ${fmtTime(row.expires_at) || "长期"}`; }
function action(row) {
  const actions = new Set(row.allowed_actions || []);
  if (actions.has("disable")) return `<button class="btn-text link" type="button" data-enrollment-id="${row.id}" data-enrollment-status="disabled">停用</button>`;
  if (actions.has("restore")) return `<button class="btn-text link" type="button" data-enrollment-id="${row.id}" data-enrollment-status="active">恢复</button>`;
  return "-";
}

function render() {
  const result = state.result || { items: [], total: 0, page: state.page, page_size: PAGE_SIZE };
  const rows = result.items || [];
  $("enrollmentRows").innerHTML = rows.map((row) => `
    <tr><td>#${escapeHtml(row.student_id)} · ${escapeHtml(row.student_username || "")}</td>
    <td>${escapeHtml(row.course_title || `#${row.course_id}`)}</td><td>${escapeHtml(windowText(row))}</td>
    <td><span class="tag">${escapeHtml(row.status_label)}</span></td><td>${action(row)}</td></tr>`).join("");
  $("enrollmentEmpty").hidden = rows.length > 0;
  $("enrollmentMeta").textContent = state.student
    ? `#${state.student.id} · ${state.student.username} · 共 ${result.total} 条`
    : `全部记录 · ${result.total} 条`;
  const pages = Math.max(1, Math.ceil(result.total / result.page_size));
  $("enrollmentPager").hidden = result.total <= result.page_size;
  $("enrollmentPageMeta").textContent = `第 ${result.page} 页，共 ${pages} 页`;
  $("previousEnrollmentPage").disabled = result.page <= 1;
  $("nextEnrollmentPage").disabled = result.page >= pages;
}

async function loadEnrollments() {
  $("enrollmentError").hidden = true;
  $("enrollmentRows").innerHTML = '<tr><td class="student-loading" colspan="5">加载中</td></tr>';
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) });
    if (state.status) params.set("status", state.status);
    if (state.student) params.set("student_id", String(state.student.id));
    state.result = await adminRequest(`/enrollments?${params}`);
    if (!state.result.items.length && state.page > 1) { state.page -= 1; return loadEnrollments(); }
    render();
  } catch (error) {
    $("enrollmentRows").innerHTML = ""; $("enrollmentEmpty").hidden = true;
    $("enrollmentErrorText").textContent = error.message; $("enrollmentError").hidden = false;
    $("enrollmentPager").hidden = true; $("enrollmentMeta").textContent = "加载失败";
  }
}

async function loadCourses() {
  const result = await adminRequest("/courses?status=published&page=1&page_size=100");
  $("enrollmentCourse").innerHTML = '<option value="">请选择课程</option>' + (result.items || []).map((course) => `<option value="${course.id}">${escapeHtml(course.title)}</option>`).join("");
}

mountStudentPicker($("enrollmentStudentPicker"), { multiple: false, onChange: (students) => { state.student = students[0] || null; state.page = 1; loadEnrollments(); } });
$("enrollmentFilterForm").addEventListener("submit", (event) => { event.preventDefault(); state.status = $("enrollmentStatus").value; state.page = 1; loadEnrollments(); });
$("refreshEnrollments").addEventListener("click", loadEnrollments);
$("retryEnrollments").addEventListener("click", loadEnrollments);
$("previousEnrollmentPage").addEventListener("click", () => { state.page -= 1; loadEnrollments(); });
$("nextEnrollmentPage").addEventListener("click", () => { state.page += 1; loadEnrollments(); });

$("enrollmentGrantForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.student) return toast("请先选择学员。", "error");
  const courseId = Number($("enrollmentCourse").value);
  if (!courseId) return toast("请选择课程。", "error");
  const body = { student_id: state.student.id, course_id: courseId, opened_at: isoFromLocal($("enrollmentOpenedAt").value), expires_at: isoFromLocal($("enrollmentExpiresAt").value) };
  Object.keys(body).forEach((key) => { if (body[key] === null) delete body[key]; });
  try { await adminRequest("/enrollments", { method: "POST", body: JSON.stringify(body) }); toast("开通操作已完成。", "success"); $("enrollmentOpenedAt").value = ""; $("enrollmentExpiresAt").value = ""; state.page = 1; await loadEnrollments(); }
  catch (error) { toast(error.message, "error"); }
});

$("enrollmentRows").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-enrollment-status]"); if (!button) return;
  const nextStatus = button.dataset.enrollmentStatus;
  if (nextStatus === "disabled" && !(await confirmDialog({ title: "停用课程开通？", message: "停用后学员将不能继续访问该课程。", confirmText: "停用", danger: true }))) return;
  try { await adminRequest(`/enrollments/${button.dataset.enrollmentId}/status`, { method: "PUT", body: JSON.stringify({ status: nextStatus }) }); toast(nextStatus === "disabled" ? "停用操作已完成。" : "恢复操作已完成。", "success"); await loadEnrollments(); }
  catch (error) { toast(error.message, "error"); }
});

loadCourses().catch((error) => { $("enrollmentCourse").innerHTML = `<option value="">${escapeHtml(error.message)}</option>`; });
loadEnrollments();
