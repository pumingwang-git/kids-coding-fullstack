import { adminRequest } from "./admin-api.js";
import { closeMask, escapeHtml, fmtTime, openMask, toast } from "./admin-ui.js";
import { initLayout } from "./admin-layout.js";

initLayout();

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 20;
const state = { box: "inbox", tab: "all", page: 1, total: 0, items: [] };
let revokeId = null;
let releaseRevokeFocus = null;

function actionList(item) {
  const actions = Array.isArray(item.actions) ? item.actions : (Array.isArray(item.allowed_actions) ? item.allowed_actions : []);
  return actions.filter((action) => action && typeof action.type === "string");
}

function actionFor(item, type) {
  return actionList(item).find((action) => action.type === type) || null;
}

function isRead(item) {
  return Boolean(item.read_at);
}

function isRevoked(item) {
  return Boolean(item.revoked_at || item.revoked);
}

function setBusy(busy) {
  $("notificationsList").setAttribute("aria-busy", String(busy));
  $("filterForm").querySelectorAll("button, select").forEach((element) => { element.disabled = busy; });
  $("readAllBtn").disabled = busy || state.box !== "inbox" || state.tab !== "all";
}

function renderTabs() {
  const inbox = state.box === "inbox";
  $("inboxTab").setAttribute("aria-selected", String(inbox));
  $("sentTab").setAttribute("aria-selected", String(!inbox));
  $("readFilterLabel").hidden = !inbox;
  $("readFilter").hidden = !inbox;
  $("readFilter").value = state.tab;
  $("readAllBtn").hidden = !inbox;
}

function itemActions(item) {
  const links = [];
  if (item.link_url && !isRevoked(item)) links.push('<button class="btn-text" type="button" data-open="true">查看</button>');
  if (!isRead(item) && state.box === "inbox") links.push('<button class="btn-text" type="button" data-read="true">标为已读</button>');
  const revoke = actionFor(item, "revoke");
  if (revoke && !isRevoked(item)) links.push(`<button class="btn-text" type="button" data-revoke="true">${escapeHtml(revoke.label || "撤回")}</button>`);
  return links.join("");
}

function renderList() {
  const host = $("notificationsList");
  if (!state.items.length) {
    host.innerHTML = '<div class="notification-state"><div><strong>没有可显示的通知</strong><p>当前筛选范围内没有需要处理的记录。</p></div></div>';
    renderFooter(0);
    return;
  }
  host.innerHTML = state.items.map((item) => {
    const classes = `${isRead(item) ? " is-read" : ""}${isRevoked(item) ? " is-revoked" : ""}`;
    const meta = [item.kind_label, fmtTime(item.created_at), isRevoked(item) ? fmtTime(item.revoked_at) : null].filter(Boolean);
    return `<article class="notification-row${classes}" data-id="${escapeHtml(item.id)}"><span class="notification-dot" aria-hidden="true"></span><div class="notification-copy"><h3 class="notification-title">${escapeHtml(item.title || "")}</h3>${item.body ? `<p class="notification-body">${escapeHtml(item.body)}</p>` : ""}<div class="notification-meta">${meta.map((text) => `<span>${escapeHtml(text)}</span>`).join("<span aria-hidden=\"true\">·</span>")}</div></div><div class="notification-row-actions">${itemActions(item)}</div></article>`;
  }).join("");
  renderFooter(state.items.length);
}

function renderFooter(shown) {
  const pages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
  const start = state.total ? (state.page - 1) * PAGE_SIZE + 1 : 0;
  const end = start ? start + shown - 1 : 0;
  $("notificationsFooter").innerHTML = `<span>${state.total ? `显示 ${start}–${end} / 共 ${state.total} 条` : ""}</span><span class="spacer"></span><button class="btn" type="button" data-page="prev"${state.page === 1 ? " disabled" : ""}>上一页</button><button class="btn" type="button" data-page="next"${state.page >= pages ? " disabled" : ""}>下一页</button>`;
}

function renderLoading() {
  $("notificationsList").innerHTML = '<div class="notification-state"><div class="notification-skeleton" aria-label="正在加载通知"><span></span><span></span><span></span><span></span></div></div>';
  $("notificationsFooter").replaceChildren();
}

