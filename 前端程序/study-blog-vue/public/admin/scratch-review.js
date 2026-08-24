// Scratch 教师批改台：队列（latest_only 待点评）→ 看作品 → 量规打分 → 给终态 / 退回重做。
// 只读档案（scratch-submissions.html）保留，这里才是写操作入口。
//
// 契约要点（与后端 admin_scratch.py 对齐）：
// - 队列 `GET /scratch/submissions?status=needs_review&latest_only=true`
// - 详情 `GET /scratch/submissions/{id}`（含 rubric=当前量规、review=已批改结果、scripts_url）
// - 通过/不通过 `POST /scratch/submissions/{id}/review`，退回 `POST .../return`（comment 必填）
// - 有量规的挑战 rubric 必须覆盖全部准则；无量规则必须为空（后端各做一次 400 兜底）。

import { initLayout } from "./admin-layout.js";
import { escapeHtml, toast } from "./admin-ui.js";
import { scratchRequest, scratchMockEnabled } from "./admin-scratch-api.js";
import {
  SUBMISSION_STATUS_LABEL,
  formatDateTime,
  studioPreviewBase,
  studioReviewUrl,
} from "./admin-scratch-core.js";

initLayout();

const $ = (id) => document.getElementById(id);
const withMock = (url) => (scratchMockEnabled() ? `${url}${url.includes("?") ? "&" : "?"}scratch_mock=1` : url);

let queue = [];
let currentIndex = -1;
let current = null;   // 当前选中提交的详情
let rubric = null;    // 当前挑战的量规（parsed）
let scores = {};      // { [criterion_id]: { level, note } }

// ---------- 队列 ----------

