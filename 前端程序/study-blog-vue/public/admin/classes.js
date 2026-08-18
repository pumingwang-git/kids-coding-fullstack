// 班级列表与详情：可见范围由后端返回，关系变更只调用对应的单条接口。
import { initLayout } from "./admin-layout.js";
import { adminDownload, adminRequest } from "./admin-api.js";
import { confirmDialog, escapeHtml, fmtTime, promptDialog, toast } from "./admin-ui.js";
import { mountStudentPicker } from "./student-picker.js";

initLayout();

const $ = (id) => document.getElementById(id);
let classes = [];
let selectedId = Number(new URLSearchParams(location.search).get("id")) || null;
let members = [];
let teachers = [];
let roleOptions = [];
let memberHistoryVisible = false;
let teacherHistoryVisible = false;
let memberBulkPicker = null;

function statusClass(status) {
  return `class-status class-status-${String(status || "unknown").replace(/[^a-z0-9_-]/gi, "")}`;
}

function renderList() {
  const keyword = $("classSearch").value.trim().toLowerCase();
  const visible = keyword
    ? classes.filter((row) => row.name.toLowerCase().includes(keyword))
    : classes;
  $("classListMeta").textContent = `${visible.length} / ${classes.length} 个班级`;
  $("classEmpty").hidden = visible.length > 0;
  $("classRows").innerHTML = visible
    .map(
      (row) => `
    <tr class="class-row" data-id="${row.id}">
      <td><a class="class-name-link" href="classes.html?id=${row.id}">${escapeHtml(row.name)}</a></td>
      <td class="class-code">${escapeHtml(row.course_id)}</td>
      <td><span class="${statusClass(row.status)}">${escapeHtml(row.status_label)}</span></td>
      <td>${escapeHtml(fmtTime(row.start_at) || "未设置")}</td>
      <td>${escapeHtml(fmtTime(row.end_at) || "未设置")}</td>
      <td><a class="btn-text" href="classes.html?id=${row.id}">查看详情</a></td>
    </tr>`,
    )
    .join("");
}

function renderDetail(row) {
  $("classDetailTitle").textContent = row.name;
  $("classDetailFields").innerHTML = [
    ["班级 ID", row.id],
    ["课包 ID", row.course_id],
    ["状态", row.status_label],
    ["开始时间", fmtTime(row.start_at) || "未设置"],
    ["结束时间", fmtTime(row.end_at) || "未设置"],
    ["更新时间", fmtTime(row.updated_at) || "未设置"],
  ]
    .map(
      ([label, value]) =>
        `<div class="class-detail-field"><dt>${label}</dt><dd>${escapeHtml(String(value))}</dd></div>`,
    )
    .join("");
  $("classDetail").hidden = false;
}

function relationTime(value) {
  return escapeHtml(fmtTime(value) || "未记录");
}

function relationName(row, type) {
  if (type === "member") return row.student_name || `#${row.student_id}`;
  return row.teacher_name || `#${row.admin_user_id}`;
}

function renderMembers() {
  const active = members.filter((row) => row.status === "active");
  const history = members.filter((row) => row.status !== "active");
  const shown = memberHistoryVisible ? members : active;
  $("classMembersMeta").textContent =
    `${active.length} 条当前关系${history.length ? ` · ${history.length} 条历史` : ""}`;
  $("classMemberEmpty").hidden = shown.length > 0;
  $("toggleMemberHistory").hidden = history.length === 0;
  $("toggleMemberHistory").textContent = memberHistoryVisible
    ? "收起历史"
    : `显示历史（${history.length}）`;
  $("classMemberRows").innerHTML = shown
    .map(
      (row) => `
    <tr class="${row.status === "active" ? "" : "class-history-row"}">
      <td><strong class="class-relation-primary">${escapeHtml(relationName(row, "member"))}</strong><small class="class-relation-secondary">#${escapeHtml(row.student_id)}</small></td>
      <td><span class="tag ${row.status === "active" ? "" : "gray"}">${escapeHtml(row.status_label)}</span></td>
      <td>${row.enrollment_status_label ? `<span class="tag ${row.enrollment_status === "active" ? "" : "gray"}">${escapeHtml(row.enrollment_status_label)}</span>` : "-"}</td>
      <td>${relationTime(row.joined_at)}</td><td>${relationTime(row.left_at)}</td>
      <td class="class-relation-actions">${row.status === "active" ? `<button class="btn-text" type="button" data-member-withdraw="${row.id}">退班</button><button class="btn-text" type="button" data-member-transfer="${row.id}">转班</button>` : ""}</td>
    </tr>`,
    )
    .join("");
}

