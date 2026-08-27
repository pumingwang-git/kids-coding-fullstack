import { initLayout } from "./admin-layout.js";
import { adminDownload, adminMe, adminRequest } from "./admin-api.js";
import { confirmDialog, escapeHtml, toast } from "./admin-ui.js";

initLayout();
const $ = (id) => document.getElementById(id);
let folders = [];
const folderChildren = new Map();
const expandedFolders = new Set();
const pickerExpanded = new Set(); // 迁移弹窗目录树自己的展开状态（与主树互不干扰）
let folderId = "";
let page = 1;
let total = 0;
let readOnly = false;
let materialRefreshTimer = null;
let pendingSignature = "";
let unchangedPendingRounds = 0;

function bytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
}

function syncMaterialRefresh(hasPending, signature = "") {
  if (hasPending && materialRefreshTimer === null) {
    materialRefreshTimer = window.setInterval(() => {
      if (document.hidden) return;
      loadMaterials({ quiet: true });
    }, 3000);
  }
  if (!hasPending && materialRefreshTimer !== null) {
    window.clearInterval(materialRefreshTimer);
    materialRefreshTimer = null;
  }
  if (!hasPending) {
    pendingSignature = "";
    unchangedPendingRounds = 0;
  }
}

async function boot() {
  try { readOnly = (await adminMe())?.capabilities?.content_edit !== true; } catch { return; }
  for (const id of ["newFolderBtn", "importFolderBtn", "uploadBtn"]) $(id).disabled = readOnly;
  await Promise.all([loadFolders(), loadMaterials()]);
}

async function loadFolders(parentId = "") {
  try {
    const data = await adminRequest(`/material-folders?parent_id=${encodeURIComponent(parentId)}`);
    const items = data.items || data;
    folderChildren.set(String(parentId), items);
    if (parentId === "") folders = items;
    renderFolders();
  } catch (error) { toast(error.message, "error"); }
}

function renderFolders() {
  const rows = (parentId = "", depth = 0) => (folderChildren.get(String(parentId)) || []).map((folder) => {
    const open = expandedFolders.has(folder.id);
    const children = open ? rows(folder.id, depth + 1) : "";
    const expand = folder.child_count ? `<button class="folder-toggle" type="button" data-toggle-folder="${folder.id}" aria-label="展开或收起">${open ? "▾" : "▸"}</button>` : '<span class="folder-toggle-placeholder"></span>';
    return `<li>${expand}<button class="folder-name ${String(folder.id) === String(folderId) ? "active" : ""}" style="padding-left:${8 + depth * 16}px" type="button" data-folder="${folder.id}"><span>📁 ${escapeHtml(folder.name)}</span><small>${folder.asset_count || 0}</small></button>${readOnly ? "" : `<button class="folder-delete btn-text link danger" type="button" data-delete-folder="${folder.id}" title="删除空文件夹">×</button>`}${children ? `<ol>${children}</ol>` : ""}</li>`;
  }).join("");
  $("materialFolderTree").innerHTML = folders.length ? rows() : '<li class="muted">还没有文件夹</li>';
}

