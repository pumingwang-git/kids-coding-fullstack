// 后台账号角色管理（ADR-001 §2.4：变更 AdminUser.role 仅限 super_admin）。
//
// 两条纪律：
// 1. 隐藏入口不是授权。这里的 can_manage_admin_roles 分支只决定「看不看得见」，
//    真正拦住越权的是后端 PUT /api/admin/admin-users/{id}/role 的 403。
// 2. 角色清单不在前端硬编码，一律取自列表接口的 roles（源头是 permissions.py 的
//    ROLE_LABELS）。前端抄一份角色集合，就是下次加角色时必然漏改的那一处。

import { adminMe, adminRequest, ifMatch } from "./admin-api.js";
import { initLayout } from "./admin-layout.js";
import { closeMask, confirmDialog, escapeHtml, fmtTime, openMask, toast } from "./admin-ui.js";

// 只有启用/停用两态，不做删除（《41、管理端账号管理范围裁决》§2.1）。
const STATUS_LABEL = { active: "启用", disabled: "已停用" };

// 数据范围徽标的配色：全局最显眼（能看到全校学生），限本班次之，不涉及学生数据用默认灰。
// 文案本身一律来自接口，这里只决定怎么上色。
const SCOPE_BADGE = { global: "warn", class: "trial", none: "" };

initLayout();

const $ = (id) => document.getElementById(id);

let accounts = [];
let roleOptions = [];
let capabilityOptions = [];
let policyRoles = [];
let scopeOptions = [];
let roleLabel = {};
let roleScope = {};
let roleCapabilities = {};
let editing = null;
let releaseFocus = null;
let releaseCreateFocus = null;
let releasePasswordFocus = null;
let releasePolicyFocus = null;
let editingPolicy = null;

function scopeBadge(role) {
  const option = roleScope[role];
  if (!option) return "";
  return `<span class="node-badge ${SCOPE_BADGE[option.scope] || ""}" title="${escapeHtml(
    option.scope_note,
  )}">${escapeHtml(option.scope_label)}</span>`;
}

