import { initLayout } from "./admin-layout.js";
import { adminMe, adminRequest } from "./admin-api.js";
import { closeMask, confirmDialog, escapeHtml, openMask, toast } from "./admin-ui.js";

initLayout();
const $ = (id) => document.getElementById(id);
// 能力清单由后端 module-registry 下发（含 implemented 标记）。接口失败时回落到这份
// 兜底，只是为了页面不至于渲染出空下拉——真正的合法性以后端校验为准。
let MODULES = [
  ["overview", "概览"], ["courses", "课程"], ["tasks", "学习任务"],
  ["explore", "探索创作"], ["paths", "学习路线"], ["projects", "实战项目"],
];
let moduleRegistry = [];
const STATUS_LABEL = { active: "已开放", planning: "规划中", hidden: "已隐藏" };
const MODULE_STATUS = { available: "可使用", planning: "规划中", hidden: "隐藏" };
let readOnly = false;
let areas = [];
let currentArea = null;
let categories = [];
let types = [];
let tags = [];
let createDraft = null;
let dirty = false;
let suppressDirty = false;
let areaSettingsRelease = null;
let createCatalogRelease = null;

function setDirty(value = true) {
  if (readOnly || suppressDirty || dirty === value) return;
  dirty = value;
  document.title = `${dirty ? "• " : ""}学习目录 · 后台`;
}

async function confirmDiscardChanges() {
  if (!dirty) return true;
  return confirmDialog({
    title: "放弃未保存的修改？",
    message: "切换专区或维护分类会丢失当前未保存的修改。",
    detail: "请先保存当前内容；确认后将放弃这些修改。",
    confirmText: "放弃修改",
    danger: true,
  });
}

function itemStatus(status) {
  return `<span class="tag ${status === "active" || status === "available" ? "" : "gray"}">${escapeHtml(STATUS_LABEL[status] || MODULE_STATUS[status] || status)}</span>`;
}

function applyReadOnlyState() {
  $("catalogReadOnlyHint").hidden = !readOnly;
  if (!readOnly) return;
  document.querySelectorAll(
    "#newAreaBtn, #areaEditorCard input, #areaEditorCard select, #areaEditorCard textarea, #areaEditorCard button, " +
    "#catalogDetails input, #catalogDetails select, #catalogDetails textarea, #catalogDetails button:not([data-tab]), " +
    "#createCatalogItem input, #createCatalogItem textarea, #createCatalogItem button",
  ).forEach((element) => { element.disabled = true; });
}

async function loadAreas(preferredKey) {
  suppressDirty = true;
  areas = await adminRequest("/learning-catalog/areas");
  if (preferredKey) currentArea = areas.find((item) => item.key === preferredKey) || null;
  if (!currentArea && areas.length) currentArea = areas[0];
  renderAreas();
  fillAreaEditor(currentArea);
  if (currentArea) await loadDetails();
  suppressDirty = false;
  setDirty(false);
}

function renderAreas() {
  const picker = $("areaPicker");
  picker.innerHTML = areas.map((area) =>
    `<option value="${escapeHtml(area.key)}">${escapeHtml(area.name)} · ${escapeHtml(STATUS_LABEL[area.status] || area.status)}</option>`,
  ).join("");
  picker.value = currentArea?.key || "";
  applyReadOnlyState();
}

function fillAreaEditor(area) {
  const creating = area === null;
  $("areaEditorTitle").textContent = creating ? "新建专区" : area.name;
  $("areaEditorHint").textContent = creating ? "创建后即可组合工作台能力" : `路由标识：${area.key}`;
  $("areaKey").value = area?.key || "";
  $("areaKey").disabled = !creating;
  $("areaName").value = area?.name || "";
  $("areaStatus").value = area?.status || "planning";
  $("areaTheme").value = area?.theme_key || "default";
  $("areaSort").value = area?.sort_order ?? 0;
  $("areaAudience").value = area?.audience || "";
  $("areaDescription").value = area?.description || "";
  $("deleteAreaBtn").hidden = creating;
  $("catalogDetails").hidden = creating;
  applyReadOnlyState();
}

function setAreaSettingsOpen(open) {
  const mask = $("areaSettingsMask");
  if (open) {
    if (!mask.hidden) return;
    fillAreaEditor(currentArea);
    areaSettingsRelease = openMask(mask, { focusSelector: "#areaName" });
  } else if (!mask.hidden) {
    closeMask(mask, areaSettingsRelease);
    areaSettingsRelease = null;
  }
}

