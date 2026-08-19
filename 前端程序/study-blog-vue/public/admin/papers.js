// 试卷管理页：列表 + 组卷 Modal + 整卷预览。
//
// 两层模型（见《3、后台试卷-组卷模块》第二节）：
//   试卷 = 内容（题目/分值/判分口径）  链接 = 一次考试安排（名称/时间/次数/呈现）
// 一张卷可有多条链接，所以列表列的是「链接数」而不是单一时间窗口。
// 链接的增删改查在 exam-links.html（《4、后台考试链接-管理模块》），本页只放跳转入口——
// 同一套规则不能存两份实现。
//
// ⚠️ 安全红线：选题只能调 GET /problems/pickable（已裁剪答案的只读端点）。
// 绝不能改成 GET /problems/{id} —— 那个接口返回完整答案、解析与参考代码，
// 一旦用在组卷面板就等于把正确答案发进了学员也能打开的浏览器。
// 需要展示更多题干内容时，请找后端扩展 pickable 的返回字段，不要换接口。

import { initLayout } from "./admin-layout.js";
import { adminRequest, ifMatch } from "./admin-api.js";
import { createPagedList } from "./admin-list.js";
import { applyPreset, PAPER_PRESETS } from "./paper-presets.js";
import { closeMask, confirmDialog, escapeHtml, isMaskOpen, openMask, toast, trapFocus } from "./admin-ui.js";
import { renderMarkdown } from "./admin-markdown.js";

initLayout();

const TYPE_LABEL = { choice: "选择", multi_choice: "多选", judge: "判断", fill: "填空", programming: "操作题" };
const STATUS_LABEL = { draft: ["草稿", "warn"], published: ["已发布", ""], archived: ["已归档", "gray"] };
const SUBJECT_LABEL = { cpp: "C++", python: "Python", scratch: "Scratch", general: "通用" };
const DIFFICULTIES = ["入门", "普及-", "普及/提高-", "普及+/提高", "提高+/省选-", "省选/NOI-", "NOI/NOI+/CTSC"];

const $ = (id) => document.getElementById(id);

// ==================== 胶囊单选组：与题库录入界面同一套视觉语言 ====================
function renderPills(container, name, options, value) {
  container.innerHTML = options
    .map(
      ([val, label]) => `<label class="pill"><input type="radio" name="${name}" value="${escapeHtml(String(val))}"${
        String(val) === String(value) ? " checked" : ""
      } /><span>${escapeHtml(label)}</span></label>`,
    )
    .join("");
}
// 小圆圈单选组：组卷左栏属性专用（rdot），比胶囊轻、适合窄面板纵向扫读。
// 胶囊（renderPills）本页还用于整卷预览的卷别切换；考试链接页（exam-links.js）也在用。
function renderDots(container, name, options, value) {
  container.innerHTML = options
    .map(
      ([val, label]) => `<label class="rdot"><input type="radio" name="${name}" value="${escapeHtml(String(val))}"${
        String(val) === String(value) ? " checked" : ""
      } /><span class="dot"></span><span class="txt">${escapeHtml(label)}</span></label>`,
    )
    .join("");
}
const pillValue = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value ?? "";

// ==================== 试卷列表 ====================
// 默认停在「已发布」：日常进这页是找能用的卷，草稿是少数人的工作台。
let zone = "published";
const rows = $("paperRows");

function questionTypes(paper) {
  const entries = Object.entries(paper.question_types || {});
  if (!entries.length) return '<span class="muted">—</span>';
  return entries.map(([type, count]) => `${escapeHtml(TYPE_LABEL[type] || type)} ${count}`).join(" · ");
}

function linkCell(paper) {
  if (!paper.link_count) return '<span class="muted">—</span>';
  const inactive = paper.link_count - (paper.active_link_count || 0);
  const suffix = inactive ? ` <span class="muted">(${inactive} 停用)</span>` : "";
  return `${paper.active_link_count || 0} 条${suffix}`;
}

function renderPaperRows(items) {
  rows.innerHTML = items
    .map((paper) => {
      const allowed = new Set(paper.allowed_actions || []);
      const actions = [
        allowed.has("edit")
          ? `<button class="btn-text link" type="button" data-edit="${paper.id}">编辑</button>`
          : `<button class="btn-text link" type="button" data-view="${paper.id}">查看</button>`,
        // 整卷预览：能看卷就能预览（view 在 allowed_actions 里与「查看」同源）。
        allowed.has("view")
          ? `<button class="btn-text link" type="button" data-preview="${paper.id}">预览整卷</button>`
          : "",
        // 「考试链接」只在已发布卷上出现：草稿没有可考内容，归档卷已锁定。
        // 用 <a> 而不是 button + location.href：中键新开标签是这个场景的常见动作
        // （一边看卷一边配链接），按钮会把这个能力吃掉。
        allowed.has("manage_links")
          ? `<a class="btn-text link" href="exam-links.html?paper_id=${paper.id}">考试链接</a>`
          : "",
        allowed.has("manage_links")
          ? `<button class="btn-text link" type="button" data-assignments="${paper.id}">名单</button>`
          : "",
        allowed.has("publish") ? `<button class="btn-text link" type="button" data-publish="${paper.id}">发布</button>` : "",
        allowed.has("archive") ? `<button class="btn-text link danger" type="button" data-archive="${paper.id}">归档</button>` : "",
        allowed.has("delete") ? `<button class="btn-text link danger" type="button" data-delete="${paper.id}">删除</button>` : "",
      ].join("");
      const status = STATUS_LABEL[paper.status] || [paper.status, "gray"];
      return `
      <tr data-row="${paper.id}">
        <td>${escapeHtml(paper.paper_id_no || "—")}</td>
        <td class="cell-clip" title="${escapeHtml(paper.title)}">${escapeHtml(paper.title)}</td>
        <td><span class="tag">${escapeHtml(paper.paper_type)}</span></td>
        <td>${escapeHtml(SUBJECT_LABEL[paper.subject] || paper.subject)}</td>
        <td>${escapeHtml(paper.ruleset || "—")}</td>
        <td>${questionTypes(paper)}</td>
        <td>${paper.total_score}</td>
        <td>${linkCell(paper)}</td>
        <td><span class="tag ${status[1]}">${status[0]}</span></td>
        <td><div class="row-actions">${actions}</div></td>
      </tr>`;
    })
    .join("");
}

const list = createPagedList({
  els: {
    rows,
    emptyTip: $("emptyTip"),
    errorTip: $("errorTip"),
    errorText: $("errorText"),
    totalTip: $("totalTip"),
    prevBtn: $("prevPageBtn"),
    nextBtn: $("nextPageBtn"),
    retryBtn: $("retryBtn"),
    pageSizeSelect: $("pageSize"),
  },
  skeletonCols: 10,
  fetchPage: ({ page, size }) => {
    const params = new URLSearchParams({ status: zone, page, size });
    const keyword = $("sKeyword").value.trim();
    if (keyword) params.set("keyword", keyword);
    for (const [id, key] of [["sType", "paper_type"], ["sSubject", "subject"], ["sOwner", "owner_id"]]) {
      const value = $(id).value;
      if (value) params.set(key, value);
    }
    return adminRequest(`/papers?${params}`);
  },
  renderRows: renderPaperRows,
  onLoaded: refreshCounts,
});

