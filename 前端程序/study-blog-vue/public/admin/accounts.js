// 后台账号角色管理（ADR-001 §2.4：变更 AdminUser.role 仅限 super_admin）。
//
// 两条纪律：
// 1. 隐藏入口不是授权。这里的 can_manage_admin_roles 分支只决定「看不看得见」，
//    真正拦住越权的是后端 PUT /api/admin/admin-users/{id}/role 的 403。
// 2. 角色清单不在前端硬编码，一律取自列表接口的 roles（源头是 permissions.py 的
//    ROLE_LABELS）。前端抄一份角色集合，就是下次加角色时必然漏改的那一处。

import { adminMe, adminRequest } from "./admin-api.js";
import { initLayout } from "./admin-layout.js";
import { closeMask, confirmDialog, escapeHtml, fmtTime, openMask, toast } from "./admin-ui.js";

// 只有启用/停用两态，不做删除（《41、管理端账号管理范围裁决》§2.1）。
const STATUS_LABEL = { active: "启用", disabled: "已停用" };

initLayout();

const $ = (id) => document.getElementById(id);

let accounts = [];
let roleOptions = [];
let roleLabel = {};
let editing = null;
let releaseFocus = null;

function renderRows(items) {
  $("emptyTip").hidden = items.length > 0;
  $("accountRows").innerHTML = items
    .map(
      (account) => `<tr>
      <td>${escapeHtml(account.display_name || "—")}</td>
      <td>${escapeHtml(account.username)}</td>
      <td><span class="tag">${escapeHtml(roleLabel[account.role] || account.role)}</span></td>
      <td><span class="node-badge ${account.status === "active" ? "trial" : ""}">${
        STATUS_LABEL[account.status] || escapeHtml(account.status)
      }</span></td>
      <td>${fmtTime(account.created_at)}</td>
      <td>
        <button class="btn-text link" type="button" data-edit="${account.id}">变更角色</button>
        <button class="btn-text link" type="button" data-status="${account.id}">${
          account.status === "active" ? "停用" : "启用"
        }</button>
      </td>
    </tr>`,
    )
    .join("");
}

async function loadList() {
  $("errorTip").hidden = true;
  try {
    const data = await adminRequest("/admin-users");
    roleOptions = data.roles || [];
    roleLabel = Object.fromEntries(roleOptions.map((role) => [role.value, role.label]));
    accounts = data.items || [];
    renderRows(accounts);
  } catch (error) {
    $("accountRows").innerHTML = "";
    $("emptyTip").hidden = true;
    $("errorText").textContent = error.message;
    $("errorTip").hidden = false;
  }
}

function openEditor(id) {
  const account = accounts.find((item) => item.id === id);
  if (!account) return;
  editing = account;
  $("roleTarget").textContent = `${account.display_name || account.username}（#${account.id}）`;
  $("roleCurrent").textContent = roleLabel[account.role] || account.role;
  $("roleSelect").innerHTML = roleOptions
    .map(
      (role) =>
        `<option value="${escapeHtml(role.value)}"${role.value === account.role ? " selected" : ""}>${escapeHtml(
          role.label,
        )}</option>`,
    )
    .join("");
  $("roleError").hidden = true;
  releaseFocus = openMask($("roleMask"), { focusSelector: "#roleSelect" });
}

function closeEditor() {
  closeMask($("roleMask"), releaseFocus);
  releaseFocus = null;
  editing = null;
}

function showEditorError(message) {
  $("roleError").textContent = message;
  $("roleError").hidden = false;
}

async function toggleStatus(id) {
  const account = accounts.find((item) => item.id === id);
  if (!account) return;
  const disabling = account.status === "active";
  const name = account.display_name || account.username;
  // 停用会把人挡在门外，值得一次确认；启用是恢复，不拦。
  if (disabling) {
    const confirmed = await confirmDialog({
      title: "停用账号",
      message: `确定停用「${name}」吗？`,
      detail: "该账号将立即无法登录，已登录的会话会被强制退出。历史数据与审计记录全部保留，随时可以重新启用。",
      confirmText: "停用",
      danger: true,
    });
    if (!confirmed) return;
  }
  try {
    await adminRequest(`/admin-users/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({ status: disabling ? "disabled" : "active" }),
    });
    toast(disabling ? `已停用「${name}」。` : `已启用「${name}」。`);
    await loadList();
  } catch (error) {
    toast(error.message, "error");
  }
}

$("accountRows").addEventListener("click", (event) => {
  const edit = event.target.closest("[data-edit]");
  if (edit) {
    openEditor(Number(edit.dataset.edit));
    return;
  }
  const status = event.target.closest("[data-status]");
  if (status) toggleStatus(Number(status.dataset.status));
});

$("retryBtn").addEventListener("click", loadList);
$("roleClose").addEventListener("click", closeEditor);
$("roleCancel").addEventListener("click", closeEditor);
$("roleMask").addEventListener("click", (event) => {
  if (event.target === $("roleMask")) closeEditor();
});

$("roleSave").addEventListener("click", async () => {
  if (!editing) return;
  const role = $("roleSelect").value;
  if (role === editing.role) {
    showEditorError("该账号已经是此角色。");
    return;
  }
  $("roleSave").disabled = true;
  try {
    await adminRequest(`/admin-users/${editing.id}/role`, {
      method: "PUT",
      body: JSON.stringify({ role }),
    });
    const label = roleLabel[role] || role;
    closeEditor();
    toast(`角色已变更为「${label}」。`);
    await loadList();
  } catch (error) {
    showEditorError(error.message);
  } finally {
    $("roleSave").disabled = false;
  }
});

(async () => {
  let me;
  try {
    me = await adminMe();
  } catch {
    return; // 未登录：initLayout 已经负责跳转登录页。
  }
  if (!me.can_manage_admin_roles) {
    $("forbiddenCard").hidden = false;
    return;
  }
  $("listCard").hidden = false;
  await loadList();
})();