function areaPayload() {
  return {
    key: $("areaKey").value.trim(), name: $("areaName").value.trim(),
    status: $("areaStatus").value, theme_key: $("areaTheme").value,
    sort_order: Number($("areaSort").value) || 0,
    audience: $("areaAudience").value.trim() || null,
    description: $("areaDescription").value.trim() || null,
  };
}

async function loadDetails() {
  const key = encodeURIComponent(currentArea.key);
  [categories, types, tags] = await Promise.all([
    adminRequest(`/learning-catalog/categories?area_key=${key}`),
    adminRequest(`/learning-catalog/types?area_key=${key}`),
    adminRequest(`/learning-catalog/tags?area_key=${key}`),
  ]);
  renderModules(); renderCategoryTree(); renderSimpleRows("types"); renderSimpleRows("tags");
}

function isImplemented(moduleKey) {
  const hit = moduleRegistry.find((item) => item.module_key === moduleKey);
  return hit ? hit.implemented !== false : true;
}

function moduleRow(item = {}) {
  const options = MODULES.map(([key, label]) => `<option value="${key}" ${item.module_key === key ? "selected" : ""}>${label}</option>`).join("");
  const hidden = item.status === "hidden";
  // 没有真实页面的能力不允许标成「可使用」，否则学生点进去是占位页，状态与事实相反。
  const usable = isImplemented(item.module_key || MODULES[0]?.[0]);
  // 隐藏行必须留在列表里并且看得出是隐着的。之前后端对管理端也滤掉了 hidden，
  // 那一行从界面消失、下次「保存导航」整表替换时被真删——名称和排序一起丢。
  return `<div class="catalog-row module-row${hidden ? " module-row-hidden" : ""}">
    <select class="module-key" aria-label="工作台能力">${options}</select>
    <input class="module-label" aria-label="导航名称" maxlength="50" value="${escapeHtml(item.label || "")}" placeholder="导航名称" />
    <select class="module-status" aria-label="模块状态"><option value="available" ${item.status === "available" ? "selected" : ""} ${usable ? "" : "disabled"}>可使用${usable ? "" : "（暂无页面）"}</option><option value="planning" ${!item.status || item.status === "planning" ? "selected" : ""}>规划中</option><option value="hidden" ${hidden ? "selected" : ""}>隐藏</option></select>
    <input class="module-sort" type="number" value="${item.sort_order ?? 0}" aria-label="排序" />
    <button class="btn-text link danger" data-remove-row type="button">移除</button>
    <span class="module-hidden-flag">${hidden ? "学生端不显示" : ""}</span>
  </div>`;
}

function renderModules() {
  $("moduleRows").innerHTML = (currentArea.modules || []).map(moduleRow).join("") || '<div class="empty">尚未配置工作台导航</div>';
  applyReadOnlyState();
}

function categoryOption(currentId, parentId) {
  return ['<option value="">顶级方向</option>'].concat(categories.filter((item) => item.id !== currentId).map((item) =>
    `<option value="${item.id}" ${item.id === parentId ? "selected" : ""}>${escapeHtml(item.name)}</option>`)).join("");
}

function categoryRow(item, depth = 0) {
  return `<div class="catalog-tree-row" data-id="${item.id}" style="--depth:${depth}">
    <span class="tree-line"></span><input class="item-name" aria-label="分类名称" value="${escapeHtml(item.name)}" maxlength="50" />
    <input class="item-key" value="${escapeHtml(item.key)}" maxlength="64" aria-label="稳定标识（创建后不可修改）" readonly aria-readonly="true" />
    <input class="item-description" aria-label="分类说明" value="${escapeHtml(item.description || "")}" maxlength="300" placeholder="分类说明（可选）" />
    <select class="item-parent" aria-label="上级分类">${categoryOption(item.id, item.parent_id)}</select>
    <input class="item-sort" type="number" value="${item.sort_order}" aria-label="排序" />
    <label class="catalog-switch" title="启用分类"><input class="item-active" type="checkbox" aria-label="启用分类" ${item.is_active ? "checked" : ""} /></label>
    <div class="catalog-tree-actions">
      <button class="btn-text link" data-item="save-category" type="button">保存</button>
      <button class="btn-text link" data-add-child type="button">加下级</button>
      <button class="btn-text link danger" data-item="delete-category" type="button">删除</button>
    </div>
  </div>`;
}

function renderCategoryTree() {
  const byParent = new Map();
  for (const item of categories) {
    const list = byParent.get(item.parent_id) || [];
    list.push(item); byParent.set(item.parent_id, list);
  }
  const walk = (parent, depth) => (byParent.get(parent) || []).map((item) => categoryRow(item, depth) + walk(item.id, depth + 1)).join("");
  $("categoryTree").innerHTML = walk(null, 0) || '<div class="empty">还没有分类，先添加一个方向</div>';
  applyReadOnlyState();
}