async function refreshCounts() {
  try {
    const { counts } = await adminRequest("/paper-status-counts");
    for (const [key, id] of [["draft", "draftCount"], ["published", "publishedCount"], ["archived", "archivedCount"]]) {
      $(id).textContent = counts[key] ?? 0;
    }
  } catch {
    /* 计数失败不该拖垮列表本身 */
  }
}

// ==================== 组卷 Modal ====================
const composeMask = $("composeMask");
let paperState = null;
let selected = []; // [{problem_id_no, score, title, type, missing}]
let editingId = null;
let editingRevision = null;
let editingStatus = null; // null=新建；否则 draft / published / archived
let readOnly = false;
let snapshotAtOpen = "";
let releaseCompose = null;

const emptyPaper = () => ({
  title: "", description: "", paper_type: "练习卷", subject: "cpp", ruleset: "IOI",
  score_mode: "testcase", partial_credit_multi: false, pass_score: null,
});
const snapshot = () => JSON.stringify({ paperState, selected });
const totalScore = () => selected.reduce((sum, item) => sum + (Number(item.score) || 0), 0);

// 及格分 vs 总分：超过即时标红提示。草稿允许保存（与后端语义一致），发布时才拦（见 savePaper）。
// 触发点：改及格分 / 加删题 / 改分值——总分降了，原本合法的及格分也会变非法。
function refreshPassScoreWarn() {
  const raw = $("pPassScore").value;
  const over = raw !== "" && Number(raw) > totalScore();
  $("passScoreWarn").hidden = !over;
  if (over) $("passScoreWarn").textContent = `及格分超过当前总分（${totalScore()} 分）`;
  $("pPassScore").classList.toggle("input-invalid", over);
}

// 只重绘「预设管得到」的单选组（类型/学科/赛制/计分）+ 刷新只读禁用。
// 名称/说明/半分勾选/及格分是用户自由输入，这里绝不回写——
// 否则切换预设时会把用户已敲进去的内容覆盖成旧值。
// 自由输入通过 input/change 监听实时回写 paperState（见下方事件绑定），
// 所以单选组从 paperState 重绘永远是准的。
function renderComposeAttrs() {
  renderDots($("pTypeGroup"), "pType", PAPER_PRESETS.map((p) => [p.paper_type, p.paper_type]), paperState.paper_type);
  renderDots($("pSubjectGroup"), "pSubject", Object.entries(SUBJECT_LABEL), paperState.subject);
  renderDots($("pRulesetGroup"), "pRuleset", [["IOI", "IOI"], ["ACM", "ACM"], ["OI", "OI"], ["custom", "自定义"]], paperState.ruleset);
  renderDots($("pScoreModeGroup"), "pScoreMode", [["testcase", "按测试点部分分"], ["all_or_nothing", "全对得分"]], paperState.score_mode);
  for (const el of composeMask.querySelectorAll("input, textarea, button")) {
    // 只读「查看」态下仍放行「预览整卷」：预览的是已落库内容，不算编辑动作。
    if (el.id !== "composeClose" && el.id !== "composeCancel" && el.id !== "openPreviewBtn") el.disabled = readOnly;
  }
}

// 底栏按钮跟着试卷状态走，理由与列表行操作同源：后端 allowed_actions 里，
// published 卷根本没有 publish 这个动作。若照旧摆出「保存并发布」，点下去会先 PUT 成功
// （改动已落库）、再被 publish 挡回 403，用户看到的是「提示没权限、改动却保留了」的假失败。
function renderComposeFooter() {
  const published = editingStatus === "published";
  $("saveBtn").textContent = published ? "保存修改" : "保存草稿";
  $("saveBtn").classList.toggle("primary", published);
  $("saveBtn").hidden = readOnly;
  $("publishBtn").hidden = readOnly || published;
  $("composeHint").textContent = published ? "已发布卷：保存后立即对已分发的考试链接生效，并会重新过一遍发布校验。" : "";
}

function renderSelected() {
  $("selectedEmpty").hidden = selected.length > 0;
  $("selectedRows").innerHTML = selected
    .map((item, index) => {
      const bad = item.missing
        ? '<span class="tag danger">⚠ 题号不存在或未过审</span>'
        : `${escapeHtml(item.title || "")}`;
      return `
      <tr data-index="${index}">
        <td>${index + 1}</td>
        <td>${escapeHtml(item.problem_id_no)}</td>
        <td class="cell-clip" title="${escapeHtml(item.title || "")}">${bad}</td>
        <td>${escapeHtml(TYPE_LABEL[item.type] || "—")}</td>
        <td><input class="score-input" type="number" min="1" value="${item.score}" data-score="${index}" ${readOnly ? "disabled" : ""} /></td>
        <td><div class="row-actions">
          <span class="drag-grip${readOnly ? " disabled" : ""}" title="按住拖拽排序" aria-label="拖拽排序 ${escapeHtml(item.problem_id_no)}">⠿</span>
          <button class="btn-text link" type="button" data-up="${index}" aria-label="上移 ${escapeHtml(item.problem_id_no)}" ${readOnly || index === 0 ? "disabled" : ""}>↑</button>
          <button class="btn-text link" type="button" data-down="${index}" aria-label="下移 ${escapeHtml(item.problem_id_no)}" ${readOnly || index === selected.length - 1 ? "disabled" : ""}>↓</button>
          <button class="btn-text link danger" type="button" data-remove="${index}" aria-label="删除 ${escapeHtml(item.problem_id_no)}" ${readOnly ? "disabled" : ""}>✕</button>
        </div></td>
      </tr>`;
    })
    .join("");
  $("totalScore").textContent = String(totalScore());
  // 工具条计数徽章与汇总条题数共用 data-question-count，一次同步两处。
  for (const node of composeMask.querySelectorAll("[data-question-count]")) node.textContent = String(selected.length);
  // 校验条：有解析失败的题号亮红「N 道题待处理」，全部正常亮绿。
  const invalid = selected.filter((item) => item.missing).length;
  const chip = $("validationChip");
  chip.textContent = invalid ? `${invalid} 道题待处理` : "题目状态正常";
  chip.classList.toggle("ok", invalid === 0);
  // 总分变了，及格分是否超标要重判（原来合法的及格分可能变非法）。
  refreshPassScoreWarn();
}

// 题号输入是主路径：换行 / 空格 / 逗号 / 顿号任意分隔，直接粘贴老师手里的清单。
export function splitIdNos(text) {
  return String(text || "")
    .split(/[\s,，、;；]+/)
    .map((token) => token.trim().toUpperCase())
    .filter(Boolean);
}

