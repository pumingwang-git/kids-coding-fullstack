import { adminMe, adminRequest } from "./admin-api.js";
import { escapeHtml, fmtTime } from "./admin-ui.js";
import { initLayout } from "./admin-layout.js";

initLayout();
const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 20;
let page = 1;
let total = 0;
let dicts = null;

function optionMarkup(items, valueKey = "machine_name", labelKey = "display_name") {
  return items.map((item) => `<option value="${escapeHtml(item[valueKey])}">${escapeHtml(item[labelKey])}</option>`).join("");
}

function queryParams() {
  const values = {
    event_type: $("eventType").value,
    outcome: $("outcome").value,
    admin_user_id: $("adminUserId").value,
    user_id: $("userId").value,
    resource_type: $("resourceType").value.trim(),
    resource_id: $("resourceId").value,
    created_from: $("createdFrom").value,
    created_to: $("createdTo").value,
    page,
    page_size: PAGE_SIZE,
  };
  return Object.entries(values).filter(([, value]) => value !== "").map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join("&");
}

function personCell(id, person, label) {
  if (id == null) return '<span class="muted">—</span>';
  const name = person?.display_name || person?.username || label;
  return `<span class="audit-person"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(label)} #${escapeHtml(String(id))}</small></span>`;
}

function renderRows(items) {
  $("auditRows").innerHTML = items.map((item) => {
    const event = dicts.event_types.find((option) => option.machine_name === item.event_type);
    const outcome = dicts.outcomes.find((option) => option.machine_name === item.outcome);
    const summary = JSON.stringify(item.summary || {}, null, 2);
    return `<tr>
      <td>${escapeHtml(fmtTime(item.created_at))}</td>
      <td><span class="audit-event"><strong>${escapeHtml(event?.display_name || item.event_type)}</strong><code>${escapeHtml(item.event_type)}</code></span></td>
      <td><span class="tag ${escapeHtml(outcome?.tone || "")}">${escapeHtml(outcome?.display_name || item.outcome)}</span></td>
      <td>${personCell(item.admin_user_id, item.admin_user, "后台账号")}</td>
      <td>${personCell(item.user_id, item.user, "学员账号")}</td>
      <td>${item.resource_type ? `<span class="audit-resource"><strong>${escapeHtml(item.resource_type)}</strong>${item.resource_id == null ? "" : `<small>#${escapeHtml(String(item.resource_id))}</small>`}</span>` : '<span class="muted">—</span>'}</td>
      <td><details class="audit-summary"><summary>查看</summary><pre>${escapeHtml(summary)}</pre></details></td>
    </tr>`;
  }).join("");
  $("emptyTip").hidden = items.length > 0;
}

async function loadDicts() {
  dicts = await adminRequest("/dicts");
  $("eventType").insertAdjacentHTML("beforeend", optionMarkup(dicts.event_types));
  $("outcome").insertAdjacentHTML("beforeend", optionMarkup(dicts.outcomes));
}

async function loadEvents() {
  $("errorTip").hidden = true;
  $("listMeta").textContent = "加载中";
  try {
    const data = await adminRequest(`/audit/events?${queryParams()}`);
    total = Number(data.total || 0);
    renderRows(data.items || []);
    $("listMeta").textContent = `共 ${total} 条记录`;
    $("pageMeta").textContent = `第 ${page} 页 / 共 ${Math.max(1, Math.ceil(total / PAGE_SIZE))} 页`;
    $("prevBtn").disabled = page <= 1;
    $("nextBtn").disabled = page * PAGE_SIZE >= total;
  } catch (error) {
    $("auditRows").innerHTML = "";
    $("emptyTip").hidden = true;
    $("errorText").textContent = error.message;
    $("errorTip").hidden = false;
  }
}

async function boot() {
  try {
    await adminMe();
    await loadDicts();
    await loadEvents();
  } catch (error) {
    $("errorText").textContent = error.message;
    $("errorTip").hidden = false;
  }
}

$("filterForm").addEventListener("submit", (event) => { event.preventDefault(); page = 1; loadEvents(); });
$("clearBtn").addEventListener("click", () => { $("filterForm").reset(); page = 1; loadEvents(); });
$("refreshBtn").addEventListener("click", loadEvents);
$("retryBtn").addEventListener("click", loadEvents);
$("prevBtn").addEventListener("click", () => { if (page > 1) { page -= 1; loadEvents(); } });
$("nextBtn").addEventListener("click", () => { if (page * PAGE_SIZE < total) { page += 1; loadEvents(); } });
boot();
