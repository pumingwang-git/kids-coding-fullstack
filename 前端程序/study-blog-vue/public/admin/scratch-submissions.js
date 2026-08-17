// Scratch 学生作品只读列表（任务书 21c 固定功能范围 5）：
// 学生、挑战、最后提交、通过状态、提交次数、查看快照/反馈入口。
// 本页没有任何写操作；快照是提交时刻的不可变版本，不是学生当前工作副本。

import { initLayout } from "./admin-layout.js";
import { escapeHtml, toast } from "./admin-ui.js";
import { scratchRequest, scratchMockEnabled } from "./admin-scratch-api.js";
import { SUBMISSION_STATUS_LABEL, formatDateTime, studioPreviewBase, studioPreviewUrl } from "./admin-scratch-core.js";

initLayout();

const $ = (id) => document.getElementById(id);
const withMock = (url) => (scratchMockEnabled() ? `${url}${url.includes("?") ? "&" : "?"}scratch_mock=1` : url);

let page = 1;
const size = 20;
let total = 0;

// URL 携带 challenge_id（从挑战列表/内容块弹窗跳入）时直接过滤
const initialChallenge = new URLSearchParams(location.search).get("challenge_id") || "";

async function loadChallengeFilter() {
  try {
    const data = await scratchRequest("/scratch/challenges/options");
    $("sChallenge").innerHTML = `<option value="">全部挑战</option>${(data.items || [])
      .map((c) => `<option value="${c.id}" ${String(c.id) === initialChallenge ? "selected" : ""}>#${c.id} ${escapeHtml(c.title)}</option>`)
      .join("")}`;
  } catch (error) {
    // 过滤器加载失败不挡列表（列表仍可「全部挑战」查询），但要提示
    toast(`挑战列表加载失败：${error.message}`, "error");
  }
}

async function loadList() {
  $("errorTip").hidden = true;
  const params = new URLSearchParams({ page: String(page), page_size: String(size) });
  if ($("sChallenge").value) params.set("challenge_id", $("sChallenge").value);
  if ($("sStatus").value) params.set("status", $("sStatus").value);
  try {
    const data = await scratchRequest(`/scratch/submissions?${params}`);
    total = data.total || 0;
    renderRows(data.items || []);
  } catch (error) {
    $("submissionRows").innerHTML = "";
    $("emptyTip").hidden = true;
    $("errorText").textContent = error.message;
    $("errorTip").hidden = false;
  }
}

const STATUS_BADGE = { passed: "trial", evaluating: "warn", needs_review: "warn", returned: "warn", failed: "err" };

function renderRows(items) {
  $("emptyTip").hidden = items.length > 0;
  $("totalTip").textContent = `共 ${total} 条 · 第 ${page}/${Math.max(1, Math.ceil(total / size))} 页`;
  $("prevPageBtn").disabled = page <= 1;
  $("nextPageBtn").disabled = page * size >= total;
  $("submissionRows").innerHTML = items
    .map(
      (s) => `<tr>
      <td>${escapeHtml(s.student_name || `#${s.student_id}`)}</td>
      <td>${escapeHtml(s.challenge_title || `#${s.challenge_id}`)}</td>
      <td>${formatDateTime(s.submitted_at)}</td>
      <td><span class="node-badge ${STATUS_BADGE[s.status] || "warn"}">${SUBMISSION_STATUS_LABEL[s.status] || s.status}</span></td>
      <td>${s.attempt_count ?? 0}</td>
      <td>
        <button class="btn-text link" type="button" data-snapshot="${s.id}">快照与反馈</button>
        <button class="btn-text link" type="button" data-studio="${s.id}" data-challenge="${s.challenge_id}">Studio 只读查看</button>
      </td>
    </tr>`,
    )
    .join("");
}

$("searchBtn").addEventListener("click", () => {
  page = 1;
  loadList();
});
$("retryBtn").addEventListener("click", loadList);
$("prevPageBtn").addEventListener("click", () => {
  if (page > 1) {
    page -= 1;
    loadList();
  }
});
$("nextPageBtn").addEventListener("click", () => {
  if (page * size < total) {
    page += 1;
    loadList();
  }
});

function closeSnapshot() {
  $("snapshotMask").hidden = true;
}
$("snapshotClose").addEventListener("click", closeSnapshot);
$("snapshotOk").addEventListener("click", closeSnapshot);
$("snapshotMask").addEventListener("click", (e) => {
  if (e.target === $("snapshotMask")) closeSnapshot();
});

$("submissionRows").addEventListener("click", async (event) => {
  const snapshot = event.target.closest("[data-snapshot]");
  if (snapshot) {
    try {
      const s = await scratchRequest(`/scratch/submissions/${Number(snapshot.dataset.snapshot)}`);
      $("snapshotBody").innerHTML = `
        <div class="form-field"><label>学生 / 挑战</label><span>${escapeHtml(s.student_name || `#${s.student_id}`)} · ${escapeHtml(s.challenge_title || "")}</span></div>
        <div class="form-field"><label>快照版本</label><span>第 ${s.snapshot?.revision_no ?? "—"} 版 · 保存于 ${formatDateTime(s.snapshot?.saved_at)}</span></div>
        <div class="form-field"><label>内容指纹</label><span class="muted">${escapeHtml(s.snapshot?.content_hash || "—")} · ${s.snapshot?.size_bytes ?? "—"} 字节</span></div>
        <div class="form-field"><label>判定结果</label><span>${SUBMISSION_STATUS_LABEL[s.status] || s.status}${
          s.evaluation ? `（规则通过 ${s.evaluation.rules_passed}/${s.evaluation.rules_total}）` : ""
        }</span></div>
        <div class="form-field"><label>反馈</label><span>${escapeHtml(s.feedback || "暂无反馈。")}</span></div>`;
      $("snapshotMask").hidden = false;
    } catch (error) {
      toast(error.message, "error");
    }
    return;
  }
  const studio = event.target.closest("[data-studio]");
  if (studio) {
    // 在 Studio 中以管理员只读模式打开该次提交的快照；不写学生项目
    const url = studioPreviewUrl(Number(studio.dataset.challenge), {
      studioBase: studioPreviewBase(),
      extra: { submission_id: studio.dataset.studio }
    });
    window.open(withMock(url), "_blank", "noopener");
  }
});

(async () => {
  await loadChallengeFilter();
  await loadList();
})();
