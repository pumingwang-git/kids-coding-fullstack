// 后台账号角色管理（ADR-001 §2.4：变更 AdminUser.role 仅限 super_admin）。
//
// 两条纪律：
// 1. 隐藏入口不是授权。这里的 can_manage_admin_roles 分支只决定「看不看得见」，
//    真正拦住越权的是后端 PUT /api/admin/admin-users/{id}/role 的 403。
// 2. 角色清单不在前端硬编码，一律取自列表接口的 roles（源头是 permissions.py 的
//    ROLE_LABELS）。前端抄一份角色集合，就是下次加角色时必然漏改的那一处。

import { adminMe, adminRequest } from "./admin-api.js";
import { initLayout } from "./admin-layout.js";
import { closeMask, escapeHtml, fmtTime, openMask, toast } from "./admin-ui.js";

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
      <td><span class="node-badge ${account.status === "active" ? "trial" : "warn"}">${
        account.status === "active" ? "启用" : escapeHtml(account.status)
      }</span></td>
      <td>${fmtTime(account.created_at)}</td>
      <td><button class="btn-text link" type="button" data-edit="${account.id}">变更角色</button></td>
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

$("accountRows").addEventListener("click", (event) => {
  const button = event.target.closest("[data-edit]");
  if (button) openEditor(Number(button.dataset.edit));
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