function renderRows(items) {
  $("emptyTip").hidden = items.length > 0;
  $("accountRows").innerHTML = items
    .map(
      (account) => `<tr>
      <td>${escapeHtml(account.display_name || "—")}</td>
      <td>${escapeHtml(account.username)}</td>
      <td>
        <span class="tag">${escapeHtml(roleLabel[account.role] || account.role)}</span>
        ${scopeBadge(account.role)}
      </td>
      <td><span class="node-badge ${account.status === "active" ? "trial" : ""}">${
        STATUS_LABEL[account.status] || escapeHtml(account.status)
      }</span></td>
      <td>${fmtTime(account.created_at)}</td>
      <td>
        <button class="btn-text link" type="button" data-edit="${account.id}">变更角色</button>
        <button class="btn-text link" type="button" data-status="${account.id}">${
          account.status === "active" ? "停用" : "启用"
        }</button>
        <button class="btn-text link" type="button" data-reset="${account.id}">重置密码</button>
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
    const roleDirectory = data.role_directory || roleOptions;
    roleLabel = Object.fromEntries(roleDirectory.map((role) => [role.value, role.label]));
    roleScope = Object.fromEntries(roleDirectory.map((role) => [role.value, role]));
    roleCapabilities = Object.fromEntries(roleDirectory.map((role) => [role.value, role.capabilities || {}]));
    capabilityOptions = data.capabilities || [];
    accounts = data.items || [];
    renderRows(accounts);
    renderPermissionMatrix();
  } catch (error) {
    $("accountRows").innerHTML = "";
    $("emptyTip").hidden = true;
    $("errorText").textContent = error.message;
    $("errorTip").hidden = false;
  }
}

function enabledCapabilityLabels(role) {
  return capabilityOptions
    .filter((capability) => role.capabilities?.[capability.key])
    .map((capability) => capability.label);
}

function renderRolePolicies() {
  $("rolePolicyEmpty").hidden = policyRoles.length > 0;
  $("rolePolicyList").innerHTML = policyRoles
    .map((role) => {
      const labels = enabledCapabilityLabels(role);
      const policyState = role.is_protected
        ? '<span class="tag warn">受保护</span>'
        : role.is_system
          ? '<span class="tag gray">系统角色</span>'
          : '<span class="tag">自定义</span>';
      const action = role.is_protected
        ? '<span class="muted">策略不可修改</span>'
        : `<button class="btn-text link" type="button" data-policy-edit="${escapeHtml(role.value)}">编辑策略</button>`;
      return `<article class="role-policy-row">
        <div class="role-policy-identity">
          <div><strong>${escapeHtml(role.label)}</strong><code>${escapeHtml(role.value)}</code></div>
          <div class="role-policy-tags">${policyState}${scopeBadge(role.value)}<span class="tag gray">v${role.revision}</span></div>
        </div>
        <p>${escapeHtml(role.description || role.scope_note)}</p>
        <div class="role-policy-capabilities">${
          labels.length
            ? labels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")
            : '<span class="muted">无业务权限</span>'
        }</div>
        <div class="role-policy-action">${action}</div>
      </article>`;
    })
    .join("");
}

async function loadRolePolicies() {
  $("rolePolicyError").hidden = true;
  try {
    const data = await adminRequest("/roles");
    policyRoles = data.items || [];
    capabilityOptions = data.capabilities || [];
    scopeOptions = data.scopes || [];
    roleLabel = { ...roleLabel, ...Object.fromEntries(policyRoles.map((role) => [role.value, role.label])) };
    roleScope = { ...roleScope, ...Object.fromEntries(policyRoles.map((role) => [role.value, role])) };
    roleCapabilities = { ...roleCapabilities, ...Object.fromEntries(policyRoles.map((role) => [role.value, role.capabilities || {}])) };
    renderRolePolicies();
    renderPermissionMatrix();
  } catch (error) {
    $("rolePolicyList").innerHTML = "";
    $("rolePolicyEmpty").hidden = true;
    $("rolePolicyErrorText").textContent = error.message;
    $("rolePolicyError").hidden = false;
  }
}

function renderPermissionMatrix() {
  const groups = [...new Set(capabilityOptions.map((capability) => capability.group))];
  const header = `<thead><tr><th>角色</th><th>数据范围</th>${groups.map((group) => `<th>${escapeHtml(group)}</th>`).join("")}</tr></thead>`;
  const rows = roleOptions.map((role) => {
    const cells = groups.map((group) => {
      const items = capabilityOptions.filter((capability) => capability.group === group);
      const enabled = items.filter((capability) => roleCapabilities[role.value]?.[capability.key]);
      return `<td>${enabled.length ? enabled.map((capability) => `<span class="permission-item" title="${escapeHtml(capability.description)}">${escapeHtml(capability.label)}</span>`).join("") : '<span class="muted">—</span>'}</td>`;
    }).join("");
    return `<tr><th>${escapeHtml(role.label)}</th><td>${scopeBadge(role.value)}</td>${cells}</tr>`;
  }).join("");
  $("permissionMatrix").innerHTML = header + `<tbody>${rows}</tbody>`;
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
  renderScopeNote();
  releaseFocus = openMask($("roleMask"), { focusSelector: "#roleSelect" });
}

// 选中哪个角色就显示哪个角色的范围说明——让操作者在点保存前看到影响面，
// 而不是等对方打开页面全空之后来报假 bug。
function renderScopeNote() {
  const option = roleScope[$("roleSelect").value];
  $("roleScopeNote").textContent = option ? option.scope_note : "—";
}

$("roleSelect").addEventListener("change", renderScopeNote);

function closeEditor() {
  closeMask($("roleMask"), releaseFocus);
  releaseFocus = null;
  editing = null;
}

function showEditorError(message) {
  $("roleError").textContent = message;
  $("roleError").hidden = false;
}

function roleOptionsMarkup(selected = "") {
  return roleOptions.map((role) => `<option value="${escapeHtml(role.value)}"${role.value === selected ? " selected" : ""}>${escapeHtml(role.label)}</option>`).join("");
}

function renderCreateRoleNote() {
  const option = roleScope[$("createRole").value];
  $("createRoleNote").textContent = option?.scope_note || "—";
}

function openCreateAccount() {
  $("createUsername").value = "";
  $("createDisplayName").value = "";
  $("createRole").innerHTML = roleOptionsMarkup();
  $("createError").hidden = true;
  renderCreateRoleNote();
  releaseCreateFocus = openMask($("createMask"), { focusSelector: "#createUsername" });
}

function closeCreateAccount() {
  closeMask($("createMask"), releaseCreateFocus);
  releaseCreateFocus = null;
}

function showInitialPassword(password) {
  $("initialPassword").textContent = password;
  releasePasswordFocus = openMask($("passwordMask"), { focusSelector: "#copyInitialPassword" });
}

function closeInitialPassword() {
  $("initialPassword").textContent = "";
  closeMask($("passwordMask"), releasePasswordFocus);
  releasePasswordFocus = null;
}

function rolePolicyPayload() {
  return {
    key: $("rolePolicyKey").value.trim(),
    label: $("rolePolicyLabel").value.trim(),
    description: $("rolePolicyDescription").value.trim(),
    scope: $("rolePolicyScope").value,
    capabilities: [...document.querySelectorAll("[data-capability]:checked")].map(
      (input) => input.dataset.capability,
    ),
  };
}

function renderCapabilityEditor(selected = []) {
  const selectedSet = new Set(selected);
  const groups = [...new Set(capabilityOptions.map((capability) => capability.group))];
  $("roleCapabilityGroups").innerHTML = groups
    .map((group) => {
      const items = capabilityOptions.filter((capability) => capability.group === group);
      return `<section class="role-capability-group"><h3>${escapeHtml(group)}</h3>${items
        .map(
          (capability) => `<label class="role-capability-option${capability.assignable === false ? " is-locked" : ""}">
            <input type="checkbox" data-capability="${escapeHtml(capability.key)}"${
              selectedSet.has(capability.key) ? " checked" : ""
            }${capability.assignable === false ? " disabled" : ""} />
            <span><strong>${escapeHtml(capability.label)}</strong><small>${escapeHtml(
              capability.assignable === false ? "仅超级管理员可持有" : capability.description,
            )}</small></span>
          </label>`,
        )
        .join("")}</section>`;
    })
    .join("");
}

function openRolePolicyEditor(role = null) {
  editingPolicy = role;
  $("rolePolicyTitle").textContent = role ? "编辑角色策略" : "新增角色";
  $("rolePolicySave").textContent = role ? "保存策略" : "创建角色";
  $("rolePolicyDelete").hidden = !role || role.is_system || role.is_protected;
  $("rolePolicyKey").value = role?.value || "";
  $("rolePolicyKey").disabled = Boolean(role);
  $("rolePolicyLabel").value = role?.label || "";
  $("rolePolicyDescription").value = role?.description || "";
  $("rolePolicyScope").innerHTML = scopeOptions
    .map(
      (scope) => `<option value="${escapeHtml(scope.value)}"${scope.value === (role?.scope || "none") ? " selected" : ""}>${escapeHtml(scope.label)}</option>`,
    )
    .join("");
  renderCapabilityEditor(
    role
      ? Object.entries(role.capabilities || {}).filter(([, enabled]) => enabled).map(([key]) => key)
      : [],
  );
  $("rolePolicyFormError").hidden = true;
  releasePolicyFocus = openMask($("rolePolicyMask"), {
    focusSelector: role ? "#rolePolicyLabel" : "#rolePolicyKey",
  });
}

function closeRolePolicyEditor() {
  closeMask($("rolePolicyMask"), releasePolicyFocus);
  releasePolicyFocus = null;
  editingPolicy = null;
}

async function saveRolePolicy() {
  $("rolePolicyFormError").hidden = true;
  $("rolePolicySave").disabled = true;
  try {
    const payload = rolePolicyPayload();
    if (!payload.key || !payload.label) throw new Error("请填写角色标识和角色名称。");
    if (editingPolicy) {
      await adminRequest(`/roles/${encodeURIComponent(editingPolicy.value)}`, {
        method: "PUT",
        headers: ifMatch(editingPolicy.revision),
        body: JSON.stringify(payload),
      });
      toast(`已更新角色「${payload.label}」。`);
    } else {
      await adminRequest("/roles", { method: "POST", body: JSON.stringify(payload) });
      toast(`已创建角色「${payload.label}」。`);
    }
    closeRolePolicyEditor();
    await loadList();
    await loadRolePolicies();
  } catch (error) {
    $("rolePolicyFormError").textContent = error.status === 409
      ? `${error.message} 已重新加载最新角色策略。`
      : error.message;
    $("rolePolicyFormError").hidden = false;
    if (error.status === 409) await loadRolePolicies();
  } finally {
    $("rolePolicySave").disabled = false;
  }
}

async function deleteRolePolicy() {
  if (!editingPolicy) return;
  const confirmed = await confirmDialog({
    title: "退役角色",
    message: `确定退役「${editingPolicy.label}」吗？`,
    detail: "角色标识将永久保留且不可复用；仍有账号使用时服务端会拒绝退役。",
    confirmText: "退役角色",
    danger: true,
  });
  if (!confirmed) return;
  try {
    const label = editingPolicy.label;
    await adminRequest(`/roles/${encodeURIComponent(editingPolicy.value)}`, {
      method: "DELETE",
      headers: ifMatch(editingPolicy.revision),
    });
    closeRolePolicyEditor();
    toast(`角色「${label}」已退役。`);
    await loadList();
    await loadRolePolicies();
  } catch (error) {
    $("rolePolicyFormError").textContent = error.message;
    $("rolePolicyFormError").hidden = false;
  }
}

async function createAccount() {
  $("createError").hidden = true;
  $("createSave").disabled = true;
  try {
    const result = await adminRequest("/admin-users", {
      method: "POST",
      body: JSON.stringify({
        username: $("createUsername").value.trim(),
        display_name: $("createDisplayName").value.trim(),
        role: $("createRole").value,
      }),
    });
    closeCreateAccount();
    showInitialPassword(result.initial_password);
    await loadList();
  } catch (error) {
    $("createError").textContent = error.message;
    $("createError").hidden = false;
  } finally {
    $("createSave").disabled = false;
  }
}

async function resetPassword(id) {
  const account = accounts.find((item) => item.id === id);
  if (!account) return;
  const name = account.display_name || account.username;
  const confirmed = await confirmDialog({
    title: "重置密码",
    message: `确定重置「${name}」的密码吗？`,
    detail: "该账号的全部现有会话会立即失效，并生成只能显示一次的初始口令。",
    confirmText: "重置密码",
    danger: true,
  });
  if (!confirmed) return;
  try {
    const result = await adminRequest(`/admin-users/${id}/password-reset`, { method: "POST", body: "{}" });
    showInitialPassword(result.initial_password);
    await loadList();
  } catch (error) {
    toast(error.message, "error");
  }
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
  if (status) {
    toggleStatus(Number(status.dataset.status));
    return;
  }
  const reset = event.target.closest("[data-reset]");
  if (reset) resetPassword(Number(reset.dataset.reset));
});

$("retryBtn").addEventListener("click", loadList);
$("rolePolicyRetry").addEventListener("click", loadRolePolicies);
$("createRoleBtn").addEventListener("click", () => openRolePolicyEditor());
$("rolePolicyClose").addEventListener("click", closeRolePolicyEditor);
$("rolePolicyCancel").addEventListener("click", closeRolePolicyEditor);
$("rolePolicySave").addEventListener("click", saveRolePolicy);
$("rolePolicyDelete").addEventListener("click", deleteRolePolicy);
$("rolePolicyMask").addEventListener("click", (event) => {
  if (event.target === $("rolePolicyMask")) closeRolePolicyEditor();
});
$("rolePolicyList").addEventListener("click", (event) => {
  const button = event.target.closest("[data-policy-edit]");
  if (!button) return;
  const role = policyRoles.find((item) => item.value === button.dataset.policyEdit);
  if (role) openRolePolicyEditor(role);
});
$("roleClose").addEventListener("click", closeEditor);
$("roleCancel").addEventListener("click", closeEditor);
$("roleMask").addEventListener("click", (event) => {
  if (event.target === $("roleMask")) closeEditor();
});
$("createAccountBtn").addEventListener("click", openCreateAccount);
$("createRole").addEventListener("change", renderCreateRoleNote);
$("createClose").addEventListener("click", closeCreateAccount);
$("createCancel").addEventListener("click", closeCreateAccount);
$("createSave").addEventListener("click", createAccount);
$("createMask").addEventListener("click", (event) => { if (event.target === $("createMask")) closeCreateAccount(); });
$("passwordDone").addEventListener("click", closeInitialPassword);
$("copyInitialPassword").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("initialPassword").textContent);
  toast("一次性口令已复制。");
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
      headers: ifMatch(editing.role_revision),
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
  $("permissionCard").hidden = false;
  $("rolePolicyCard").hidden = false;
  $("createAccountBtn").hidden = false;
  $("createRoleBtn").hidden = false;
  await loadList();
  await loadRolePolicies();
})();