function simpleRow(kind, item) {
  const isType = kind === "types";
  return `<div class="catalog-row simple-row" data-id="${item.id}">
    <input class="item-name" aria-label="${isType ? "课程类型名称" : "标签名称"}" value="${escapeHtml(item.name)}" maxlength="50" />
    <input class="item-key" value="${escapeHtml(item.key)}" maxlength="64" aria-label="稳定标识（创建后不可修改）" readonly aria-readonly="true" />
    ${isType ? `<input class="item-description" value="${escapeHtml(item.description || "")}" maxlength="200" placeholder="用途说明" />` : ""}
    <input class="item-sort" type="number" value="${item.sort_order}" aria-label="排序" />
    <div class="catalog-simple-actions">
      <label class="catalog-switch" title="启用"><input class="item-active" type="checkbox" aria-label="启用" ${item.is_active ? "checked" : ""} /></label>
      <button class="btn-text link" data-item="save-${kind}" type="button">保存</button>
      <button class="btn-text link danger" data-item="delete-${kind}" type="button">删除</button>
    </div>
  </div>`;
}

function renderSimpleRows(kind) {
  const rows = kind === "types" ? types : tags;
  $(kind === "types" ? "typeRows" : "tagRows").innerHTML = rows.map((item) => simpleRow(kind, item)).join("") || '<div class="empty">还没有内容</div>';
  applyReadOnlyState();
}

function openCreateForm(kind, parentId = null) {
  const labels = { categories: parentId ? "下级分类" : "方向", types: "课程类型", tags: "课程特色" };
  createDraft = { kind, parentId };
  $("createCatalogTitle").textContent = `新增${labels[kind]}`;
  $("createCatalogHint").textContent = "保存后名称、排序和启停仍可维护；稳定标识不能修改。";
  $("createCatalogName").value = "";
  $("createCatalogKey").value = "";
  $("createCatalogKey").maxLength = kind === "types" ? 32 : 64;
  $("createCatalogDescription").value = "";
  $("createCatalogDescriptionRow").hidden = kind === "tags";
  const mask = $("createCatalogItem");
  if (mask.hidden) createCatalogRelease = openMask(mask, { focusSelector: "#createCatalogName" });
}

function closeCreateForm() {
  createDraft = null;
  const mask = $("createCatalogItem");
  if (!mask.hidden) {
    closeMask(mask, createCatalogRelease);
    createCatalogRelease = null;
  }
}

async function submitCreateForm() {
  if (!createDraft || !currentArea) return;
  const name = $("createCatalogName").value.trim();
  const key = $("createCatalogKey").value.trim();
  if (!name || !key) return;
  const description = $("createCatalogDescription").value.trim() || null;
  const { kind, parentId } = createDraft;
  const payload = { area_key: currentArea.key, key, name, sort_order: 0 };
  if (kind === "categories") {
    payload.parent_id = parentId;
    payload.description = description;
  } else if (kind === "types") {
    payload.description = description;
  }
  await adminRequest(`/learning-catalog/${kind}`, { method: "POST", body: JSON.stringify(payload) });
  closeCreateForm();
  await loadDetails();
  setDirty(false); toast(`${kind === "categories" ? "分类" : kind === "types" ? "课程类型" : "标签"}已添加`);
}

async function saveCategory(row) {
  const id = Number(row.dataset.id);
  await adminRequest(`/learning-catalog/categories/${id}`, { method: "PUT", body: JSON.stringify({
    area_key: currentArea.key,
    parent_id: row.querySelector(".item-parent").value ? Number(row.querySelector(".item-parent").value) : null,
    key: row.querySelector(".item-key").value.trim(), name: row.querySelector(".item-name").value.trim(),
    description: row.querySelector(".item-description").value.trim() || null,
    is_active: row.querySelector(".item-active").checked,
    sort_order: Number(row.querySelector(".item-sort").value) || 0,
  }) });
  await loadDetails(); setDirty(false); toast("分类已保存");
}

async function saveSimple(kind, row) {
  const payload = {
    area_key: currentArea.key, key: row.querySelector(".item-key").value.trim(),
    name: row.querySelector(".item-name").value.trim(),
    is_active: row.querySelector(".item-active").checked,
    sort_order: Number(row.querySelector(".item-sort").value) || 0,
  };
  if (kind === "types") payload.description = row.querySelector(".item-description").value.trim() || null;
  await adminRequest(`/learning-catalog/${kind}/${row.dataset.id}`, { method: "PUT", body: JSON.stringify(payload) });
  await loadDetails(); setDirty(false); toast("已保存");
}