function renderError(error) {
  $("notificationsList").innerHTML = `<div class="notification-state"><div><strong>通知加载失败</strong><p>${escapeHtml(error.message || "请稍后重试。")}</p><button class="btn" id="listRetry" type="button">重新加载</button></div></div>`;
  $("notificationsFooter").replaceChildren();
}

async function loadNotifications() {
  setBusy(true);
  renderLoading();
  try {
    const params = new URLSearchParams({ box: state.box, tab: state.tab, page: String(state.page), page_size: String(PAGE_SIZE) });
    const payload = await adminRequest(`/notifications?${params}`);
    state.items = payload.items || [];
    state.total = Number(payload.total || 0);
    renderList();
  } catch (error) {
    renderError(error);
  } finally {
    setBusy(false);
  }
}

function safeNavigate(linkUrl) {
  try {
    const destination = new URL(linkUrl, location.origin);
    if (destination.origin !== location.origin || !destination.pathname.startsWith("/")) throw new Error("unsafe");
    location.assign(`${destination.pathname}${destination.search}${destination.hash}`);
  } catch {
    toast("通知跳转地址不可用。", "error");
  }
}

async function markRead(item) {
  const button = document.activeElement;
  button.disabled = true;
  try {
    await adminRequest(`/notifications/${encodeURIComponent(item.id)}/read`, { method: "POST", body: "{}" });
    item.read_at = new Date().toISOString();
    renderList();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function markAllRead() {
  $("readAllBtn").disabled = true;
  try {
    await adminRequest("/notifications/read-all", { method: "POST", body: "{}" });
    state.items.forEach((item) => { item.read_at = item.read_at || new Date().toISOString(); });
    renderList();
    toast("已标记当前收件箱通知为已读。");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(false);
  }
}

function closeRevoke() {
  closeMask($("revokeMask"), releaseRevokeFocus);
  releaseRevokeFocus = null;
  revokeId = null;
  $("revokeError").hidden = true;
}

function openRevoke(id) {
  revokeId = id;
  releaseRevokeFocus = openMask($("revokeMask"), { focusSelector: "#revokeConfirm" });
}

async function revoke() {
  if (revokeId == null) return;
  const button = $("revokeConfirm");
  button.disabled = true;
  $("revokeError").hidden = true;
  try {
    await adminRequest(`/notifications/${encodeURIComponent(revokeId)}/revoke`, { method: "POST", body: "{}" });
    closeRevoke();
    await loadNotifications();
    toast("通知已撤回。");
  } catch (error) {
    $("revokeError").textContent = error.message || "撤回失败，请重试。";
    $("revokeError").hidden = false;
  } finally {
    button.disabled = false;
  }
}

$("inboxTab").addEventListener("click", () => { state.box = "inbox"; state.tab = "all"; state.page = 1; renderTabs(); loadNotifications(); });
$("sentTab").addEventListener("click", () => { state.box = "sent"; state.tab = "all"; state.page = 1; renderTabs(); loadNotifications(); });
$("filterForm").addEventListener("submit", (event) => { event.preventDefault(); state.tab = $("readFilter").value; state.page = 1; loadNotifications(); });
$("readAllBtn").addEventListener("click", markAllRead);
$("notificationsList").addEventListener("click", (event) => {
  const row = event.target.closest("[data-id]");
  if (!row) return;
  const item = state.items.find((candidate) => String(candidate.id) === row.dataset.id);
  if (!item) return;
  if (event.target.closest("[data-open]")) safeNavigate(item.link_url);
  if (event.target.closest("[data-read]")) markRead(item);
  if (event.target.closest("[data-revoke]")) openRevoke(item.id);
});
$("notificationsFooter").addEventListener("click", (event) => {
  const direction = event.target.dataset.page;
  if (!direction) return;
  state.page += direction === "next" ? 1 : -1;
  loadNotifications();
});
$("notificationsList").addEventListener("click", (event) => { if (event.target.id === "listRetry") loadNotifications(); });
$("revokeClose").addEventListener("click", closeRevoke);
$("revokeCancel").addEventListener("click", closeRevoke);
$("revokeConfirm").addEventListener("click", revoke);
$("revokeMask").addEventListener("click", (event) => { if (event.target === $("revokeMask")) closeRevoke(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && $("revokeMask").classList.contains("show")) closeRevoke(); });

renderTabs();
loadNotifications();