async function loadMaterials({ quiet = false } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: "50" });
  if (folderId !== "") params.set("folder_id", String(folderId));
  const keyword = $("materialKeyword").value.trim();
  const type = $("materialType").value;
  if (keyword) params.set("keyword", keyword);
  if (type) params.set("type", type);
  if (!quiet) $("materialRows").innerHTML = '<tr><td colspan="6" class="muted">正在载入…</td></tr>';
  try {
    const data = await adminRequest(`/materials?${params}`);
    total = data.total || 0;
    const items = data.items || [];
    const pending = items.filter((item) => !["ready", "failed"].includes(item.status));
    const signature = pending.map((item) => `${item.id}:${item.status}`).join(",");
    if (signature && signature === pendingSignature) unchangedPendingRounds += 1;
    else unchangedPendingRounds = 0;
    pendingSignature = signature;
    // 3 秒一次，连续 100 次无任何状态变化（约 5 分钟）即停止。
    // 后端启动扫尾只覆盖“已 complete 但后台校验中断”的行；此处不把未知上传直接判失败。
    const stuck = unchangedPendingRounds >= 100;
    syncMaterialRefresh(Boolean(pending.length) && !stuck, signature);
    $("materialsSummary").textContent = stuck
      ? `发现 ${pending.length} 份资料 5 分钟未变化，已停止自动刷新；请检查对象存储或重启后端触发扫尾。`
      : `共 ${total} 份资料 · 每页 50 条${pending.length ? " · 正在自动刷新处理状态" : ""}`;
    $("materialsPage").textContent = `第 ${page} 页`;
    $("materialsPrev").disabled = page <= 1;
    $("materialsNext").disabled = page * 50 >= total;
    $("materialRows").innerHTML = items.length ? items.map((item) => `<tr><td><strong>${escapeHtml(item.display_name)}</strong>${item.tags?.length ? `<small class="material-tags">${item.tags.map(escapeHtml).join(" · ")}</small>` : ""}</td><td>${escapeHtml(item.asset_type)}</td><td>${escapeHtml(item.folder_name || "未分类")}</td><td>${bytes(item.size_bytes)}</td><td><span class="node-badge ${item.status === "ready" ? "" : "warn"}">${item.status === "ready" ? "可用" : escapeHtml(item.status)}</span></td><td><button class="btn-text link" type="button" data-download="${item.id}" data-name="${escapeHtml(item.display_name)}">下载</button>${readOnly ? "" : `<button class="btn-text link danger" type="button" data-delete="${item.id}" data-name="${escapeHtml(item.display_name)}">删除</button>`}</td></tr>`).join("") : '<tr><td colspan="6" class="muted">没有匹配资料</td></tr>';
  } catch (error) {
    syncMaterialRefresh(false);
    if (!quiet) $("materialRows").innerHTML = `<tr><td colspan="6" class="field-error">${escapeHtml(error.message)}</td></tr>`;
  }
}

async function uploadFile(file, targetFolder) {
  const init = await adminRequest("/materials/uploads/init", { method: "POST", body: JSON.stringify({ display_name: file.name, folder_id: targetFolder || null, mime_type: file.type || null, file_size: file.size }) });
  const put = async (url, body) => {
    const response = await fetch(url, { method: "PUT", body, headers: file.type ? { "Content-Type": file.type } : {} });
    if (!response.ok) throw new Error(`对象存储上传失败（HTTP ${response.status}）。`);
    return response.headers.get("ETag") || response.headers.get("etag") || "";
  };
  const parts = [];
  if (init.mode === "presigned_put") await put(init.presigned_url, file);
  else {
    for (let number = 1; number <= init.part_count; number += 1) {
      const start = (number - 1) * init.part_size;
      const url = await adminRequest(`/materials/uploads/${init.upload_session_id}/parts/${number}`);
      parts.push({ part_number: number, etag: await put(url.url, file.slice(start, Math.min(start + init.part_size, file.size))) });
    }
  }
  await adminRequest(`/materials/uploads/${init.upload_session_id}/complete`, { method: "POST", body: JSON.stringify({ parts }) });
}

async function uploadSelected(files) {
  const list = [...files];
  if (!list.length) return;
  $("materialsSummary").textContent = `正在上传 0 / ${list.length}…`;
  let succeeded = 0;
  for (const file of list) {
    try { await uploadFile(file, folderId); succeeded += 1; $("materialsSummary").textContent = `正在上传 ${succeeded} / ${list.length}…`; }
    catch (error) { toast(`《${file.name}》上传失败：${error.message}`, "error"); }
  }
  toast(`${succeeded} 份资料已提交校验；状态变为“可用”后才能绑定到课时。`);
  await loadMaterials();
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && materialRefreshTimer !== null) loadMaterials({ quiet: true });
});
window.addEventListener("beforeunload", () => syncMaterialRefresh(false));