// 批量导入增强：题号后可跟一个分值——「Q000006:15」「Q000006 15」「Q000006，15」均可。
// 规则一句话：纯数字永远归属前面最近的那个题号；没配分值的题用默认分（10）。
// 题号靠形态识别（字母+数字），所以题号本身就是题与题之间的分界，不需要专门分隔符；
// 换行 / 空格 / Tab / 逗号 / 顿号 / 冒号都只是 token 之间的噪音。
const ID_TOKEN = /^[A-Za-z]+\d+$/;
const SCORE_TOKEN = /^\d+$/;
export function parseIdScoreEntries(text) {
  const entries = [];
  for (const raw of String(text || "").split(/[\s,，、;；:]+/)) {
    const token = raw.trim();
    if (!token) continue;
    if (ID_TOKEN.test(token)) {
      entries.push({ id: token.toUpperCase(), score: null });
    } else if (SCORE_TOKEN.test(token) && entries.length && entries[entries.length - 1].score === null) {
      const value = Number(token);
      if (Number.isInteger(value) && value > 0) entries[entries.length - 1].score = value;
    }
    // 游离数字（前面没题号 / 该题已有分值 / 非正整数）一律忽略不标红——分值好改，题号错才值得标红。
  }
  return entries;
}

async function parseIdInput() {
  const entries = parseIdScoreEntries($("idInput").value);
  if (!entries.length) {
    $("importFeedback").textContent = "请先粘贴或输入题号。";
    return;
  }
  const known = new Set(selected.map((item) => item.problem_id_no));
  const seen = new Set();
  // 跳过两类重复：已在已选列表里的、本次粘贴里重复出现的（保首次）。
  const fresh = entries.filter((entry) => {
    if (known.has(entry.id) || seen.has(entry.id)) return false;
    seen.add(entry.id);
    return true;
  });
  if (!fresh.length) {
    $("idInput").value = "";
    $("importFeedback").textContent = "这些题号都已在列表里。";
    return;
  }
  // 逐个查 pickable 校验并回填摘要；解析不出来的不静默丢弃，留在列表里标红。
  const found = new Map();
  for (const entry of fresh) {
    try {
      const data = await adminRequest(`/problems/pickable?keyword=${encodeURIComponent(entry.id)}&page=1&size=20`);
      const hit = (data.items || []).find((item) => item.problem_id_no === entry.id);
      if (hit) found.set(entry.id, hit);
    } catch {
      /* 单条失败按未找到处理，下面统一标红 */
    }
  }
  for (const entry of fresh) {
    const hit = found.get(entry.id);
    selected.push({
      problem_id_no: entry.id,
      score: entry.score ?? 10,
      title: hit ? hit.title || hit.stem_text : "",
      type: hit ? hit.type : null,
      missing: !hit,
    });
  }
  $("idInput").value = "";
  renderSelected();
  const missing = fresh.filter((entry) => !found.has(entry.id));
  const skipped = entries.length - fresh.length;
  $("importFeedback").textContent = `已加入 ${fresh.length} 道${skipped ? `，跳过重复 ${skipped} 道` : ""}`;
  if (missing.length) toast(`${missing.length} 个题号无法解析，已在列表中标红：${missing.map((entry) => entry.id).join("、")}`, "error");
}

// ==================== 题库选题面板（辅助入口，默认收起）====================
const bankList = createPagedList({
  els: {
    rows: $("bankRows"),
    emptyTip: $("bEmptyTip"),
    errorTip: $("bErrorTip"),
    errorText: $("bErrorText"),
    totalTip: $("bTotalTip"),
    prevBtn: $("bPrevBtn"),
    nextBtn: $("bNextBtn"),
    retryBtn: $("bRetryBtn"),
  },
  skeletonCols: 5,
  fetchPage: ({ page, size }) => {
    const params = new URLSearchParams({ page, size });
    const keyword = $("bKeyword").value.trim();
    if (keyword) params.set("keyword", keyword);
    if ($("bType").value) params.set("type", $("bType").value);
    if ($("bDifficulty").value) params.set("difficulty", $("bDifficulty").value);
    // ⚠️ 只能是 pickable：见文件头安全红线。
    return adminRequest(`/problems/pickable?${params}`);
  },
  renderRows(items) {
    const known = new Set(selected.map((item) => item.problem_id_no));
    $("bankRows").innerHTML = items
      .map((item) => {
        const added = known.has(item.problem_id_no);
        return `
      <tr>
        <td><button class="btn-text link" type="button" data-add="${escapeHtml(item.problem_id_no)}" ${
          added ? "disabled" : ""
        }>${added ? "已加入" : "加入"}</button></td>
        <td>${escapeHtml(item.problem_id_no)}</td>
        <td class="cell-clip" title="${escapeHtml(item.stem_text || "")}">${escapeHtml(item.title || item.stem_text || "")}</td>
        <td>${escapeHtml(TYPE_LABEL[item.type] || item.type)}</td>
        <td>${escapeHtml(item.difficulty || "")}</td>
      </tr>`;
      })
      .join("");
  },
});

function openCompose(paper) {
  paperState = paper ? {
    title: paper.title, description: paper.description, paper_type: paper.paper_type,
    subject: paper.subject, ruleset: paper.ruleset, score_mode: paper.score_mode,
    partial_credit_multi: paper.partial_credit_multi, pass_score: paper.pass_score,
  } : emptyPaper();
  selected = paper
    ? (paper.questions || []).map((q) => ({
        problem_id_no: q.problem_id_no, score: q.score,
        title: q.problem ? q.problem.title : "", type: q.problem ? q.problem.type : null,
        missing: !q.problem,
      }))
    : [];
  editingId = paper ? paper.id : null;
  editingRevision = paper ? paper.revision : null;
  editingStatus = paper ? paper.status : null;
  $("composeTitle").textContent = paper ? (readOnly ? "查看试卷" : "编辑试卷") : "组卷";
  $("presetHint").textContent = "";
  $("idInput").value = "";
  if (!paper) {
    // 首屏一致性：默认选中的类型要把预设真正展开，否则字段值停在初始值、
    // 和界面上选中的「练习卷」标签对不上。展开必须在拍快照之前。
    const preset = applyPreset(paperState, null, paperState.paper_type);
    if (preset) $("presetHint").textContent = `已按「${preset.paper_type}」填充，可逐项调整`;
  }
  // 自由文本只在打开时填充一次；之后的界面重绘不再碰它们（见 renderComposeAttrs 注释）。
  $("pTitle").value = paperState.title;
  $("pDesc").value = paperState.description;
  $("pPartialMulti").checked = paperState.partial_credit_multi;
  $("pPassScore").value = paperState.pass_score ?? "";
  renderComposeAttrs();
  renderComposeFooter();
  renderSelected();
  snapshotAtOpen = snapshot();
  // 抽屉回到初始状态：关闭、回到题库页签、清空导入反馈。
  closeDrawer({ restoreFocus: false });
  activateDrawerPanel("libraryPanel");
  $("importFeedback").textContent = "";
  releaseCompose = openMask(composeMask, { focusSelector: "#pTitle" });
}

async function closeCompose() {
  if (!readOnly && snapshot() !== snapshotAtOpen) {
    const ok = await confirmDialog({
      title: "放弃未保存的修改？",
      message: "组卷内容有改动尚未保存。",
      confirmText: "放弃修改",
      danger: true,
    });
    if (!ok) return;
  }
  closeMask(composeMask, releaseCompose);
  releaseCompose = null;
  readOnly = false;
}