async function loadChallengeFilter() {
  try {
    const data = await scratchRequest("/scratch/challenges/options");
    $("sChallenge").innerHTML = `<option value="">全部挑战</option>${(data.items || [])
      .map((c) => `<option value="${c.id}">#${c.id} ${escapeHtml(c.title)}</option>`)
      .join("")}`;
  } catch (error) {
    toast(`挑战列表加载失败：${error.message}`, "error");
  }
}

async function loadQueue() {
  $("queueError").hidden = true;
  const params = new URLSearchParams({ status: "needs_review", latest_only: "true", page_size: "50" });
  if ($("sChallenge").value) params.set("challenge_id", $("sChallenge").value);
  try {
    const data = await scratchRequest(`/scratch/submissions?${params}`);
    queue = data.items || [];
    renderQueue();
    if (queue.length) {
      await select(0);
    } else {
      clearWorkspace();
    }
  } catch (error) {
    $("queueList").innerHTML = "";
    $("queueEmpty").hidden = true;
    $("queueErrorText").textContent = error.message;
    $("queueError").hidden = false;
  }
}

function renderQueue() {
  $("queueCount").textContent = `${queue.length} 条`;
  $("queueEmpty").hidden = queue.length > 0;
  $("queueList").innerHTML = queue
    .map(
      (s, i) => `<li class="queue-item${i === currentIndex ? " active" : ""}" data-index="${i}" role="button" tabindex="0">
        <div class="q-title"><span>${escapeHtml(s.student_name || `#${s.student_id}`)} <small>#${s.attempt_count}</small></span><span class="node-badge ${STATUS_BADGE(s.status)}">${SUBMISSION_STATUS_LABEL[s.status] || s.status}</span></div>
        <div class="q-meta">${escapeHtml(s.challenge_title || "")} · ${formatDateTime(s.submitted_at)}</div>
      </li>`,
    )
    .join("");
}

function STATUS_BADGE(status) {
  return { passed: "trial", failed: "err", needs_review: "warn", returned: "warn" }[status] || "warn";
}

// ---------- 选中与工作区 ----------

async function select(i) {
  if (i < 0 || i >= queue.length) return;
  currentIndex = i;
  const s = queue[i];
  try {
    current = await scratchRequest(`/scratch/submissions/${s.id}`);
    rubric = current.rubric && Array.isArray(current.rubric.criteria) ? current.rubric : null;
    resetScoring();
    renderQueue();
    renderWork();
    renderScoring();
  } catch (error) {
    toast(error.message, "error");
  }
}

function clearWorkspace() {
  current = null;
  rubric = null;
  scores = {};
  $("workBody").innerHTML = '<p class="muted">队列为空，或尚未选中提交。</p>';
  $("rubricArea").innerHTML = "";
  $("scoreTotal").textContent = "";
  $("comment").value = "";
  $("incompleteTip").textContent = "";
  setActionButtonsDisabled(true);
}

function renderWork() {
  if (!current) return;
  const snap = current.snapshot || {};
  const evaln = current.evaluation || {};
  const missing = (evaln.missing || []).map((m) => `<div class="eval-line bad">${escapeHtml(m)}</div>`).join("");
  const passed = evaln.rules_total ? `<div class="eval-line ok">自动判定 ${evaln.rules_passed}/${evaln.rules_total} 项通过</div>` : "";
  const unsupported = (evaln.unsupported || []).length
    ? `<div class="muted">含需人工确认的规则：${escapeHtml((evaln.unsupported || []).join("、"))}</div>`
    : "";
  $("workBody").innerHTML = `
    <div class="work-block">
      <div class="work-meta">
        <div class="kv"><label>学生</label><span>${escapeHtml(current.student_name || `#${current.student_id}`)}</span></div>
        <div class="kv"><label>挑战</label><span>${escapeHtml(current.challenge_title || `#${current.challenge_id}`)}</span></div>
        <div class="kv"><label>课时 / 块</label><span>${escapeHtml(current.lesson_title || "")} · ${escapeHtml(current.block_title || "")}</span></div>
        <div class="kv"><label>第几次提交</label><span>#${current.attempt_count}</span></div>
        <div class="kv"><label>提交时间</label><span>${formatDateTime(current.submitted_at)}</span></div>
        <div class="kv"><label>当前状态</label><span><span class="node-badge ${STATUS_BADGE(current.status)}">${SUBMISSION_STATUS_LABEL[current.status] || current.status}</span></span></div>
      </div>
    </div>
    <div class="work-block">
      <h3>提交快照（判定证据）</h3>
      <div class="snapshot-line">第 ${snap.revision_no ?? "—"} 版 · sha256:${escapeHtml(String(snap.content_hash || "—").replace(/^sha256:/, "").slice(0, 8))} · ${formatDateTime(snap.saved_at)} · ${snap.size_bytes ?? "—"} 字节</div>
    </div>
    <div class="work-block">
      <h3>自动判定</h3>
      ${passed}${missing}${unsupported || '<div class="muted">无逐条判定结论。</div>'}
    </div>
    <div class="work-block">
      <h3>脚本</h3>
      <div class="scripts-empty" id="scriptsBox">积木图将在后续版本接入（P2），当前请在 Studio 中查看脚本。</div>
    </div>`;
  $("studioOpen").disabled = false;
  $("downloadSb3").href = snap.download_url || "#";
}

// ---------- 打分 ----------

function resetScoring() {
  scores = {};
  if (current?.review?.items) {
    for (const item of current.review.items) {
      scores[item.criterion_id] = { level: item.level, note: item.note || "" };
    }
  }
  $("comment").value = current?.review?.comment || "";
}

function hasRubric() {
  return Boolean(rubric && Array.isArray(rubric.criteria) && rubric.criteria.length);
}

function incompleteCount() {
  if (!hasRubric()) return 0;
  return rubric.criteria.filter((c) => scores[c.id]?.level == null).length;
}

function renderScoring() {
  if (!current) return;
  const area = $("rubricArea");
  if (!hasRubric()) {
    area.innerHTML = '<p class="muted">本关未配置量规，只需通过 / 不通过 + 总评。</p>';
  } else {
    area.innerHTML = rubric.criteria
      .map((c, ci) => {
        const levels = (c.levels || [])
          .map(
            (lvl) => `<label class="rubric-level"><input type="radio" name="crit_${ci}" value="${lvl.value}" data-criterion="${escapeHtml(c.id)}" ${scores[c.id]?.level === lvl.value ? "checked" : ""} /> <span>${escapeHtml(lvl.label)}</span><em>${lvl.points} 分</em></label>`,
          )
          .join("");
        return `<div class="rubric-criterion">
          <div class="rubric-criterion-head"><strong>${escapeHtml(c.label)}</strong>${c.desc ? `<span class="muted">${escapeHtml(c.desc)}</span>` : ""}</div>
          <div class="rubric-levels">${levels}</div>
          <textarea class="rubric-note" rows="2" data-note-for="${escapeHtml(c.id)}" placeholder="逐项评语（可选）">${escapeHtml(scores[c.id]?.note || "")}</textarea>
        </div>`;
      })
      .join("");
  }
  updateTotal();
}

function updateTotal() {
  if (!hasRubric()) {
    $("scoreTotal").textContent = "";
    $("incompleteTip").textContent = "";
    setActionButtonsDisabled(false);
    return;
  }
  const total = rubric.criteria.reduce((sum, c) => {
    const lvl = (c.levels || []).find((l) => l.value === scores[c.id]?.level);
    return sum + (lvl ? lvl.points : 0);
  }, 0);
  $("scoreTotal").innerHTML = `${total} <span class="max">/ ${rubric.max_score ?? 0}</span>`;
  const left = incompleteCount();
  $("incompleteTip").textContent = left ? `还有 ${left} 项未评` : "";
  setActionButtonsDisabled(left > 0);
}

function setActionButtonsDisabled(disabled) {
  $("btnPass").disabled = disabled;
  $("btnFail").disabled = disabled;
  $("btnReturn").disabled = disabled;
}

function buildRubricItems() {
  if (!hasRubric()) return [];
  return rubric.criteria.map((c) => ({
    criterion_id: c.id,
    level: scores[c.id]?.level,
    note: scores[c.id]?.note || "",
  }));
}

async function doAction(kind) {
  if (!current) return;
  const comment = $("comment").value.trim();
  const items = buildRubricItems();

  if (kind === "returned" && !comment) {
    $("comment").classList.add("input-invalid");
    $("comment").focus();
    toast("退回重做必须写清楚要改什么。", "error");
    return;
  }
  if (incompleteCount() > 0) {
    toast(`还有 ${incompleteCount()} 项量规未评。`, "error");
    return;
  }

  const body = kind === "returned"
    ? { comment, rubric: items }
    : { verdict: kind, comment, rubric: items };

  $("btnPass").disabled = $("btnFail").disabled = $("btnReturn").disabled = true;
  try {
    const path = kind === "returned"
      ? `/scratch/submissions/${current.id}/return`
      : `/scratch/submissions/${current.id}/review`;
    const result = await scratchRequest(path, { method: "POST", body: JSON.stringify(body),
      headers: { "Idempotency-Key": crypto.randomUUID() } });
    const verdictText = { passed: "通过", failed: "不通过", returned: "退回重做" }[kind];
    toast(`已${verdictText}：${escapeHtml(current.student_name || "")} 的提交。`);
    if (kind === "passed" && result?.completed) {
      toast("已写入课时完成进度。");
    }
    // 从队列移除并前进到下一条
    queue.splice(currentIndex, 1);
    if (queue.length) {
      await select(Math.min(currentIndex, queue.length - 1));
    } else {
      clearWorkspace();
      renderQueue();
    }
  } catch (error) {
    toast(error.message, "error");
    updateTotal();
  }
}

// ---------- 事件 ----------

$("searchBtn").addEventListener("click", loadQueue);
$("refreshBtn").addEventListener("click", loadQueue);
$("sChallenge").addEventListener("change", loadQueue);

$("queueList").addEventListener("click", (event) => {
  const item = event.target.closest("[data-index]");
  if (item) select(Number(item.dataset.index));
});

$("studioOpen").addEventListener("click", () => {
  if (current) window.open(withMock(studioReviewUrl(current.id)), "_blank", "noopener");
});

$("btnPass").addEventListener("click", () => doAction("passed"));
$("btnFail").addEventListener("click", () => doAction("failed"));
$("btnReturn").addEventListener("click", () => doAction("returned"));

$("comment").addEventListener("input", () => $("comment").classList.remove("input-invalid"));

// 量规 radio / 评语变更 → 同步 scores
$("rubricArea").addEventListener("change", (event) => {
  const radio = event.target.closest("input[type=radio][data-criterion]");
  if (radio) {
    const cid = radio.dataset.criterion;
    scores[cid] = { ...(scores[cid] || {}), level: Number(radio.value) };
    updateTotal();
  }
});
$("rubricArea").addEventListener("input", (event) => {
  const note = event.target.closest("[data-note-for]");
  if (note) {
    const cid = note.dataset.noteFor;
    scores[cid] = { ...(scores[cid] || {}), note: note.value };
  }
});

// 键盘：J/K 切上下条；Ctrl+Enter 通过当前条。焦点在输入框里时 J/K 不劫持。
document.addEventListener("keydown", (event) => {
  const tag = (event.target.tagName || "").toLowerCase();
  const typing = tag === "input" || tag === "textarea" || tag === "select";
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    doAction("passed");
    return;
  }
  if (typing) return;
  if (event.key === "j" || event.key === "J") {
    event.preventDefault();
    if (currentIndex + 1 < queue.length) select(currentIndex + 1);
  } else if (event.key === "k" || event.key === "K") {
    event.preventDefault();
    if (currentIndex - 1 >= 0) select(currentIndex - 1);
  }
});

(async () => {
  clearWorkspace();
  await loadChallengeFilter();
  await loadQueue();
})();