async function uploadImportItem(sessionId, upload, file) {
  const put = async (url, body) => {
    const response = await fetch(url, { method: "PUT", body, headers: file.type ? { "Content-Type": file.type } : {} });
    if (!response.ok) throw new Error(`对象存储上传失败（HTTP ${response.status}）。`);
    return response.headers.get("ETag") || response.headers.get("etag") || "";
  };
  const parts = [];
  if (upload.mode === "presigned_put") await put(upload.presigned_url, file);
  else {
    for (let number = 1; number <= upload.part_count; number += 1) {
      const start = (number - 1) * upload.part_size;
      const signed = await adminRequest(`/material-imports/${sessionId}/items/${upload.item_id}/part-url?part_number=${number}`);
      parts.push({ part_number: number, etag: await put(signed.url, file.slice(start, Math.min(start + upload.part_size, file.size))) });
    }
  }
  await adminRequest(`/material-imports/${sessionId}/items/${upload.item_id}/complete`, { method: "POST", body: JSON.stringify({ parts }) });
}

async function allImportItems(sessionId) {
  const result = [];
  for (let importPage = 1; ; importPage += 1) {
    const data = await adminRequest(`/material-imports/${sessionId}?page=${importPage}&page_size=200`);
    result.push(...(data.items || []));
    if (result.length >= data.total) return result;
  }
}

function watchImport(sessionId, totalFiles, onDone) {
  let attempts = 0;
  const timer = setInterval(async () => {
    try {
      const state = await adminRequest(`/material-imports/${sessionId}?page_size=1`);
      const done = (state.stats?.imported || 0) + (state.stats?.skipped || 0) + (state.stats?.failed || 0) + (state.stats?.conflicted || 0);
      setImportProgress(state.status === "finalizing" ? "正在由服务端校验哈希并归档" : `迁移状态：${state.status}`, done, totalFiles);
      attempts += 1;
      if (!["finalizing", "uploading", "collecting"].includes(state.status) || attempts >= 360) {
        clearInterval(timer);
        onDone?.();
      }
    } catch { clearInterval(timer); }
  }, 2000);
}

// ---- Windows 文件夹迁移：目标目录树选择器 + 结果页（2026-08-10 定稿） ----
// 之前目标目录隐式用「左侧当前选中的文件夹」，用户看不清落到哪、也常出现
// 「迁移完文件不显示」。现在：
//   1. 弹窗里必选「保存到」目录树（默认当前选中文件夹，可改到任意目录/根）；
//   2. 最终化完成后自动切到目标文件夹刷新列表；
//   3. 结果页展示 成功/跳过/冲突/失败 计数与失败文件清单（可复制）。