function collectPaperPayload() {
  return {
    title: $("pTitle").value.trim(),
    description: $("pDesc").value.trim(),
    paper_type: pillValue("pType"),
    subject: pillValue("pSubject"),
    ruleset: pillValue("pRuleset"),
    score_mode: pillValue("pScoreMode"),
    partial_credit_multi: $("pPartialMulti").checked,
    pass_score: $("pPassScore").value === "" ? null : Number($("pPassScore").value),
    questions: selected.map((item, index) => ({
      problem_id_no: item.problem_id_no, score: Number(item.score) || 0, sort_order: index,
    })),
  };
}

// keepOpen=true 供「保存并预览」用：保存成功后组卷弹窗不关闭，紧跟着在上面打开整卷预览。
// 返回 true/false 表示是否真正落库，调用方据此决定是否继续（校验 toast 后中断）。
async function savePaper({ publish, keepOpen = false }) {
  // 已发布卷不存在「再发布一次」：底栏已经不给这个按钮，这里是二道保险——
  // 真发出去只会先 PUT 成功再被后端 409 挡回，白白造出一次半成功的写入。
  const wantPublish = publish && editingStatus !== "published";
  if (!$("pTitle").value.trim()) { toast("请填写试卷名称。", "error"); return false; }
  if (!selected.length) { toast("请先加入至少一道题。", "error"); return false; }
  if (selected.some((item) => item.missing)) { toast("有题号无法解析（红色行），请先移除或改正。", "error"); return false; }
  // 发布前置校验：与后端发布校验同语义，前端先拦省一次往返；草稿允许带着红提示保存。
  if (wantPublish && $("pPassScore").value !== "" && Number($("pPassScore").value) > totalScore()) {
    toast(`及格分超过当前总分（${totalScore()} 分），无法发布——请先调整及格分或题目分值。`, "error");
    return false;
  }
  const buttons = [$("saveBtn"), $("publishBtn")];
  buttons.forEach((btn) => (btn.disabled = true));
  $("composeState").textContent = "处理中…";
  try {
    const payload = collectPaperPayload();
    const saved = editingId
      ? await adminRequest(`/papers/${editingId}`, { method: "PUT", headers: ifMatch(editingRevision), body: JSON.stringify(payload) })
      : await adminRequest("/papers", { method: "POST", body: JSON.stringify(payload) });
    // 这一步已经 commit 了：立刻把本地状态和快照对齐。
    // 后面任一步失败也不能再弹「放弃未保存的修改？」——那笔改动已经放弃不掉了。
    editingId = saved.id;
    editingRevision = saved.revision;
    editingStatus = saved.status;
    snapshotAtOpen = snapshot();
    if (wantPublish) {
      // 发布同样会 _touch，revision 必须从响应里取回，否则弹窗留着的是过期版本号。
      const published = await adminRequest(`/papers/${saved.id}/publish`, { method: "POST", headers: ifMatch(saved.revision), body: "{}" });
      editingRevision = published.revision;
      editingStatus = published.status;
      toast("已发布。发布后可在「考试链接」里安排场次。", "success");
      zone = "published";
      syncZoneTabs();
    } else {
      toast(editingStatus === "published" ? "已保存，修改已对现有考试链接生效。" : "已保存。", "success");
      // 默认分区是「已发布」：存了草稿要跟进到草稿区，否则刚存的卷在眼前消失。
      if (["draft", "published", "archived"].includes(editingStatus) && editingStatus !== zone) {
        zone = editingStatus;
        syncZoneTabs();
      }
    }
    if (keepOpen) {
      // 保存并预览：弹窗留着，但状态可能从「新建」变成「草稿」，底栏按钮要跟着换。
      renderComposeFooter();
    } else {
      closeMask(composeMask, releaseCompose);
      releaseCompose = null;
    }
    list.reload();
    return true;
  } catch (error) {
    toast(error.message || "保存失败。", "error");
    // 失败也可能是「PUT 成过、publish 没成」这种半程失败：底栏按新状态重画，
    // 列表刷新到真实数据，绝不让界面停留在与库里不一致的样子。
    renderComposeFooter();
    list.reload();
    return false;
  } finally {
    buttons.forEach((btn) => (btn.disabled = false));
    $("composeState").textContent = "";
  }
}

// ==================== 整卷预览 ====================
// 取数只走 GET /papers/{id}/preview（卷级组装、按 with_answers 裁剪答案），
// 绝不调 /problems/{id}——那会把完整答案发进学员卷也能打开的浏览器。
// 卷别切换 = 重新请求 ?with_answers=0|1：学员卷的响应里必须压根没有答案字段，
// CSS 隐藏不是安全边界（见 DEMO 与《整卷预览-技术方案》4.1）。
const previewMask = $("paperPreviewMask");
const previewSheet = $("paperPreviewSheet");
let previewPaperId = null;
let previewLoadSeq = 0; // 防连点卷别时旧响应后落地、覆盖新响应
let releasePreviewFocus = null;
let previewOpener = null; // 关闭后把焦点还回去（列表行的按钮或组卷工具条的按钮）

const PV_VARIANTS = [["student", "学员卷"], ["teacher", "教师卷"]];
const pvIsTeacher = () => pillValue("pvVariant") === "teacher";
const isPreviewOpen = () => !previewMask.hidden;

// 参考答案的一行摘要：选择/判断给选项字母，填空逐空列出，操作题指向参考代码。
function pvAnswerText(question) {
  if (question.type === "fill") {
    return (question.blanks || []).map((b) => `第 ${b.blank_index + 1} 空：${b.answer}`).join("；") || "—";
  }
  if (question.options) {
    return question.options.filter((o) => o.is_correct).map((o) => o.label).join("、") || "—";
  }
  return "见参考代码";
}

// 留白按题型给：选择类给一条答案栏，操作题给手写框，
// 填空题什么都不给——题干里的横线本身就是答题处，再补一行是多余的。
function pvAnswerSpaceShell(question) {
  if (question.type === "programming") {
    return '<div class="answer-space"><p class="hint">（在评测系统中提交代码；如需手写，请写在下框内）</p><div class="box"></div></div>';
  }
  if (question.type === "fill") return "";
  return '<div class="answer-space"><span class="slot">答案：<i></i></span></div>';
}

// 教师卷的答案区（学员卷渲染时整段不存在——响应里本来就没有这些字段）。
function pvAnswerBoxShell(question, paper) {
  let ref = "";
  if (question.type === "programming") {
    const p = question.programming;
    ref = `<h4>参考代码（${p.ref_code.language === "python" ? "Python" : "C++"}）</h4><pre>${escapeHtml(p.ref_code.code || "（未提供）")}</pre>
       <h4>通过条件</h4><p>${escapeHtml(p.pass_condition || "—")}</p>`;
  }
  const halfNote = question.type === "multi_choice" && paper.partial_credit_multi
    ? '<p class="half-note">本卷多选按半分计：少选且无错选给一半分。</p>'
    : "";
  return `
    <div class="answer-box">
      <h4>参考答案</h4><p>${escapeHtml(pvAnswerText(question))}</p>${halfNote}
      ${question.analysis ? '<h4>答案解析</h4><div class="md-slot" data-md-slot="analysis"></div>' : ""}
      ${ref}
    </div>`;
}