function renderTeacherRoleOptions(roleOptions = []) {
  const select = $("teacherRole");
  const options = new Map();
  roleOptions.forEach((option) => {
    if (option?.value && option?.label) options.set(option.value, option.label);
  });
  select.innerHTML = [...options]
    .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
    .join("");
  select.disabled = options.size === 0;
  if (!options.size) select.innerHTML = '<option value="">暂无可选班内角色</option>';
}

function renderTeachers() {
  const active = teachers.filter((row) => row.ended_at == null);
  const history = teachers.filter((row) => row.ended_at != null);
  const shown = teacherHistoryVisible ? teachers : active;
  $("classTeachersMeta").textContent =
    `${active.length} 条当前关系${history.length ? ` · ${history.length} 条历史` : ""}`;
  $("classTeacherEmpty").hidden = shown.length > 0;
  $("toggleTeacherHistory").hidden = history.length === 0;
  $("toggleTeacherHistory").textContent = teacherHistoryVisible
    ? "收起历史"
    : `显示历史（${history.length}）`;
  $("classTeacherRows").innerHTML = shown
    .map(
      (row) => `
    <tr class="${row.ended_at == null ? "" : "class-history-row"}">
      <td><strong class="class-relation-primary">${escapeHtml(relationName(row, "teacher"))}</strong><small class="class-relation-secondary">#${escapeHtml(row.admin_user_id)}</small></td><td>${escapeHtml(row.role_in_class_label)}</td>
      <td>${relationTime(row.assigned_at)}</td><td>${relationTime(row.ended_at)}</td>
      <td class="class-relation-actions">${row.ended_at == null ? `<button class="btn-text" type="button" data-teacher-unassign="${row.id}">结束</button>` : ""}</td>
    </tr>`,
    )
    .join("");
}

function relationError(error) {
  return error?.message || "请求失败，请稍后再试。";
}

async function loadRelations(classId) {
  $("classRelations").hidden = false;
  $("classMemberRows").innerHTML = '<tr><td class="class-loading" colspan="6">加载中</td></tr>';
  $("classTeacherRows").innerHTML = '<tr><td class="class-loading" colspan="5">加载中</td></tr>';
  try {
    const [memberPayload, teacherPayload] = await Promise.all([
      adminRequest(`/classes/${classId}/members`),
      adminRequest(`/classes/${classId}/teachers`),
    ]);
    members = memberPayload?.items || [];
    teachers = teacherPayload?.items || [];
    renderMembers();
    renderTeacherRoleOptions(roleOptions);
    renderTeachers();
  } catch (error) {
    members = [];
    teachers = [];
    memberHistoryVisible = false;
    teacherHistoryVisible = false;
    renderMembers();
    renderTeachers();
    renderTeacherRoleOptions([]);
    const message = escapeHtml(relationError(error));
    $("classMemberRows").innerHTML =
      `<tr><td class="class-loading" colspan="6">${message}</td></tr>`;
    $("classTeacherRows").innerHTML =
      `<tr><td class="class-loading" colspan="5">${message}</td></tr>`;
    $("classMemberEmpty").hidden = true;
    $("classTeacherEmpty").hidden = true;
    $("classMembersMeta").textContent = "加载失败";
    $("classTeachersMeta").textContent = "加载失败";
  }
}

async function refreshRelations() {
  if (selectedId) await loadRelations(selectedId);
}

async function openDetail(id, { updateUrl = true } = {}) {
  const row = classes.find((item) => item.id === id);
  if (!row) return;
  selectedId = id;
  memberHistoryVisible = false;
  teacherHistoryVisible = false;
  if (updateUrl) history.pushState({}, "", `classes.html?id=${id}`);
  $("classDetailError").hidden = true;
  renderDetail(row);
  await loadRelations(id);
  try {
    const fresh = await adminRequest(`/classes/${id}`);
    const index = classes.findIndex((item) => item.id === id);
    if (index >= 0) classes[index] = fresh;
    renderList();
    renderDetail(fresh);
  } catch (error) {
    $("classDetailError").textContent = relationError(error);
    $("classDetailError").hidden = false;
  }
}

function closeDetail() {
  selectedId = null;
  members = [];
  teachers = [];
  history.pushState({}, "", "classes.html");
  $("classDetail").hidden = true;
}