function openImportModal(files) {
  const list = [...files];
  const root = (list[0].webkitRelativePath || list[0].name).split("/")[0] || "Windows 文件夹";
  let pickFolderId = folderId || "";
  let pickFolderName = "";

  const mask = document.createElement("div");
  mask.className = "modal-mask show import-config-mask";
  mask.innerHTML = `<section class="modal" role="dialog" aria-modal="true" aria-labelledby="importConfigTitle">
    <div class="modal-head"><h2 id="importConfigTitle">Windows 文件夹迁移</h2><button class="modal-close" type="button" data-close-import aria-label="关闭">×</button></div>
    <div class="modal-body form-only">
      <div class="form-field"><label>来源目录</label><p class="muted" style="margin:4px 0 0">${escapeHtml(root)} · 共 ${list.length} 个文件</p></div>
      <div class="form-field"><label>冲突策略</label><select id="importPolicy">
        <option value="skip">skip · 同名跳过，保留现有资料</option>
        <option value="rename">rename · 自动重命名，两份都保留</option>
        <option value="version">version · 同名不同内容新建版本</option>
      </select></div>
      <div class="form-field"><label>保存到 <b class="req">*</b></label>
        <p class="muted" style="margin:0 0 6px">迁移后的文件放到该目录；保留目录结构时，子文件夹会在其下自动创建。</p>
        <div class="import-folder-picker"><ol id="importPickerTree"></ol></div>
      </div>
    </div>
    <div class="modal-foot"><button class="btn" type="button" data-close-import>取消</button><span class="spacer"></span><button class="btn primary" type="button" data-start-import>开始迁移</button></div>
  </section>`;
  document.body.append(mask);

  const tree = mask.querySelector("#importPickerTree");
  const renderPicker = () => {
    tree.innerHTML = `<li><button class="folder-name ${pickFolderId === "" ? "active" : ""}" type="button" data-pick-folder="">🗂 资料库根目录</button></li>${pickerRows("", 0)}`;
  };
  const pickerRows = (parentId, depth) =>
    (folderChildren.get(String(parentId)) || []).map((folder) => {
      const open = pickerExpanded.has(folder.id);
      const children = open ? pickerRows(folder.id, depth + 1) : "";
      const toggle = folder.child_count
        ? `<button class="folder-toggle" type="button" data-toggle-pick="${folder.id}" aria-label="展开或收起">${open ? "▾" : "▸"}</button>`
        : '<span class="folder-toggle-placeholder"></span>';
      const active = String(folder.id) === String(pickFolderId);
      return `<li>${toggle}<button class="folder-name ${active ? "active" : ""}" style="padding-left:${8 + depth * 16}px" type="button" data-pick-folder="${folder.id}">📁 ${escapeHtml(folder.name)}</button>${children ? `<ol>${children}</ol>` : ""}</li>`;
    }).join("");

  mask.addEventListener("click", async (event) => {
    if (event.target === mask || event.target.closest("[data-close-import]")) { mask.remove(); return; }
    const toggle = event.target.closest("[data-toggle-pick]");
    if (toggle) {
      const id = Number(toggle.dataset.togglePick);
      if (pickerExpanded.has(id)) { pickerExpanded.delete(id); renderPicker(); }
      else {
        pickerExpanded.add(id);
        if (!folderChildren.has(String(id))) await loadFolders(id);
        renderPicker();
      }
      return;
    }
    const pick = event.target.closest("[data-pick-folder]");
    if (pick) {
      const raw = pick.dataset.pickFolder;
      if (raw === "") { pickFolderId = ""; pickFolderName = "资料库根目录"; }
      else { pickFolderId = Number(raw); pickFolderName = pick.textContent.trim() || "目标文件夹"; }
      renderPicker();
      return;
    }
    if (event.target.closest("[data-start-import]")) {
      const policy = mask.querySelector("#importPolicy").value;
      mask.remove();
      await runImport(list, root, policy, pickFolderId, pickFolderName);
    }
  });
  // 根目录在 boot 时已加载（folderChildren 有 "" 键），直接渲染即可；
  // 子目录懒加载：点展开箭头时补拉。
  renderPicker();
}