// 操作题小节顺序与学员端一致：题面 → 输入格式 → 输出格式 → 样例 → 说明/提示 → 限制。
function pvProgrammingShell(question) {
  const p = question.programming;
  const samples = (p.samples || [])
    .map(
      (s, i) => `
      <div class="prog-section samples">
        <div><h5>样例输入 ${i + 1}</h5><pre>${escapeHtml(s.input)}</pre></div>
        <div><h5>样例输出 ${i + 1}</h5><pre>${escapeHtml(s.output)}</pre></div>
      </div>`,
    )
    .join("");
  return `
    <div class="md-slot" data-md-slot="stem"></div>
    <div class="prog-section"><h4>输入格式</h4><div class="md-slot" data-md-slot="input_format"></div></div>
    <div class="prog-section"><h4>输出格式</h4><div class="md-slot" data-md-slot="output_format"></div></div>
    ${samples}
    <div class="prog-section"><h4>说明 / 提示</h4><div class="md-slot" data-md-slot="hints"></div></div>
    <div class="limits">
      <span>语言：<b>${question.sub_type === "python" ? "Python" : "C++"}</b></span>
      <span>时间限制：<b>${p.time_limit_ms} ms</b></span>
      <span>内存限制：<b>${p.memory_limit_mb} MB</b></span>
    </div>`;
}

function pvQuestionShell(question, displayNo, teacher, paper) {
  if (question.missing) {
    // 题被删/退审：占位行整行标红，让老师看见「第 N 题没了」，而不是静默跳过。
    return `
      <section class="q q-missing">
        <div class="q-head">
          <span class="q-no">${displayNo}.</span>
          <span class="tag danger">⚠ 题目缺失</span>
          <span class="q-score">（${question.score} 分）</span>
        </div>
        <div class="q-body"><p class="missing-tip">题号 ${escapeHtml(question.problem_id_no)} 已被删除或未过审——本卷此处留空，请回到组卷移除或替换该题。</p></div>
      </section>`;
  }
  const isProg = question.type === "programming";
  const admin = teacher
    ? `<span class="q-admin">${escapeHtml(question.problem_id_no)} · ${escapeHtml(question.difficulty || "—")} · ${escapeHtml(question.source || "—")}</span>`
    : "";
  // 未过审（编号还在、状态已不是 approved）：与 missing 同一套提示语言，
  // 发布会拒的题，预览不能渲染得毫无痕迹。
  const approval = question.approved === false ? '<span class="tag danger">⚠ 未过审</span>' : "";
  const options = (question.options || [])
    .map(
      (opt) => `<li class="${opt.is_correct ? "correct" : ""}"><span class="opt-label">${opt.label}.</span><span class="opt-text md-slot" data-md-slot="option:${opt.label}"></span></li>`,
    )
    .join("");
  const body = isProg
    ? pvProgrammingShell(question)
    : `<div class="md-slot" data-md-slot="stem"></div>${options ? `<ul class="options">${options}</ul>` : ""}`;
  return `
    <section class="q" data-q="${displayNo - 1}">
      <div class="q-head">
        <span class="q-no">${displayNo}.</span>
        ${isProg && question.programming.title ? `<span class="q-title">${escapeHtml(question.programming.title)}</span>` : ""}
        <span class="tag">${escapeHtml(TYPE_LABEL[question.type] || question.type)}</span>
        ${approval}
        <span class="q-score">（${question.score} 分）</span>
        ${admin}
      </div>
      <div class="q-body">${body}</div>
      ${teacher ? pvAnswerBoxShell(question, paper) : pvAnswerSpaceShell(question)}
    </section>`;
}

// Markdown 槽位逐个渲染（Vditor.preview 是异步的）；渲完教师卷把填空答案填回原位。
async function pvRenderQuestionMarkdown(node, question, teacher) {
  const slots = { stem: question.stem || "" };
  if (question.type === "programming") {
    slots.input_format = question.programming.input_format;
    slots.output_format = question.programming.output_format;
    slots.hints = question.programming.hints;
  }
  if (teacher && question.analysis) slots.analysis = question.analysis;
  for (const opt of question.options || []) slots[`option:${opt.label}`] = opt.content;
  for (const slot of node.querySelectorAll(".md-slot")) {
    const key = slot.dataset.mdSlot;
    if (!(key in slots)) continue;
    await renderMarkdown(slot, slots[key]);
  }
  // 教师卷：按 blank_key 找回题干里的空位标记填上答案；学员卷没有 blanks，保持空横线。
  if (teacher && question.type === "fill") {
    for (const blank of question.blanks || []) {
      for (const mark of node.querySelectorAll(`.blank-mark[data-key="${blank.blank_key}"]`)) {
        mark.textContent = blank.answer;
        mark.classList.add("filled");
      }
    }
  }
}

async function pvRender(paper, seq) {
  const teacher = paper.with_answers === true;
  previewSheet.dataset.space = !teacher && $("pvAnswerSpace").checked ? "on" : "off";
  const passLine = paper.pass_score != null ? ` · 及格 ${paper.pass_score} 分` : "";
  previewSheet.innerHTML = `
    ${teacher ? '<div class="teacher-banner">⚠ 教师卷：含参考答案、解析与参考代码，请勿投屏或分发给学员。</div>' : ""}
    <header class="paper-head">
      <div class="paper-meta-top">
        <span>${escapeHtml(paper.paper_id_no || "草稿")}</span>
        <span class="tag">${escapeHtml(paper.paper_type)}</span>
        <span class="tag">${escapeHtml(SUBJECT_LABEL[paper.subject] || paper.subject)}</span>
        <span class="tag">${escapeHtml(paper.ruleset || "—")}</span>
      </div>
      <h1 class="paper-title">${escapeHtml(paper.title)}</h1>
      <p class="paper-sub">满分 ${paper.total_score} 分${passLine} · 共 ${paper.questions.length} 题</p>
      ${paper.description ? `<div class="paper-desc">${escapeHtml(paper.description)}</div>` : ""}
      <div class="exam-fields">
        <span>姓名<i></i></span><span>班组<i></i></span><span>学号<i></i></span><span>得分<i></i></span>
      </div>
    </header>
    ${paper.questions.map((q, i) => pvQuestionShell(q, i + 1, teacher, paper)).join("")}`;
  // 题目节点一次性快照，循环里绝不再查 previewSheet——这是本函数唯一容易写错的地方：
  // 每个 await 都可能被新一轮渲染（切卷别）插队并整块换掉 innerHTML，若在循环里重新
  // querySelector，旧这一轮会拿到**新 DOM** 的节点，把教师卷的答案写进已经换成学员卷的卷面
  // （实测：切到教师卷再立刻切回，学员卷的填空横线上会出现答案）。
  // 快照里的节点在换页后即脱离文档，旧渲染继续写也上不了屏；seq 只是省下白干的活。
  const nodes = new Map(
    [...previewSheet.querySelectorAll("section.q")].map((node) => [Number(node.dataset.q), node]),
  );
  // 按题并行：一张 20 题的卷串行渲要等 100 次 Vditor.preview，首屏明显卡。
  // 并行的粒度必须是「题」而不是「槽位」——填空回填要等本题题干渲完才有 .blank-mark 可填，
  // 而 pvRenderQuestionMarkdown 把回填放在自己那几个 await 之后，题与题之间互不相干，
  // 所以并行到题这一层，回填时序天然不受影响。
  const pending = [];
  for (const [index, question] of paper.questions.entries()) {
    if (seq !== previewLoadSeq) return; // 已被新一轮取代
    if (question.missing) continue;
    const node = nodes.get(index);
    if (!node) continue;
    if (pending.length === 0) {
      // 第一题单独等一遍：Vditor 冷启动要现拉 lute 脚本，并发首调会各拉各的（脚本 id 在
      // onload 才写上，早到的并发命不中缓存分支）。等它落地，后面的并发都走已加载的快路径。
      await pvRenderQuestionMarkdown(node, question, teacher);
      pending.push(Promise.resolve());
      continue;
    }
    pending.push(pvRenderQuestionMarkdown(node, question, teacher));
  }
  await Promise.all(pending);
}