async function loadClasses() {
  $("classError").hidden = true;
  $("classRows").innerHTML = '<tr><td class="class-loading" colspan="6">加载中</td></tr>';
  try {
    const payload = await adminRequest("/classes");
    classes = payload.items || [];
    roleOptions = Array.isArray(payload.role_options) ? payload.role_options : [];
    renderList();
    if (selectedId && classes.some((row) => row.id === selectedId))
      await openDetail(selectedId, { updateUrl: false });
    else if (selectedId) closeDetail();
  } catch (error) {
    $("classRows").innerHTML = "";
    $("classErrorText").textContent = relationError(error);
    $("classError").hidden = false;
  }
}

async function submitRelation(path, payload, successText) {
  try {
    const result = await adminRequest(path, {
      method: "POST",
      body: JSON.stringify(payload || {}),
    });
    toast(successText);
    await refreshRelations();
    return result;
  } catch (error) {
    toast(relationError(error), "error");
    return null;
  }
}

function updateMemberBulkSelection(selected) {
  $("memberBulkImportSelection").textContent = `已选择 ${selected.length} 名学员`;
  $("submitMemberBulkImport").disabled = selected.length === 0;
}

function closeMemberBulkImport() {
  const mask = $("memberBulkImportMask");
  mask.classList.remove("show");
  mask.hidden = true;
  mask.inert = true;
}

function openMemberBulkImport() {
  const mask = $("memberBulkImportMask");
  $("memberBulkImportProgress").hidden = true;
  $("memberBulkImportProgress").innerHTML = "";
  $("memberBulkImportResult").hidden = true;
  $("memberBulkImportResult").innerHTML = "";
  if (!memberBulkPicker) {
    memberBulkPicker = mountStudentPicker($("memberBulkStudentPicker"), {
      onChange: updateMemberBulkSelection,
    });
  } else {
    memberBulkPicker.clear();
  }
  updateMemberBulkSelection(memberBulkPicker.selected());
  mask.hidden = false;
  mask.inert = false;
  requestAnimationFrame(() => mask.classList.add("show"));
  $("closeMemberBulkImport").focus();
}

function renderMemberBulkResult(result) {
  const succeeded = result?.succeeded || [];
  const failed = result?.failed || [];
  const failedList = failed
    .map((row) => `${row.student_id}: ${row.reason_code}`)
    .join("\n");
  $("memberBulkImportResult").innerHTML = `<div class="import-result">
    <strong>导入完成</strong>
    <div class="import-result-stats">
      <span class="stat ok">成功 ${succeeded.length}</span>
      <span class="stat err">失败 ${failed.length}</span>
    </div>
    ${failed.length ? `<p class="field-error">失败学员 ID 与原因码：</p><pre class="import-failed-list">${escapeHtml(failedList)}</pre>` : ""}
  </div>`;
  $("memberBulkImportResult").hidden = false;
}

async function submitMemberBulkImport() {
  const selected = memberBulkPicker?.selected() || [];
  if (!selected.length || !selectedId) return;
  const submit = $("submitMemberBulkImport");
  submit.disabled = true;
  $("memberBulkImportResult").hidden = true;
  $("memberBulkImportProgress").hidden = false;
  $("memberBulkImportProgress").innerHTML = `<strong>正在导入成员</strong><div class="import-progress"><progress value="0" max="${selected.length}"></progress><span>0 / ${selected.length}</span></div>`;
  try {
    const result = await adminRequest(`/classes/${selectedId}/members/bulk`, {
      method: "POST",
      body: JSON.stringify({ student_ids: selected.map((student) => student.id) }),
    });
    $("memberBulkImportProgress").innerHTML = `<strong>成员导入完成</strong><div class="import-progress"><progress value="${selected.length}" max="${selected.length}"></progress><span>${selected.length} / ${selected.length}</span></div>`;
    renderMemberBulkResult(result);
    await refreshRelations();
    memberBulkPicker.clear();
    toast(`批量导入完成：成功 ${(result?.succeeded || []).length} 名`);
  } catch (error) {
    $("memberBulkImportProgress").hidden = true;
    $("memberBulkImportResult").innerHTML = `<p class="field-error">${escapeHtml(relationError(error))}</p>`;
    $("memberBulkImportResult").hidden = false;
  } finally {
    updateMemberBulkSelection(memberBulkPicker?.selected() || []);
  }
}