async function runImport(files, root, policy, targetFolderId, targetName) {
  try {
    await adminMe(); // 在创建会话前明确检查，避免 401 后看起来像按钮没有反应。
    const session = await adminRequest("/material-imports", { method: "POST", body: JSON.stringify({ source_root_name: root, target_folder_id: targetFolderId || null, preserve_structure: true, conflict_policy: policy }) });
    const manifest = files.map((file, index) => ({ client_id: `${crypto.randomUUID().replaceAll("-", "")}_${index}`, relative_path: file.webkitRelativePath || file.name, file_name: file.name, size_bytes: file.size, mime_type: file.type || null }));
    setImportProgress("正在建立迁移清单", 0, manifest.length);
    for (let start = 0; start < manifest.length; start += 500) {
      await adminRequest(`/material-imports/${session.id}/manifest-batches`, { method: "POST", body: JSON.stringify({ items: manifest.slice(start, start + 500) }) });
      setImportProgress("正在建立迁移清单", Math.min(start + 500, manifest.length), manifest.length);
    }
    const filesByClientId = new Map(manifest.map((item, index) => [item.client_id, files[index]]));
    const items = await allImportItems(session.id);
    let completed = 0;
    for (let start = 0; start < items.length; start += 100) {
      const batch = items.slice(start, start + 100).filter((item) => item.status === "pending" || item.status === "failed");
      if (!batch.length) { completed += Math.min(100, items.length - start); continue; }
      const prepared = await adminRequest(`/material-imports/${session.id}/upload-parts`, { method: "POST", body: JSON.stringify({ item_ids: batch.map((item) => item.id) }) });
      for (const upload of prepared.items || []) {
        const file = filesByClientId.get(upload.client_id);
        if (!file) throw new Error(`找不到迁移源文件：${upload.client_id}`);
        await uploadImportItem(session.id, upload, file);
        completed += 1;
        setImportProgress("正在迁移文件（支持分片）", completed, manifest.length);
      }
    }
    await adminRequest(`/material-imports/${session.id}/finalize`, { method: "POST", body: "{}" });
    setImportProgress("上传完成，正在由服务端校验并建立资料库记录", completed, manifest.length);
    watchImport(session.id, manifest.length, () => finishImport(session.id, targetFolderId, targetName));
    toast("文件已上传，后台正在校验哈希、处理冲突并建立文件夹结构。");
  } catch (error) {
    if (/未登录|401|会话/i.test(error.message)) {
      setImportProgress("迁移未开始：当前登录会话无效", 0, 1, "请使用当前地址重新登录后再试。不要在 localhost 和 127.0.0.1 之间切换，它们的登录 Cookie 不共享。");
    }
    toast(error.message, "error");
  }
}

async function finishImport(sessionId, targetFolderId, targetName) {
  // 自动切到目标文件夹并刷新——修复「迁移完文件在列表里看不到」的根因：
  // 之前只 loadMaterials() 刷新当前视图，而文件落到了别处。
  folderId = targetFolderId || "";
  page = 1;
  $("materialPath").textContent = folderId === "" ? "全部资料" : `文件夹：${targetName || "目标目录"}`;
  await Promise.all([loadFolders(), loadMaterials()]);
  await renderImportResult(sessionId);
}

async function renderImportResult(sessionId) {
  try {
    const state = await adminRequest(`/material-imports/${sessionId}?page_size=1`);
    const summary = state.summary || {};
    const failedItems = [];
    for (let importPage = 1; ; importPage += 1) {
      const data = await adminRequest(`/material-imports/${sessionId}?page=${importPage}&page_size=200&status=failed`);
      failedItems.push(...(data.items || []));
      if (failedItems.length >= data.total) break;
    }
    const failedList = failedItems.map((item) => item.relative_path || item.file_name).join("\n") || "无";
    $("importStatus").hidden = false;
    $("importStatus").innerHTML = `<div class="import-result">
      <strong>迁移完成</strong>
      <div class="import-result-stats">
        <span class="stat ok">成功 ${summary.success || 0}</span>
        <span class="stat">跳过 ${summary.skipped || 0}</span>
        <span class="stat warn">冲突 ${summary.conflicted || 0}</span>
        <span class="stat err">失败 ${summary.failed || 0}</span>
      </div>
      ${failedItems.length ? `<p class="field-error">失败 ${failedItems.length} 个文件：</p><pre class="import-failed-list">${escapeHtml(failedList)}</pre><button class="btn" type="button" id="copyFailedList">复制失败清单</button>` : ""}
      <p class="muted">已自动切换到迁移目标文件夹。</p>
    </div>`;
    const copy = $("copyFailedList");
    if (copy) copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(failedList); toast("失败清单已复制"); } catch { toast("复制失败，请手动选择复制。", "error"); }
    });
  } catch { /* 结果页失败不阻塞——列表已刷新 */ }
}

async function startFolderImport(files) {
  const list = [...files];
  if (!list.length) return;
  openImportModal(list);
}

