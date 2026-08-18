// 班级列表与详情：可见范围由后端 /classes 返回，前端不按角色再过滤。
import { initLayout } from "./admin-layout.js";
import { adminRequest } from "./admin-api.js";
import { escapeHtml, fmtTime, toast } from "./admin-ui.js";

initLayout();

const $ = (id) => document.getElementById(id);
let classes = [];
let selectedId = Number(new URLSearchParams(location.search).get("id")) || null;

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
  $("classRows").innerHTML = visible.map((row) => `
    <tr class="class-row" data-id="${row.id}">
      <td><a class="class-name-link" href="classes.html?id=${row.id}">${escapeHtml(row.name)}</a></td>
      <td class="class-code">${row.course_id}</td>
      <td><span class="${statusClass(row.status)}">${escapeHtml(row.status_label)}</span></td>
      <td>${escapeHtml(fmtTime(row.start_at) || "未设置")}</td>
      <td>${escapeHtml(fmtTime(row.end_at) || "未设置")}</td>
      <td><a class="btn-text" href="classes.html?id=${row.id}">查看详情</a></td>
    </tr>`).join("");
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
  ].map(([label, value]) => `
    <div class="class-detail-field"><dt>${label}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join("");
  $("classDetail").hidden = false;
}

async function openDetail(id, { updateUrl = true } = {}) {
  const row = classes.find((item) => item.id === id);
  if (!row) return;
  selectedId = id;
  if (updateUrl) history.pushState({}, "", `classes.html?id=${id}`);
  $("classDetailError").hidden = true;
  renderDetail(row);
  try {
    const fresh = await adminRequest(`/classes/${id}`);
    const index = classes.findIndex((item) => item.id === id);
    if (index >= 0) classes[index] = fresh;
    renderList();
    renderDetail(fresh);
  } catch (error) {
    $("classDetailError").textContent = error.message;
    $("classDetailError").hidden = false;
  }
}

function closeDetail() {
  selectedId = null;
  history.pushState({}, "", "classes.html");
  $("classDetail").hidden = true;
}

async function loadClasses() {
  $("classError").hidden = true;
  $("classRows").innerHTML = '<tr><td class="class-loading" colspan="6">正在加载班级…</td></tr>';
  try {
    const payload = await adminRequest("/classes");
    classes = payload.items || [];
    renderList();
    if (selectedId && classes.some((row) => row.id === selectedId)) {
      await openDetail(selectedId, { updateUrl: false });
    } else if (selectedId) {
      closeDetail();
    }
  } catch (error) {
    $("classRows").innerHTML = "";
    $("classErrorText").textContent = error.message;
    $("classError").hidden = false;
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
$("retryClasses").addEventListener("click", loadClasses);
$("closeDetail").addEventListener("click", closeDetail);
window.addEventListener("popstate", () => {
  const id = Number(new URLSearchParams(location.search).get("id")) || null;
  if (id) openDetail(id, { updateUrl: false });
  else closeDetail();
});

loadClasses().catch((error) => toast(error.message, "error"));