async function loadPaperPreview() {
  const seq = ++previewLoadSeq;
  const teacher = pvIsTeacher();
  $("pvSpaceLine").hidden = teacher; // 答题留白只在学员卷生效
  previewSheet.innerHTML = '<p class="muted" style="text-align:center; padding: 40px 0">正在加载整卷预览…</p>';
  try {
    const paper = await adminRequest(`/papers/${previewPaperId}/preview?with_answers=${teacher ? 1 : 0}`);
    if (seq !== previewLoadSeq) return; // 期间又切了一次卷别，丢弃旧响应
    await pvRender(paper, seq);
  } catch (error) {
    if (seq !== previewLoadSeq) return;
    toast(error.message || "预览加载失败。", "error");
    closePaperPreview();
  }
}

async function openPaperPreview(paperId) {
  previewPaperId = paperId;
  renderPills($("pvVariantGroup"), "pvVariant", PV_VARIANTS, "student");
  $("pvAnswerSpace").checked = false;
  if (!isPreviewOpen()) {
    previewMask.hidden = false;
    previewMask.setAttribute("aria-hidden", "false");
    // 焦点跟着走：与题库页「整题预览」对齐，另加 Tab 环（trapFocus 挂在容器上，
    // 不会和下面组卷 Modal 自己的焦点环打架）。关闭时还回打开它的那个按钮。
    previewOpener = document.activeElement;
    releasePreviewFocus = trapFocus(previewMask.querySelector(".preview-dialog"));
    $("paperPreviewClose").focus();
    // 打印专属：body.preview-open 时 @media print 只保留卷面（见 admin.css 末尾）。
    document.body.classList.add("preview-open");
  }
  await loadPaperPreview();
}

function closePaperPreview() {
  if (!isPreviewOpen()) return;
  previewLoadSeq += 1; // 让在途响应落地时被丢弃
  previewMask.hidden = true;
  previewMask.setAttribute("aria-hidden", "true");
  document.body.classList.remove("preview-open");
  releasePreviewFocus?.();
  releasePreviewFocus = null;
  previewOpener?.focus?.();
  previewOpener = null;
  previewPaperId = null;
  previewSheet.replaceChildren();
}

// 组卷中的「预览整卷」：预览取的是已落库内容，有未保存改动先确认保存，
// 保证卷面和组卷面板看到的是同一份内容。保存成功后弹窗保持打开，预览压在上面。
$("openPreviewBtn").addEventListener("click", async () => {
  if (!editingId && snapshot() === snapshotAtOpen) {
    return toast("请先保存试卷，再预览整卷。", "error");
  }
  if (snapshot() !== snapshotAtOpen) {
    const ok = await confirmDialog({
      title: "预览需要先保存",
      message: "预览展示的是已保存的试卷内容，当前有未保存的改动。",
      confirmText: "保存并预览",
    });
    if (!ok) return;
    if (!(await savePaper({ publish: false, keepOpen: true }))) return;
  }
  if (editingId) openPaperPreview(editingId);
});

$("paperPreviewClose").addEventListener("click", closePaperPreview);
previewMask.addEventListener("click", (event) => { if (event.target === previewMask) closePaperPreview(); });
$("pvVariantGroup").addEventListener("change", () => { if (previewPaperId) loadPaperPreview(); });
$("pvAnswerSpace").addEventListener("change", (event) => {
  previewSheet.dataset.space = event.target.checked ? "on" : "off";
});
$("pvPrintBtn").addEventListener("click", () => window.print());

// ==================== 考试名单 ====================
// 链接配置仍在独立页维护；这里只管理某条链接已经有的名单关系。
const assignmentMask = $("assignmentMask");
let assignmentRelease = null;
let assignmentLinkId = null;
let assignmentOptionsLoaded = false;

function assignmentEndpoint() {
  return `/exam-links/${assignmentLinkId}/assignments`;
}

function assignmentDate(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

function closeAssignments() {
  if (!isMaskOpen(assignmentMask)) return;
  closeMask(assignmentMask, assignmentRelease);
  assignmentRelease = null;
  assignmentLinkId = null;
  assignmentOptionsLoaded = false;
  $("assignmentRows").replaceChildren();
}

function renderAssignmentTypeOptions(options) {
  const select = $("assignmentTargetType");
  const selected = select.value;
  select.innerHTML = options
    .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
    .join("");
  if (options.some((option) => option.value === selected)) select.value = selected;
}

async function refreshAssignments() {
  if (!assignmentLinkId) return;
  $("assignmentRows").innerHTML = '<tr><td class="muted" colspan="5">正在读取名单…</td></tr>';
  $("assignmentEmpty").hidden = true;
  try {
    const data = await adminRequest(assignmentEndpoint());
    if (!assignmentOptionsLoaded) {
      renderAssignmentTypeOptions(data.target_type_options || []);
      assignmentOptionsLoaded = true;
    }
    $("assignmentTotal").textContent = `共 ${data.total} 条`;
    $("assignmentRows").innerHTML = (data.items || [])
      .map((item) => `
        <tr>
          <td>${escapeHtml(item.target_type_label)}</td>
          <td>${escapeHtml(item.target_name || "—")}</td>
          <td>${item.target_id}</td>
          <td>${escapeHtml(assignmentDate(item.assigned_at))}</td>
          <td><button class="btn-text link danger" type="button" data-end-assignment="${item.id}">取消指派</button></td>
        </tr>`)
      .join("");
    $("assignmentEmpty").hidden = data.total !== 0;
  } catch (error) {
    $("assignmentRows").replaceChildren();
    $("assignmentTotal").textContent = "";
    $("assignmentEmpty").hidden = false;
    $("assignmentEmpty").textContent = error.message || "名单读取失败。";
  }
}

async function openAssignments(paperId) {
  const paper = await adminRequest(`/papers/${paperId}`);
  const links = await adminRequest(`/papers/${paperId}/links`);
  if (!(links.items || []).length) {
    toast("请先创建考试链接，再配置名单。", "error");
    return;
  }
  $("assignmentPaperName").textContent = paper.title;
  $("assignmentLinkSelect").innerHTML = links.items
    .map((link) => `<option value="${link.id}">${escapeHtml(link.name)}</option>`)
    .join("");
  assignmentLinkId = Number($("assignmentLinkSelect").value);
  assignmentOptionsLoaded = false;
  assignmentRelease = openMask(assignmentMask, { focusSelector: "#assignmentLinkSelect" });
  await refreshAssignments();
}

$("assignmentClose").addEventListener("click", closeAssignments);
assignmentMask.addEventListener("click", (event) => { if (event.target === assignmentMask) closeAssignments(); });
$("assignmentLinkSelect").addEventListener("change", async (event) => {
  assignmentLinkId = Number(event.target.value);
  assignmentOptionsLoaded = false;
  await refreshAssignments();
});
$("assignmentForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const targetId = Number($("assignmentTargetId").value);
  if (!Number.isInteger(targetId) || targetId < 1) return;
  const submit = $("assignmentSubmit");
  submit.disabled = true;
  try {
    await adminRequest(assignmentEndpoint(), {
      method: "POST",
      body: JSON.stringify({ target_type: $("assignmentTargetType").value, target_id: targetId }),
    });
    $("assignmentTargetId").value = "";
    toast("已加入考试名单。", "success");
    await refreshAssignments();
  } catch (error) {
    toast(error.message || "名单添加失败。", "error");
  } finally {
    submit.disabled = false;
  }
});
$("assignmentRows").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-end-assignment]");
  if (!button) return;
  const confirmed = await confirmDialog({
    title: "取消考试指派",
    message: "确认取消这条考试名单吗？",
    detail: "取消后不会删除历史记录，之后仍可再次指派。",
    confirmText: "确认取消",
    danger: true,
  });
  if (!confirmed) return;
  button.disabled = true;
  try {
    await adminRequest(`${assignmentEndpoint()}/${button.dataset.endAssignment}`, { method: "DELETE" });
    toast("已取消指派。", "success");
    await refreshAssignments();
  } catch (error) {
    toast(error.message || "取消指派失败。", "error");
    button.disabled = false;
  }
});

