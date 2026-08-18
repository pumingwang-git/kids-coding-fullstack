// 学员列表只显示后端按 visible_student_ids() 收窄后的数据。
import { initLayout } from "./admin-layout.js";
import { adminRequest } from "./admin-api.js";
import { confirmDialog, escapeHtml, fmtTime, toast } from "./admin-ui.js";
import { fetchStudents, mountStudentPicker, STUDENT_PAGE_SIZE } from "./student-picker.js";

initLayout();

const $ = (id) => document.getElementById(id);
let state = { keyword: "", page: 1, result: null };
let selectedStudent = null;
let enrollmentRows = [];

function isoFromLocal(value) {
  return value ? new Date(value).toISOString() : null;
}

function enrollmentWindow(row) {
  const opened = fmtTime(row.opened_at) || "立即";
  const expires = fmtTime(row.expires_at) || "长期";
  return `${opened} - ${expires}`;
}

function renderEnrollments() {
  const rows = enrollmentRows;
  $("enrollmentRows").innerHTML = rows.map((row) => `
    <tr>
      <td>#${escapeHtml(row.student_id)} · ${escapeHtml(row.student_username || "")}</td>
      <td>${escapeHtml(row.course_title || `#${row.course_id}`)}</td>
      <td>${escapeHtml(enrollmentWindow(row))}</td>
      <td><span class="tag">${escapeHtml(row.status_label)}</span></td>
      <td>${renderEnrollmentAction(row)}</td>
    </tr>`).join("");
  $("enrollmentEmpty").hidden = rows.length > 0;
  $("enrollmentMeta").textContent = selectedStudent
    ? `#${selectedStudent.id} · ${selectedStudent.username} · ${rows.length} 条记录`
    : `全部记录 · ${rows.length} 条`;
}

function renderEnrollmentAction(row) {
  const actions = new Set(row.allowed_actions || []);
  if (actions.has("disable")) {
    return `<button class="btn-text link" type="button" data-enrollment-id="${row.id}" data-enrollment-status="disabled">停用</button>`;
  }
  if (actions.has("restore")) {
    return `<button class="btn-text link" type="button" data-enrollment-id="${row.id}" data-enrollment-status="active">恢复</button>`;
  }
  return "-";
}

async function loadEnrollments() {
  $("enrollmentError").hidden = true;
  try {
    const params = new URLSearchParams({ page: "1", page_size: "100" });
    if (selectedStudent) params.set("student_id", String(selectedStudent.id));
    const result = await adminRequest(`/enrollments?${params}`);
    enrollmentRows = result.items || [];
    renderEnrollments();
  } catch (error) {
    $("enrollmentRows").innerHTML = "";
    $("enrollmentEmpty").hidden = true;
    $("enrollmentErrorText").textContent = error.message;
    $("enrollmentError").hidden = false;
    $("enrollmentMeta").textContent = "加载失败";
  }
}

async function loadCourses() {
  const result = await adminRequest("/courses?status=published&page=1&page_size=100");
  $("enrollmentCourse").innerHTML = '<option value="">请选择课程</option>' + result.items.map((course) =>
    `<option value="${course.id}">${escapeHtml(course.title)}</option>`).join("");
}

function render() {
  const result = state.result || { items: [], total: 0, page: state.page, page_size: STUDENT_PAGE_SIZE };
  const items = result.items || [];
  $("studentRows").innerHTML = items
    .map(
      (student) => `
        <tr>
          <td class="student-id">#${escapeHtml(student.id)}</td>
          <td class="student-name">${escapeHtml(student.username)}</td>
          <td class="cell-clip" title="${escapeHtml(student.email)}">${escapeHtml(student.email)}</td>
          <td><span class="tag">${escapeHtml(student.status_label)}</span></td>
          <td>${escapeHtml(fmtTime(student.created_at) || "未记录")}</td>
        </tr>`,
    )
    .join("");
  $("studentEmpty").hidden = items.length > 0;
  $("studentListMeta").textContent = `共 ${result.total} 名学员`;
  $("studentPager").hidden = result.total <= result.page_size;
  $("studentPageMeta").textContent = `第 ${result.page} 页，共 ${Math.max(1, Math.ceil(result.total / result.page_size))} 页`;
  $("previousStudentPage").disabled = result.page <= 1;
  $("nextStudentPage").disabled = result.page * result.page_size >= result.total;
}

async function loadStudents() {
  $("studentError").hidden = true;
  $("studentEmpty").hidden = true;
  $("studentRows").innerHTML = '<tr><td class="student-loading" colspan="5">加载中</td></tr>';
  try {
    state.result = await fetchStudents({ keyword: state.keyword, page: state.page });
    if (state.result.items.length === 0 && state.page > 1) {
      state.page -= 1;
      state.result = await fetchStudents({ keyword: state.keyword, page: state.page });
    }
    render();
  } catch (error) {
    $("studentRows").innerHTML = "";
    $("studentErrorText").textContent = error.message;
    $("studentError").hidden = false;
    $("studentPager").hidden = true;
    $("studentListMeta").textContent = "加载失败";
  }
}

$("studentSearchForm").addEventListener("submit", (event) => {
  event.preventDefault();
  state.keyword = $("studentSearch").value.trim();
  state.page = 1;
  loadStudents();
});
$("refreshStudents").addEventListener("click", loadStudents);
$("retryStudents").addEventListener("click", loadStudents);
$("previousStudentPage").addEventListener("click", () => {
  state.page -= 1;
  loadStudents();
});
$("nextStudentPage").addEventListener("click", () => {
  state.page += 1;
  loadStudents();
});

mountStudentPicker(document.getElementById("enrollmentStudentPicker"), {
  multiple: false,
  onChange: (students) => {
    selectedStudent = students[0] || null;
    loadEnrollments();
  },
});

$("enrollmentGrantForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedStudent) return toast("请先选择学员。", "error");
  const courseId = Number($("enrollmentCourse").value);
  if (!courseId) return toast("请选择课程。", "error");
  const body = {
    student_id: selectedStudent.id,
    course_id: courseId,
    opened_at: isoFromLocal($("enrollmentOpenedAt").value),
    expires_at: isoFromLocal($("enrollmentExpiresAt").value),
  };
  Object.keys(body).forEach((key) => { if (body[key] === null) delete body[key]; });
  try {
    await adminRequest("/enrollments", { method: "POST", body: JSON.stringify(body) });
    toast("开通操作已完成。", "success");
    $("enrollmentOpenedAt").value = "";
    $("enrollmentExpiresAt").value = "";
    await loadEnrollments();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("enrollmentRows").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-enrollment-status]");
  if (!button) return;
  const nextStatus = button.dataset.enrollmentStatus;
  if (nextStatus === "disabled" && !(await confirmDialog({
    title: "停用课程开通？", message: "停用后学员将不能继续访问该课程。", confirmText: "停用", danger: true,
  }))) return;
  try {
    await adminRequest(`/enrollments/${button.dataset.enrollmentId}/status`, {
      method: "PUT", body: JSON.stringify({ status: nextStatus }),
    });
    toast(nextStatus === "disabled" ? "停用操作已完成。" : "恢复操作已完成。", "success");
    await loadEnrollments();
  } catch (error) {
    toast(error.message, "error");
  }
});

$("retryEnrollments").addEventListener("click", loadEnrollments);

loadStudents();
loadCourses().catch((error) => {
  $("enrollmentCourse").innerHTML = `<option value="">${escapeHtml(error.message)}</option>`;
});
loadEnrollments();