$("classRows").addEventListener("click", (event) => {
  const link = event.target.closest("a.class-name-link");
  if (!link) return;
  event.preventDefault();
  openDetail(Number(new URL(link.href).searchParams.get("id")));
});
$("classSearch").addEventListener("input", renderList);
$("refreshClasses").addEventListener("click", loadClasses);
$("exportClassRelationships").addEventListener("click", async () => {
  try {
    await adminDownload("/classes/export", "class-relationships.csv");
    toast("关系导出已开始");
  } catch (error) {
    toast(relationError(error), "error");
  }
});
$("retryClasses").addEventListener("click", loadClasses);
$("closeDetail").addEventListener("click", closeDetail);
$("openMemberBulkImport").addEventListener("click", openMemberBulkImport);
$("syncClassEnrollments").addEventListener("click", async () => {
  if (!selectedId) return;
  try {
    const result = await adminRequest(`/classes/${selectedId}/enrollments/sync`, { method: "POST" });
    toast(`已同步：新增 ${result.granted}，跳过 ${result.skipped}`);
    await refreshRelations();
  } catch (error) {
    toast(relationError(error), "error");
  }
});
$("closeMemberBulkImport").addEventListener("click", closeMemberBulkImport);
$("cancelMemberBulkImport").addEventListener("click", closeMemberBulkImport);
$("memberBulkImportMask").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeMemberBulkImport();
});
$("submitMemberBulkImport").addEventListener("click", submitMemberBulkImport);
$("toggleMemberHistory").addEventListener("click", () => {
  memberHistoryVisible = !memberHistoryVisible;
  renderMembers();
});
$("toggleTeacherHistory").addEventListener("click", () => {
  teacherHistoryVisible = !teacherHistoryVisible;
  renderTeachers();
});

$("enrollMemberForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const studentId = Number($("memberStudentId").value);
  if (!Number.isInteger(studentId) || studentId < 1) return;
  const result = await submitRelation(
    `/classes/${selectedId}/members`,
    { student_id: studentId },
    "成员关系已建立",
  );
  if (result) event.target.reset();
});
$("assignTeacherForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const adminUserId = Number($("teacherAdminId").value);
  const role = $("teacherRole").value;
  if (!Number.isInteger(adminUserId) || adminUserId < 1 || !role) return;
  const result = await submitRelation(
    `/classes/${selectedId}/teachers`,
    { admin_user_id: adminUserId, role_in_class: role },
    "带班关系已建立",
  );
  if (result) event.target.reset();
});

$("classMemberRows").addEventListener("click", async (event) => {
  const withdraw = event.target.closest("[data-member-withdraw]");
  if (withdraw) {
    const ok = await confirmDialog({
      title: "退班",
      message: "确认结束这条成员关系吗？",
      confirmText: "退班",
      danger: true,
    });
    if (ok)
      await submitRelation(
        `/classes/${selectedId}/members/${withdraw.dataset.memberWithdraw}/withdraw`,
        null,
        "成员关系已结束",
      );
    return;
  }
  const transfer = event.target.closest("[data-member-transfer]");
  if (!transfer) return;
  const options = classes.filter((row) => row.id !== selectedId && row.status !== "archived");
  if (!options.length) return toast("暂无可转入的班级。", "error");
  const target = await promptDialog({
    title: "转班",
    label: "转入班级",
    selectOptions: options.map((row) => ({ value: row.id, label: `${row.id} · ${row.name}` })),
    confirmText: "转班",
  });
  const targetId = Number(target);
  if (!target || !options.some((row) => row.id === targetId)) return;
  await submitRelation(
    `/classes/${selectedId}/members/${transfer.dataset.memberTransfer}/transfer`,
    { to_class_id: targetId },
    "成员已转班",
  );
});
$("classTeacherRows").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-teacher-unassign]");
  if (!button) return;
  const ok = await confirmDialog({
    title: "结束带班",
    message: "确认结束这条带班关系吗？",
    confirmText: "结束",
    danger: true,
  });
  if (ok)
    await submitRelation(
      `/classes/${selectedId}/teachers/${button.dataset.teacherUnassign}/unassign`,
      null,
      "带班关系已结束",
    );
});

window.addEventListener("popstate", () => {
  const id = Number(new URLSearchParams(location.search).get("id")) || null;
  if (id) openDetail(id, { updateUrl: false });
  else closeDetail();
});
loadClasses().catch((error) => toast(relationError(error), "error"));