// ==================== 事件绑定 ====================
function syncZoneTabs() {
  for (const btn of document.querySelectorAll(".zone-tabs button")) {
    btn.classList.toggle("active", btn.dataset.zone === zone);
  }
}

document.querySelector(".zone-tabs")?.addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-zone]");
  if (!btn) return;
  zone = btn.dataset.zone;
  syncZoneTabs();
  list.page = 1;
  list.reload();
});

$("searchBtn").addEventListener("click", () => { list.page = 1; list.reload(); });
$("resetBtn").addEventListener("click", () => {
  for (const id of ["sKeyword", "sType", "sSubject", "sOwner"]) $(id).value = "";
  list.page = 1;
  list.reload();
});
$("sKeyword").addEventListener("keydown", (e) => { if (e.key === "Enter") { list.page = 1; list.reload(); } });

$("newPaperBtn").addEventListener("click", () => { readOnly = false; openCompose(null); });

rows.addEventListener("click", async (event) => {
  const btn = event.target.closest("button[data-edit],button[data-view],button[data-preview],button[data-assignments],button[data-publish],button[data-archive],button[data-delete]");
  if (!btn) return;
  const { edit, view, preview, assignments, publish, archive, delete: del } = btn.dataset;
  try {
    if (edit || view) {
      readOnly = Boolean(view);
      openCompose(await adminRequest(`/papers/${edit || view}`));
    } else if (preview) {
      await openPaperPreview(preview);
    } else if (assignments) {
      await openAssignments(assignments);
    } else if (publish) {
      const paper = await adminRequest(`/papers/${publish}`);
      const ok = await confirmDialog({ title: "发布试卷", message: `确认发布「${paper.title}」？`, detail: "发布后即可创建考试链接；之后每次修改仍会重新过发布校验。", confirmText: "确认发布" });
      if (!ok) return;
      await adminRequest(`/papers/${publish}/publish`, { method: "POST", headers: ifMatch(paper.revision), body: "{}" });
      toast("已发布。", "success");
      list.reload();
    } else if (archive) {
      const paper = await adminRequest(`/papers/${archive}`);
      const ok = await confirmDialog({ title: "归档试卷", message: `确认归档「${paper.title}」？`, detail: "归档即锁定：试卷不可再编辑，其下所有考试链接一并停用且无法重置。", confirmText: "确认归档", danger: true });
      if (!ok) return;
      await adminRequest(`/papers/${archive}/archive`, { method: "POST", headers: ifMatch(paper.revision), body: "{}" });
      toast("已归档。", "success");
      list.reload();
    } else if (del) {
      // 归档卷和草稿的后果完全不同：归档卷名下的链接会一并销毁，必须把话说清楚。
      const paper = await adminRequest(`/papers/${del}`);
      const archived = paper.status === "archived";
      const ok = await confirmDialog({
        title: "删除试卷",
        message: `确认删除「${paper.title}」？`,
        detail: archived
          ? `归档卷删除后不可恢复：名下 ${paper.link_count} 条考试链接一并销毁，已分发出去的地址全部失效；编号 ${paper.paper_id_no} 不会被回收，审计记录保留。`
          : "草稿删除后不可恢复。",
        confirmText: "确认删除",
        danger: true,
      });
      if (!ok) return;
      await adminRequest(`/papers/${del}`, { method: "DELETE", headers: ifMatch(paper.revision) });
      toast("已删除。", "success");
      list.retreatIfEmpty();
      list.reload();
    }
  } catch (error) {
    toast(error.message || "操作失败。", "error");
    list.reload();
  }
});

// 组卷 Modal 内的交互
$("composeClose").addEventListener("click", closeCompose);
$("composeCancel").addEventListener("click", closeCompose);
composeMask.addEventListener("click", (e) => { if (e.target === composeMask) closeCompose(); });
$("saveBtn").addEventListener("click", () => savePaper({ publish: false }));
$("publishBtn").addEventListener("click", async () => {
  const ok = await confirmDialog({ title: "发布试卷", message: "确认保存并发布这张试卷？", detail: "发布后可在「考试链接」里安排场次；之后每次修改仍会重新过发布校验。", confirmText: "确认发布" });
  if (ok) savePaper({ publish: true });
});
$("parseIdsBtn").addEventListener("click", parseIdInput);
$("bSearchBtn").addEventListener("click", () => { bankList.page = 1; bankList.reload(); });
$("bankRows").addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-add]");
  if (!btn || btn.disabled) return;
  const item = bankList.items.find((row) => row.problem_id_no === btn.dataset.add);
  if (!item) return;
  selected.push({ problem_id_no: item.problem_id_no, score: 10, title: item.title || item.stem_text, type: item.type, missing: false });
  renderSelected();
  bankList.reload();
});
$("selectedRows").addEventListener("input", (event) => {
  const index = event.target.dataset.score;
  if (index === undefined) return;
  selected[Number(index)].score = Number(event.target.value) || 0;
  $("totalScore").textContent = String(totalScore());
});
$("selectedRows").addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-up],button[data-down],button[data-remove]");
  if (!btn || btn.disabled) return;
  const { up, down, remove } = btn.dataset;
  if (remove !== undefined) selected.splice(Number(remove), 1);
  else {
    const from = Number(up ?? down);
    const to = up !== undefined ? from - 1 : from + 1;
    [selected[from], selected[to]] = [selected[to], selected[from]];
  }
  renderSelected();
  bankList.reload();
});