async function removeItem(kind, id, label) {
  const ok = await confirmDialog({ title: `删除${label}`, message: `有下级或课包正在使用时不能删除，可以改为停用。`, confirmText: "删除", danger: true });
  if (!ok) return;
  try {
    await adminRequest(`/learning-catalog/${kind}/${id}`, { method: "DELETE" });
    await loadDetails(); toast("已删除");
  } catch (error) {
    if (!String(error.message || "").includes("停用")) throw error;
    const disable = await confirmDialog({
      title: `无法删除${label}`,
      message: error.message,
      detail: "停用后会保留既有关联，并从学生端可选目录中移除。",
      confirmText: "停用并保留关联",
      danger: true,
    });
    if (!disable) return;
    const row = (kind === "categories" ? categories : kind === "types" ? types : tags).find((item) => item.id === Number(id));
    if (!row) return;
    const path = `/learning-catalog/${kind}/${id}`;
    const payload = { ...row, area_key: currentArea.key, is_active: false };
    await adminRequest(path, { method: "PUT", body: JSON.stringify(payload) });
    await loadDetails(); toast(`${label}已停用，既有关联已保留`);
  }
}

$("areaPicker").addEventListener("change", async (event) => {
  if (!(await confirmDiscardChanges())) { event.target.value = currentArea?.key || ""; return; }
  currentArea = areas.find((area) => area.key === event.target.value) || null;
  renderAreas(); fillAreaEditor(currentArea); await loadDetails();
});
$("openAreaSettingsBtn").addEventListener("click", () => setAreaSettingsOpen(true));
$("closeAreaSettingsBtn").addEventListener("click", async () => { if (await confirmDiscardChanges()) setAreaSettingsOpen(false); });
$("areaSettingsMask").addEventListener("mousedown", async (event) => {
  if (event.target === event.currentTarget && await confirmDiscardChanges()) setAreaSettingsOpen(false);
});
$("newAreaBtn").addEventListener("click", async () => { if (!(await confirmDiscardChanges())) return; currentArea = null; renderAreas(); fillAreaEditor(null); setDirty(false); setAreaSettingsOpen(true); });
$("cancelCreateCatalogItem").addEventListener("click", async () => { if (await confirmDiscardChanges()) closeCreateForm(); });
$("createCatalogItem").addEventListener("mousedown", async (event) => {
  if (event.target === event.currentTarget && await confirmDiscardChanges()) closeCreateForm();
});
$("createCatalogItemForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { await submitCreateForm(); }
  catch (error) { toast(error.message, "error"); }
});
$("saveAreaBtn").addEventListener("click", async () => {
  const payload = areaPayload();
  if (!payload.key || !payload.name) return toast("请填写专区标识和名称", "error");
  const path = currentArea ? `/learning-catalog/areas/${currentArea.key}` : "/learning-catalog/areas";
  const method = currentArea ? "PUT" : "POST";
  try { const saved = await adminRequest(path, { method, body: JSON.stringify(payload) }); await loadAreas(saved.key); setDirty(false); setAreaSettingsOpen(false); toast("专区已保存"); }
  catch (error) { toast(error.message, "error"); }
});
$("deleteAreaBtn").addEventListener("click", async () => {
  const ok = await confirmDialog({ title: "删除专区", message: "有关联课包的专区不能删除，只能改为隐藏。", confirmText: "删除", danger: true });
  if (!ok) return;
  try { await adminRequest(`/learning-catalog/areas/${currentArea.key}`, { method: "DELETE" }); currentArea = null; await loadAreas(); toast("专区已删除"); }
  catch (error) {
    if (!String(error.message || "").includes("只能停用")) return toast(error.message, "error");
    const disable = await confirmDialog({ title: "无法删除专区", message: error.message, detail: "停用后会保留课程和目录配置，并从学生端入口隐藏。", confirmText: "停用专区", danger: true });
    if (!disable) return;
    try {
      await adminRequest(`/learning-catalog/areas/${currentArea.key}`, { method: "PUT", body: JSON.stringify({ ...areaPayload(), status: "hidden" }) });
      await loadAreas(); setDirty(false); toast("专区已停用，关联内容已保留");
    } catch (disableError) { toast(disableError.message, "error"); }
  }
});
document.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", async () => {
  if (button.classList.contains("active") || !(await confirmDiscardChanges())) return;
  document.querySelectorAll("[data-tab]").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll("[data-tab]").forEach((item) => { item.setAttribute("aria-selected", String(item === button)); item.tabIndex = item === button ? 0 : -1; });
  document.querySelectorAll("[data-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === button.dataset.tab));
  setDirty(false);
}));
document.querySelector(".zone-tabs")?.addEventListener("keydown", (event) => {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const tabs = [...document.querySelectorAll('[data-tab]')];
  const current = tabs.indexOf(document.activeElement);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  tabs[next].focus(); tabs[next].click();
});
$("addModuleBtn").addEventListener("click", () => { if ($("moduleRows").querySelector(".empty")) $("moduleRows").innerHTML = ""; $("moduleRows").insertAdjacentHTML("beforeend", moduleRow()); });
$("moduleRows").addEventListener("click", (event) => event.target.closest("[data-remove-row]")?.closest(".catalog-row")?.remove());
// 状态改成隐藏时立刻灰显并打标，运营不用等保存就知道这一行学生端看不到；
// 换能力时同步「可使用」是否可选，避免提交后才被后端 400 顶回来。
$("moduleRows").addEventListener("change", (event) => {
  const row = event.target.closest(".module-row");
  if (!row) return;
  if (event.target.closest(".module-status")) {
    const hidden = event.target.value === "hidden";
    row.classList.toggle("module-row-hidden", hidden);
    const flag = row.querySelector(".module-hidden-flag");
    if (flag) flag.textContent = hidden ? "学生端不显示" : "";
  }
  if (event.target.closest(".module-key")) {
    const usable = isImplemented(event.target.value);
    const status = row.querySelector(".module-status");
    const available = status.querySelector('option[value="available"]');
    available.disabled = !usable;
    available.textContent = usable ? "可使用" : "可使用（暂无页面）";
    if (!usable && status.value === "available") status.value = "planning";
  }
});
$("saveModulesBtn").addEventListener("click", async () => {
  const rows = [...$("moduleRows").querySelectorAll(".module-row")].map((row) => ({
    module_key: row.querySelector(".module-key").value, label: row.querySelector(".module-label").value.trim(),
    status: row.querySelector(".module-status").value, sort_order: Number(row.querySelector(".module-sort").value) || 0,
  }));
  try { const saved = await adminRequest(`/learning-catalog/areas/${currentArea.key}/modules`, { method: "PUT", body: JSON.stringify(rows) }); currentArea = saved; await loadAreas(saved.key); setDirty(false); toast("导航已保存"); }
  catch (error) { toast(error.message, "error"); }
});
$("addRootCategoryBtn").addEventListener("click", () => openCreateForm("categories"));
$("categoryTree").addEventListener("click", async (event) => {
  const row = event.target.closest(".catalog-tree-row"); if (!row) return;
  try {
    if (event.target.closest("[data-add-child]")) openCreateForm("categories", Number(row.dataset.id));
    if (event.target.closest('[data-item="save-category"]')) await saveCategory(row);
    if (event.target.closest('[data-item="delete-category"]')) await removeItem("categories", row.dataset.id, "分类");
  } catch (error) { toast(error.message, "error"); }
});
$("addTypeBtn").addEventListener("click", () => openCreateForm("types"));
$("addTagBtn").addEventListener("click", () => openCreateForm("tags"));
for (const [id, kind, label] of [["typeRows", "types", "课程类型"], ["tagRows", "tags", "标签"]]) {
  $(id).addEventListener("click", async (event) => {
    const row = event.target.closest(".catalog-row"); if (!row) return;
    try {
      if (event.target.closest(`[data-item="save-${kind}"]`)) await saveSimple(kind, row);
      if (event.target.closest(`[data-item="delete-${kind}"]`)) await removeItem(kind, row.dataset.id, label);
    } catch (error) { toast(error.message, "error"); }
  });
}

(async () => {
  try {
    readOnly = (await adminMe())?.capabilities?.content_edit !== true;
    applyReadOnlyState();
    try {
      moduleRegistry = await adminRequest("/learning-catalog/module-registry");
      if (moduleRegistry.length) MODULES = moduleRegistry.map((item) => [item.module_key, item.label]);
    } catch { /* 拉不到就用兜底清单渲染，合法性最终以后端校验为准 */ }
    await loadAreas();
  } catch (error) { toast(error.message, "error"); }
})();

document.addEventListener("input", (event) => { if (event.target.closest("#areaEditorCard, #catalogDetails, #createCatalogItem")) setDirty(); });
document.addEventListener("change", (event) => { if (event.target.closest("#areaEditorCard, #catalogDetails, #createCatalogItem")) setDirty(); });
window.addEventListener("beforeunload", (event) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