function setImportProgress(label, value, max, detail = "") {
  $("importStatus").hidden = false;
  $("importStatus").innerHTML = `<strong>${escapeHtml(label)}</strong><div class="import-progress"><progress value="${value}" max="${max || 1}"></progress><span>${value} / ${max}</span></div>${detail ? `<p class="field-error">${escapeHtml(detail)}</p>` : ""}`;
}

$("materialFolderTree").addEventListener("click", async (event) => {
  const toggle = event.target.closest("[data-toggle-folder]");
  if (toggle) { const id = Number(toggle.dataset.toggleFolder); if (expandedFolders.has(id)) expandedFolders.delete(id); else { expandedFolders.add(id); if (!folderChildren.has(String(id))) await loadFolders(id); } renderFolders(); return; }
  const button = event.target.closest("[data-folder]");
  if (button) { folderId = Number(button.dataset.folder); page = 1; $("materialPath").textContent = `文件夹：${button.textContent.trim()}`; renderFolders(); await loadMaterials(); return; }
  const del = event.target.closest("[data-delete-folder]");
  if (!del) return;
  const ok = await confirmDialog({ title: "删除文件夹", message: "确定删除此空文件夹吗？", detail: "包含子文件夹或资料时系统会拒绝删除，避免递归误删。", confirmText: "删除", danger: true });
  if (!ok) return;
  try { await adminRequest(`/material-folders/${del.dataset.deleteFolder}`, { method: "DELETE" }); toast("文件夹已删除"); if (Number(folderId) === Number(del.dataset.deleteFolder)) folderId = ""; await loadFolders(); } catch (error) { toast(error.message, "error"); }
});
$("allMaterialsBtn").addEventListener("click", () => { folderId = ""; page = 1; $("materialPath").textContent = "全部资料"; renderFolders(); loadMaterials(); });
$("searchMaterialsBtn").addEventListener("click", () => { page = 1; loadMaterials(); });
$("materialKeyword").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); page = 1; loadMaterials(); } });
$("materialType").addEventListener("change", () => { page = 1; loadMaterials(); });
$("materialsPrev").addEventListener("click", () => { if (page > 1) { page -= 1; loadMaterials(); } });
$("materialsNext").addEventListener("click", () => { if (page * 50 < total) { page += 1; loadMaterials(); } });
$("uploadBtn").addEventListener("click", () => $("uploadInput").click());
$("uploadInput").addEventListener("change", async (event) => { await uploadSelected(event.target.files); event.target.value = ""; });
$("importFolderBtn").addEventListener("click", () => $("importInput").click());
$("importInput").addEventListener("change", async (event) => { await startFolderImport(event.target.files); event.target.value = ""; });
$("newFolderBtn").addEventListener("click", async () => { const name = await promptDialog({ title: "新建资料文件夹", label: "文件夹名称", placeholder: "如：第一章资料", maxLength: 200, confirmText: "创建" }); if (!name) return; try { await adminRequest("/material-folders", { method: "POST", body: JSON.stringify({ name, parent_id: folderId || null }) }); toast("文件夹已创建"); await loadFolders(); } catch (error) { toast(error.message, "error"); } });
$("materialRows").addEventListener("click", async (event) => { const download = event.target.closest("[data-download]"); if (download) { try { await adminDownload(`/materials/${download.dataset.download}/download`, download.dataset.name); } catch (error) { toast(error.message, "error"); } return; } const del = event.target.closest("[data-delete]"); if (!del) return; const ok = await confirmDialog({ title: "删除资料", message: `确定删除《${del.dataset.name}》吗？`, detail: "如果该资料仍被课时引用，系统会拒绝删除并提示先解绑。", confirmText: "删除", danger: true }); if (!ok) return; try { await adminRequest(`/materials/${del.dataset.delete}`, { method: "DELETE" }); toast("资料已删除"); await loadMaterials(); } catch (error) { toast(error.message, "error"); } });

boot();