// 拖拽排序：⠿ 手柄按住才放行拖拽（避免误拖文本），松手即收回。
// 与 ↑↓ 单格微调并存：长距离挪动用拖拽，相邻换位用箭头。
let dragIndex = null;
const clearDragState = () => {
  dragIndex = null;
  for (const tr of $("selectedRows").querySelectorAll("tr")) {
    tr.classList.remove("dragging", "drop-before", "drop-after");
    tr.draggable = false;
  }
};
$("selectedRows").addEventListener("mousedown", (event) => {
  const grip = event.target.closest(".drag-grip");
  if (!grip || grip.classList.contains("disabled")) return;
  const tr = grip.closest("tr");
  if (tr) tr.draggable = true;
});
$("selectedRows").addEventListener("dragstart", (event) => {
  const tr = event.target.closest("tr");
  if (!tr || readOnly) return;
  dragIndex = Number(tr.dataset.index);
  tr.classList.add("dragging");
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
});
$("selectedRows").addEventListener("dragover", (event) => {
  const tr = event.target.closest("tr");
  if (!tr || dragIndex === null) return;
  event.preventDefault();
  const rect = tr.getBoundingClientRect();
  const before = (event.clientY || 0) < rect.top + rect.height / 2;
  tr.classList.toggle("drop-before", before);
  tr.classList.toggle("drop-after", !before);
});
$("selectedRows").addEventListener("drop", (event) => {
  const tr = event.target.closest("tr");
  if (!tr || dragIndex === null) return;
  event.preventDefault();
  const rect = tr.getBoundingClientRect();
  const before = (event.clientY || 0) < rect.top + rect.height / 2;
  const from = dragIndex;
  let to = Number(tr.dataset.index) + (before ? 0 : 1);
  const [moved] = selected.splice(from, 1);
  if (to > from) to -= 1;
  selected.splice(to, 0, moved);
  clearDragState();
  renderSelected();
});
$("selectedRows").addEventListener("dragend", clearDragState);

// ==================== 题目来源抽屉（从题库添加 / 批量导入题号） ====================
const composeRight = $("composeRight");
const sourceDrawer = $("sourceDrawer");
let lastDrawerTrigger = null;

function activateDrawerPanel(panelId) {
  for (const tab of document.querySelectorAll("#composeModal .drawer-tab")) {
    const active = tab.dataset.panel === panelId;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  }
  for (const panel of document.querySelectorAll("#composeModal .drawer-panel")) {
    panel.hidden = panel.id !== panelId;
  }
}

const isDrawerOpen = () => composeRight.classList.contains("is-drawer-open");

function openDrawer(panelId, trigger) {
  lastDrawerTrigger = trigger || null;
  activateDrawerPanel(panelId);
  composeRight.classList.add("is-drawer-open");
  sourceDrawer.removeAttribute("inert");
  sourceDrawer.setAttribute("aria-hidden", "false");
  $("openLibrary").setAttribute("aria-expanded", String(trigger === $("openLibrary")));
  $("openImport").setAttribute("aria-expanded", String(trigger === $("openImport")));
  // 题库页签激活即刷新：保证「已加入」置灰与已选列表同步。
  if (panelId === "libraryPanel") bankList.reload();
  $("drawerClose").focus();
}

function closeDrawer({ restoreFocus = true } = {}) {
  if (!isDrawerOpen()) return;
  composeRight.classList.remove("is-drawer-open");
  sourceDrawer.setAttribute("inert", "");
  sourceDrawer.setAttribute("aria-hidden", "true");
  $("openLibrary").setAttribute("aria-expanded", "false");
  $("openImport").setAttribute("aria-expanded", "false");
  if (restoreFocus && lastDrawerTrigger) lastDrawerTrigger.focus();
  lastDrawerTrigger = null;
}

$("openLibrary").addEventListener("click", () => openDrawer("libraryPanel", $("openLibrary")));
$("openImport").addEventListener("click", () => openDrawer("importPanel", $("openImport")));
for (const btn of document.querySelectorAll("#composeModal [data-close-drawer]")) {
  btn.addEventListener("click", () => closeDrawer());
}
for (const tab of document.querySelectorAll("#composeModal .drawer-tab")) {
  tab.addEventListener("click", () => {
    activateDrawerPanel(tab.dataset.panel);
    if (tab.dataset.panel === "libraryPanel") bankList.reload();
  });
}
$("pTypeGroup").addEventListener("change", () => {
  const preset = applyPreset(paperState, null, pillValue("pType"));
  if (!preset) return;
  renderComposeAttrs();
  $("presetHint").textContent = `已按「${preset.paper_type}」填充，可逐项调整`;
});

// 自由输入实时回写 paperState：一是预设切换时单选组从 paperState 重绘不会丢改动，
// 二是 snapshot 脏检查能覆盖全部字段（只改名称也会触发「放弃未保存的修改？」提醒）。
$("pTitle").addEventListener("input", (event) => { paperState.title = event.target.value; });
$("pDesc").addEventListener("input", (event) => { paperState.description = event.target.value; });
$("pPassScore").addEventListener("input", (event) => {
  paperState.pass_score = event.target.value === "" ? null : Number(event.target.value);
  refreshPassScoreWarn();
});
$("pPartialMulti").addEventListener("change", (event) => { paperState.partial_credit_multi = event.target.checked; });
$("pSubjectGroup").addEventListener("change", () => { paperState.subject = pillValue("pSubject"); });
$("pRulesetGroup").addEventListener("change", () => { paperState.ruleset = pillValue("pRuleset"); });
$("pScoreModeGroup").addEventListener("change", () => { paperState.score_mode = pillValue("pScoreMode"); });

// 链接管理已迁往 exam-links.html（《4、后台考试链接-管理模块》）：同一套规则不存两份实现。

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  // 预览层（z-index 110）压在所有弹窗之上，Escape 先关它。
  if (isPreviewOpen()) closePaperPreview();
  else if (isMaskOpen(assignmentMask)) closeAssignments();
  else if (isDrawerOpen()) closeDrawer();
  else if (isMaskOpen(composeMask)) closeCompose();
});

// ==================== 启动 ====================
function fillSelect(el, options, placeholder) {
  el.innerHTML = `<option value="">${placeholder}</option>` + options.map(([v, l]) => `<option value="${escapeHtml(String(v))}">${escapeHtml(l)}</option>`).join("");
}

async function bootstrap() {
  fillSelect($("bType"), Object.entries(TYPE_LABEL), "全部题型");
  fillSelect($("bDifficulty"), DIFFICULTIES.map((d) => [d, d]), "全部难度");
  syncZoneTabs();
  const tasks = [list.reload(), refreshCounts()];
  try {
    const { items } = await adminRequest("/paper-owners");
    $("sOwner").innerHTML = '<option value="">全部</option>' + items.map((o) => `<option value="${o.id}">${escapeHtml(o.display_name)}</option>`).join("");
  } catch {
    /* 负责人下拉失败不影响主列表 */
  }
  await Promise.allSettled(tasks);
}

bootstrap();
