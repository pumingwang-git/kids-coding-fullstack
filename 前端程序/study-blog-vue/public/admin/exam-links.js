// 考试链接管理页：跨试卷的链接列表 + 新建/编辑 Modal（含考前提醒规则）。
//
// 规则单一来源（《4、后台考试链接-管理模块》）：
// - 行操作按钮完全按后端返回的 allowed_actions 渲染，前端不写 if (status === ...) 之类的推断；
// - 运行态（phase）由后端按服务器时钟算好随行返回，前端不自己算——
//   客户端时间不准会让老师看到「进行中」而学生打不开；
// - 归档卷的链接只给「删除」（清理），增改由后端 409 挡回并说清原因。
//
// 模块划分：常量与格式化 / 列表 / 复制 / 通知文案 / 预检与学员体验预览 / Modal。

import { initLayout } from "./admin-layout.js";
import { adminRequest, ifMatch } from "./admin-api.js";
import { createPagedList } from "./admin-list.js";
import { createPaperPicker, paperLabel } from "./admin-combobox.js";
import { applyPreset } from "./paper-presets.js";
import { closeMask, confirmDialog, escapeHtml, fmtTime, isMaskOpen, openMask, toast, toIso, toLocalInput } from "./admin-ui.js";

initLayout();

const $ = (id) => document.getElementById(id);

// ==================== 常量与格式化 ====================
const LATE_OPTIONS = [["truncate", "截断到结束时间"], ["block", "剩余不足禁止开始"], ["overrun", "允许超出"]];
const POLICY_OPTIONS = [["best", "取最高"], ["last", "取最新"], ["first", "取首次"]];
const FEEDBACK_OPTIONS = [["realtime", "实时"], ["compile_only", "仅编译"], ["after_close", "截止后"]];
const ANALYSIS_OPTIONS = [["never", "不显示"], ["after_submit", "交卷后"], ["after_close", "截止后"]];
const SHOW_SCORE_OPTIONS = [["immediate", "立即"], ["after_close", "截止后"], ["never", "不显示"]];
// 时间/时长的显式模式：不再用「留空代表某种状态」——留空是二义性（没填 vs 故意不设），
// 模式单选把意图说死，输入框只在对应模式下出现。
const OPEN_MODE_OPTIONS = [["now", "立即开放"], ["scheduled", "定时开放"]];
const CLOSE_MODE_OPTIONS = [["forever", "长期有效"], ["scheduled", "指定关闭时间"]];
const DURATION_MODE_OPTIONS = [["unlimited", "不限时"], ["limited", "限时作答"]];
const PAPER_TYPES = ["练习卷", "测试卷", "模拟卷", "竞赛卷", "作业卷"];

// 运行态徽章：「状态」（人为开关）与「运行态」（时间窗口）是两回事，表格只显示一列，停用优先。
const PHASE_LABEL = { not_started: ["未开始", "warn"], running: ["进行中", ""], ended: ["已结束", "gray"] };

function renderPills(container, name, options, value) {
  container.innerHTML = options
    .map(
      ([val, label]) => `<label class="pill"><input type="radio" name="${name}" value="${escapeHtml(String(val))}"${
        String(val) === String(value) ? " checked" : ""
      } /><span>${escapeHtml(label)}</span></label>`,
    )
    .join("");
}
const pillValue = (name) => document.querySelector(`input[name="${name}"]:checked`)?.value ?? "";

function linkWindow(link) {
  const open = link.open_at ? fmtTime(link.open_at) : "立即开放";
  const close = link.close_at ? fmtTime(link.close_at) : "长期有效";
  return `${open} ~ ${close}`;
}

function runBadge(link) {
  // 停用优先：一条 disabled 的链接同样可能落在时间窗口内，但老师首先要知道它被关了。
  if (link.status === "disabled") return '<span class="tag gray">已停用</span>';
  const [label, tone] = PHASE_LABEL[link.phase] || [link.phase || "—", "gray"];
  return `<span class="tag ${tone}">${label}</span>`;
}

// ==================== 复制 ====================
// 统一入口：clipboard API 不可用时回退 execCommand，再不行就明说。
export async function copyText(text, label = "内容") {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${label}已复制。`, "success");
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      toast(`${label}已复制。`, "success");
    } catch {
      toast(`复制失败，请手动选择复制。`, "error");
    } finally {
      area.remove();
    }
  }
}

// ==================== 完整地址的取用 ====================
// 有管理权的人：exam_url 内联在行数据里，直接用。
// 审核员 / 卷已转让的原作者：行里只有打码串，完整地址走 reveal-url，
// 服务端每次写一条审计再返回——留痕记的是「谁把地址拿走了」，不是「谁看了列表」。
async function resolveExamUrl(link) {
  if (link.exam_url) return { url: new URL(link.exam_url, location.origin).href, audited: false };
  const revealed = await adminRequest(`/links/${link.id}/reveal-url`, { method: "POST", body: "{}" });
  return { url: new URL(revealed.exam_url, location.origin).href, audited: true };
}

// ==================== 通知文案（纯函数，单测直接覆盖） ====================
// examUrl 由调用方先取好再传进来：完整地址可能要走一次 reveal 往返，纯函数不该自己去拿。
export function buildNoticeText(link, examUrl) {
  const lines = [`【${link.paper?.title || ""}】${link.name}`];
  const open = link.open_at ? fmtTime(link.open_at) : "即日起";
  const close = link.close_at ? fmtTime(link.close_at) : "长期有效";
  const duration = link.duration_minutes ? `（限时 ${link.duration_minutes} 分钟）` : "（不限时）";
  lines.push(`考试时间：${open} ~ ${close}${duration}`);
  lines.push(`作答次数：${link.attempt_limit === 0 ? "不限" : `${link.attempt_limit} 次`}`);
  lines.push(`链接：${examUrl}`);
  if (link.entry_open_minutes > 0) {
    lines.push(`提示：可提前 ${link.entry_open_minutes} 分钟进入候考页，需登录后作答。`);
  }
  return lines.join("\n");
}

// ==================== 表单有效值 ====================
// 模式单选决定对应输入是否生效：scheduled 模式下的空时间是「没填完」，
// now/forever/unlimited 模式下输入框里的残留值一律不生效。
export function effectiveForm(form) {
  return {
    ...form,
    open_at: form.open_mode === "scheduled" ? form.open_at : "",
    close_at: form.close_mode === "scheduled" ? form.close_at : "",
    duration_minutes: form.duration_mode === "limited" ? form.duration_minutes : "",
    entry_open_minutes: form.open_mode === "scheduled" ? form.entry_open_minutes : 0,
  };
}

// ==================== 规则冲突预检（纯函数，单测直接覆盖） ====================
// 与后端 ExamLinkPayload 同语义，先拦省一次往返。返回问题数组：
// 右栏「学员实际体验」就地亮出全部，保存时 toast 第一条并中止——不等保存才报错。
export function collectIssues(rawForm) {
  const form = effectiveForm(rawForm);
  const issues = [];
  if (rawForm.open_mode === "scheduled" && !form.open_at) issues.push("选择了定时开放，但还没填开放时间。");
  if (rawForm.close_mode === "scheduled" && !form.close_at) issues.push("选择了指定关闭时间，但还没填关闭时间。");
  if (rawForm.duration_mode === "limited" && !(Number(form.duration_minutes) >= 1)) {
    issues.push("选择了限时作答，但还没填考试时长。");
  }
  const remind = form.remind_minutes;
  const tokens = remind ? remind.split(/[,，、\s]+/).filter(Boolean) : [];
  if (tokens.some((token) => !/^\d+$/.test(token))) issues.push("考中提醒只能填分钟数，用逗号分隔（如 30,10,5）。");
  const minutes = [...new Set(tokens.map(Number))];
  if (minutes.some((m) => m < 1 || m > 1440)) issues.push("考中提醒的分钟数必须在 1–1440 之间。");
  if (minutes.length > 5) issues.push("考中提醒最多设置 5 个时间点。");
  const duration = form.duration_minutes === "" ? null : Number(form.duration_minutes);
  if (minutes.length && duration === null && !form.close_at) {
    issues.push("不限时且长期有效的链接算不出剩余时间，无法设置考中提醒。");
  }
  if (minutes.length && duration && Math.max(...minutes) >= duration) {
    issues.push("考中提醒的时间点必须小于考试时长，否则永远不会触发。");
  }
  if (rawForm.open_mode === "scheduled" && Number(form.entry_open_minutes) < 0) {
    issues.push("候考页提前时间不能为负。");
  }
  if (form.notice_ack_required && !form.notice.trim()) issues.push("要求确认已读时，考试须知不能为空。");
  if (form.open_at && form.close_at && new Date(form.open_at) >= new Date(form.close_at)) {
    issues.push("开放时间必须早于关闭时间。");
  }
  // 与后端 schedule_is_consistent 同语义：block 策略下窗口短于时长 = 没有任何人能开始作答。
  if (form.late_start_policy === "block" && form.open_at && form.close_at && duration) {
    const windowMinutes = (new Date(form.close_at) - new Date(form.open_at)) / 60_000;
    if (windowMinutes < duration) {
      issues.push("开放窗口短于考试时长，禁止开始策略下没有任何人能开始作答。");
    }
  }
  return issues;
}

// ==================== 学员实际体验（纯函数，单测直接覆盖） ====================
// 右栏固定预览：把「开放窗口 + 时长 + 迟到策略 + 提醒 + 结果公布」翻译成学员视角的
// 逐条事实——这比让老师对着输入框脑内推演可靠得多。冲突一并返回，就地亮警告。
export function buildStudentPreview(rawForm) {
  const form = effectiveForm(rawForm);
  const lines = [];
  const duration = form.duration_minutes === "" ? null : Number(form.duration_minutes);
  const open = form.open_at ? new Date(form.open_at) : null;
  const openValid = open && !Number.isNaN(open.getTime());
  const entryOpen = Number(form.entry_open_minutes) || 0;
  if (openValid) {
    if (entryOpen > 0) lines.push(`${fmtTime(new Date(open.getTime() - entryOpen * 60_000))} 可进候考页`);
    lines.push(`${fmtTime(open)} 正式开考`);
  } else {
    lines.push("立即开放：学员随时可进入作答");
  }
  lines.push(duration ? `限时 ${duration} 分钟` : "不限时作答");
  if (form.late_start_policy === "truncate" && duration && form.close_at) lines.push("迟到者按关闭时间缩短作答时长");
  if (form.late_start_policy === "block" && duration) lines.push(`剩余不足 ${duration} 分钟禁止进场`);
  if (form.late_start_policy === "overrun" && duration && form.close_at) lines.push("允许超出关闭时间作答满时长");
  if (form.remind_minutes) lines.push(`剩余 ${form.remind_minutes.split(/[,，、\s]+/).filter(Boolean).join("/")} 分钟提醒`);
  if (form.close_at) {
    const close = new Date(form.close_at);
    if (!Number.isNaN(close.getTime())) lines.push(`${fmtTime(close)} 统一关闭`);
  } else {
    lines.push("长期有效，不统一关闭");
  }
  const attempt = Number(form.attempt_limit) || 0;
  lines.push(attempt === 0 ? "不限作答次数" : attempt === 1 ? "只有 1 次作答机会" : `可作答 ${attempt} 次`);
  const SCORE_LINE = { immediate: "立即显示分数", after_close: "关闭后显示分数", never: "不显示分数" };
  const ANALYSIS_LINE = { after_submit: "交卷后显示解析", after_close: "关闭后显示解析", never: "不显示解析" };
  lines.push([SCORE_LINE[form.show_score], ANALYSIS_LINE[form.show_analysis]].filter(Boolean).join("，"));
  if (form.notice.trim()) lines.push(form.notice_ack_required ? "开考前须阅读并确认考试须知" : "开考前展示考试须知");
  return { lines, issues: collectIssues(rawForm) };
}

// ==================== 列表 ====================
let zone = ""; // "" = 全部；active / disabled
const rows = $("linkRows");

function renderLinkRows(items) {
  rows.innerHTML = items
    .map((link) => {
      const allowed = new Set(link.allowed_actions || []);
      const paper = link.paper || {};
      // 无管理权时行里只有打码串（exam_url 键整个不出现）——这里绝不能无条件 new URL()，
      // 一个 undefined 就会抛 TypeError 把整张表的渲染打断。
      const shown = link.exam_url ? new URL(link.exam_url, location.origin).href : link.exam_url_hint || "";
      // 完整地址要走一次留痕往返的人，也给复制按钮：复制动作不变，变的只是背后多一条审计。
      const canCopyUrl = allowed.has("copy") || allowed.has("reveal_url");
      // 两个复制动作放在各自内容旁边，而不是挤进操作列——操作列已有五项。
      const nameCell = `
        <div class="link-cell">
          <span class="link-name" title="${escapeHtml(link.name)}">${escapeHtml(link.name)}</span>
          <button class="copy-icon" type="button" data-copy-name="${link.id}" title="复制名称">⧉</button>
        </div>
        <div class="link-cell">
          <span class="link-url muted" title="${escapeHtml(shown)}">${escapeHtml(shown)}</span>
          ${canCopyUrl ? `<button class="copy-icon" type="button" data-copy-url="${link.id}" title="${allowed.has("copy") ? "复制链接" : "复制链接（取用将记入审计）"}">⧉</button>` : ""}
        </div>`;
      const actions = [
        allowed.has("edit")
          ? `<button class="btn-text link" type="button" data-edit="${link.id}">编辑</button>`
          : allowed.has("view")
            ? `<button class="btn-text link" type="button" data-view="${link.id}">查看</button>`
            : "", // reviewer 只读：不给查看入口的话，「view」就是个没人消费的死键
        // 看结果跟着读的权限走：能看到这条链接的人就能看这场成绩（reports 页按 link_id 直接展开）。
        allowed.has("view") ? `<a class="btn-text link" href="reports.html?link_id=${link.id}">成绩</a>` : "",
        allowed.has("reset_token") ? `<button class="btn-text link" type="button" data-reset="${link.id}">重置</button>` : "",
        allowed.has("delete") ? `<button class="btn-text link danger" type="button" data-delete="${link.id}">删除</button>` : "",
        canCopyUrl ? `<button class="btn-text link" type="button" data-copy-notice="${link.id}">复制通知</button>` : "",
      ].join("");
      // 启停开关：启用/停用收成一个控件，不再是一对此消彼长的文字按钮。
      // 能不能扳仍然只看 allowed_actions：active 时需要 disable，停用时需要 enable。
      const isActive = link.status === "active";
      const toggleable = isActive ? allowed.has("disable") : allowed.has("enable");
      const toggleCell = `
        <label class="switch">
          <input type="checkbox" data-toggle="${link.id}"${isActive ? " checked" : ""}${toggleable ? "" : " disabled"}
            aria-label="${isActive ? "停用" : "启用"}「${escapeHtml(link.name)}」" />
          <span class="slider"></span>
        </label>`;
      return `
      <tr data-row="${link.id}">
        <td>${nameCell}</td>
        <td class="cell-clip" title="${escapeHtml(paper.title || "")}">${escapeHtml(paper.paper_id_no || "—")}<br /><span class="muted">${escapeHtml(paper.title || "")}</span></td>
        <td class="cell-clip">${escapeHtml(linkWindow(link))}</td>
        <td>${link.duration_minutes ? `${link.duration_minutes}′` : "不限"}</td>
        <td>${link.attempt_limit === 0 ? "不限" : link.attempt_limit}</td>
        <td>${toggleCell}</td>
        <td>${runBadge(link)}</td>
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
  skeletonCols: 8,
  fetchPage: ({ page, size }) => {
    const params = new URLSearchParams({ page, size });
    if (zone) params.set("status", zone);
    const keyword = $("sKeyword").value.trim();
    if (keyword) params.set("keyword", keyword);
    for (const [id, key] of [["sPaper", "paper_id"], ["sPhase", "phase"], ["sOwner", "owner_id"]]) {
      const value = $(id).value;
      if (value) params.set(key, value);
    }
    return adminRequest(`/exam-links?${params}`);
  },
  renderRows: renderLinkRows,
  onLoaded: refreshCounts,
});

async function refreshCounts() {
  try {
    const { counts } = await adminRequest("/exam-link-counts");
    for (const [key, id] of [["all", "allCount"], ["active", "activeCount"], ["disabled", "disabledCount"]]) {
      $(id).textContent = counts[key] ?? 0;
    }
  } catch {
    /* 计数失败不该拖垮列表本身 */
  }
}

// ==================== 新建 / 编辑链接 Modal ====================
const linkMask = $("linkMask");
let papers = []; // 前 100 条缓存只供「新建时按筛选预选」兜底；两个组合框都走远程搜索
let paramPaper = null; // ?paper_id= 跳入时拉到的卷详情（新建预选用，可能不在缓存里）
let editingLink = null; // null = 新建
let readOnly = false; // reviewer / 别人的卷：只读查看
let snapshotAtOpen = "";
let releaseLink = null;

const emptyLink = () => ({
  paper_id: "", name: "",
  open_mode: "now", open_at: "", close_mode: "forever", close_at: "",
  duration_mode: "unlimited", duration_minutes: "",
  late_start_policy: "truncate", attempt_limit: 1, score_policy: "best",
  feedback_mode: "realtime", show_analysis: "after_submit", show_score: "immediate",
  shuffle_questions: false, shuffle_options: false,
  notice: "", notice_ack_required: false, entry_open_minutes: 0, remind_minutes: "", warn_unanswered: true,
});

function readForm() {
  return {
    paper_id: $("lPaper").value,
    name: $("lName").value.trim(),
    open_mode: pillValue("lOpenMode") || "now",
    open_at: $("lOpenAt").value,
    close_mode: pillValue("lCloseMode") || "forever",
    close_at: $("lCloseAt").value,
    duration_mode: pillValue("lDurationMode") || "unlimited",
    duration_minutes: $("lDuration").value,
    late_start_policy: pillValue("lLate"),
    attempt_limit: $("lAttempt").value,
    score_policy: pillValue("lPolicy"),
    feedback_mode: pillValue("lFeedback"),
    show_analysis: pillValue("lAnalysis"),
    show_score: pillValue("lShowScore"),
    shuffle_questions: $("lShuffleQ").checked,
    shuffle_options: $("lShuffleO").checked,
    notice: $("lNotice").value,
    notice_ack_required: $("lNoticeAck").checked,
    entry_open_minutes: $("lEntryOpen").value,
    remind_minutes: $("lRemind").value.trim(),
    warn_unanswered: $("lWarnUnanswered").checked,
  };
}
const snapshot = () => JSON.stringify(readForm());

// ==================== 联动：无意义组合不让它停在界面上 ====================
// 每一条都对应预览区少一句废话、保存时少一个死配置。
function syncModeVisibility() {
  const form = readForm();
  $("lOpenAtWrap").hidden = form.open_mode !== "scheduled";
  $("lCloseAtWrap").hidden = form.close_mode !== "scheduled";
  $("lDurationWrap").hidden = form.duration_mode !== "limited";
  // 立即开放 = 随时可进，「提前 N 分钟进候考页」无从谈起：清零并禁用。
  const entry = $("lEntryOpen");
  if (form.open_mode !== "scheduled") {
    entry.value = "0";
    entry.disabled = true;
  } else if (!readOnly) {
    entry.disabled = false;
  }
  // 长期有效没有「关闭时间」可截：截断策略禁用，已选中的自动退到禁止开始。
  const truncate = document.querySelector('input[name="lLate"][value="truncate"]');
  if (truncate) {
    if (form.close_mode !== "scheduled") {
      if (truncate.checked) document.querySelector('input[name="lLate"][value="block"]').checked = true;
      truncate.disabled = true;
    } else if (!readOnly) {
      truncate.disabled = false;
    }
  }
  // 只允许作答一次：取最高/最新/首次无从谈起，整行隐藏。
  $("lPolicyRow").hidden = Number(form.attempt_limit) === 1;
  // 须知为空时「必须阅读」自动禁用：勾选状态保留（预设可能已选中），
  // 写上须知后自动恢复可用；保存时空须知会强制按未勾选提交。
  $("lNoticeAck").disabled = readOnly || !form.notice.trim();
}

function refreshPreview() {
  syncModeVisibility();
  const { lines, issues } = buildStudentPreview(readForm());
  // aria-live 只在内容真正变化时更新：每次击键都重写文本会让读屏整段重念。
  const linesEl = $("previewLines");
  const linesKey = lines.join("\n");
  if (linesEl.dataset.key !== linesKey) {
    linesEl.dataset.key = linesKey;
    linesEl.innerHTML = lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  }
  const issuesEl = $("previewIssues");
  const issuesKey = issues.join("\n");
  if (issuesEl.dataset.key !== issuesKey) {
    issuesEl.dataset.key = issuesKey;
    issuesEl.hidden = issues.length === 0;
    issuesEl.innerHTML = issues.map((issue) => `<div>⚠ ${escapeHtml(issue)}</div>`).join("");
  }
}

function fillForm(state) {
  $("lName").value = state.name;
  $("lOpenAt").value = state.open_at;
  $("lCloseAt").value = state.close_at;
  $("lDuration").value = state.duration_minutes;
  $("lAttempt").value = state.attempt_limit;
  $("lShuffleQ").checked = state.shuffle_questions;
  $("lShuffleO").checked = state.shuffle_options;
  $("lNotice").value = state.notice;
  $("lNoticeAck").checked = state.notice_ack_required;
  $("lEntryOpen").value = state.entry_open_minutes;
  $("lRemind").value = state.remind_minutes;
  $("lWarnUnanswered").checked = state.warn_unanswered;
  // 模式优先取表单状态里的显式值（新建/预设），编辑既有链接时从字段值反推。
  renderPills($("lOpenModeGroup"), "lOpenMode", OPEN_MODE_OPTIONS, state.open_mode ?? (state.open_at ? "scheduled" : "now"));
  renderPills($("lCloseModeGroup"), "lCloseMode", CLOSE_MODE_OPTIONS, state.close_mode ?? (state.close_at ? "scheduled" : "forever"));
  renderPills($("lDurationModeGroup"), "lDurationMode", DURATION_MODE_OPTIONS, state.duration_mode ?? (state.duration_minutes ? "limited" : "unlimited"));
  renderPills($("lLateGroup"), "lLate", LATE_OPTIONS, state.late_start_policy);
  renderPills($("lPolicyGroup"), "lPolicy", POLICY_OPTIONS, state.score_policy);
  renderPills($("lFeedbackGroup"), "lFeedback", FEEDBACK_OPTIONS, state.feedback_mode);
  renderPills($("lAnalysisGroup"), "lAnalysis", ANALYSIS_OPTIONS, state.show_analysis);
  renderPills($("lShowScoreGroup"), "lShowScore", SHOW_SCORE_OPTIONS, state.show_score);
  refreshPreview();
}

// ==================== 所属试卷：远程搜索组合框 ====================
// 实现收在 admin-combobox.js（筛选栏共用同一份）；这里只留 Modal 的业务接线：
// 点选 → 记 id + 触发预设；重新输入 → 清除已选，保存时拿到的永远是有效 id。
let selectedPaper = null; // 当前 Modal 选中的卷对象（预设填充要读卷型）

function selectPaper(paper) {
  selectedPaper = paper;
  $("lPaper").value = paper.id;
  $("lPaperInput").value = paperLabel(paper);
  modalPicker.close();
  applyPaperPreset();
}

const modalPicker = createPaperPicker({
  input: $("lPaperInput"),
  list: $("lPaperList"),
  status: "published", // 新建只能选已发布卷：草稿没有可考内容，归档卷已锁定
  canOpen: () => !readOnly && !editingLink,
  focusKeyword: () => (selectedPaper ? "" : $("lPaperInput").value.trim()),
  onSelect: selectPaper,
  onInput: () => {
    // 重新输入 = 放弃已选：id 立即失效，保存时会被「请点选」拦下。
    selectedPaper = null;
    $("lPaper").value = "";
  },
  revertLabel: () => (selectedPaper ? paperLabel(selectedPaper) : ""),
});

function resetPaperPicker() {
  selectedPaper = null;
  $("lPaper").value = "";
  $("lPaperInput").value = "";
  modalPicker.close();
}

function openLinkModal(link, { viewOnly = false } = {}) {
  editingLink = link || null;
  readOnly = viewOnly;
  $("linkModalTitle").textContent = viewOnly ? "查看考试链接" : link ? "编辑考试链接" : "新建考试链接";
  // 编辑时所属试卷用纯只读文本：禁用的控件像「能改但没权限」，静态文本才是
  // 「这是事实」——链接不换卷，换卷等于换内容，那是另一条链接。
  $("lPaperPicker").hidden = Boolean(link);
  $("lPaperStatic").hidden = !link;
  if (link) {
    $("lPaperStatic").textContent = paperLabel({ ...(link.paper || {}), id: link.paper_id });
  }
  $("lPaperHint").textContent = "";
  if (link) {
    // hidden input 仍然记卷 id：快照/校验的读取路径不变。
    $("lPaper").value = link.paper_id;
    selectedPaper = link.paper || null;
    fillForm({
      ...emptyLink(),
      ...link,
      open_at: toLocalInput(link.open_at),
      close_at: toLocalInput(link.close_at),
      duration_minutes: link.duration_minutes ?? "",
      attempt_limit: link.attempt_limit,
      entry_open_minutes: link.entry_open_minutes,
      // 后端只存字段值，模式从值反推（空 = 立即开放 / 长期有效 / 不限时）。
      open_mode: link.open_at ? "scheduled" : "now",
      close_mode: link.close_at ? "scheduled" : "forever",
      duration_mode: link.duration_minutes ? "limited" : "unlimited",
    });
  } else {
    resetPaperPicker();
    fillForm(emptyLink());
    // ?paper_id= 跳入（或筛选栏已选卷）时新建直接预选这卷：缓存里没有就用
    // applyPaperParam 拉过的详情；都没有就退化成编号展示（卷型未知，不填预设）。
    const presetId = $("sPaper").value;
    if (presetId) {
      const cached = papers.find((item) => String(item.id) === presetId) ??
        (paramPaper && String(paramPaper.id) === presetId ? paramPaper : null);
      if (cached) {
        selectPaper(cached); // 预选同样触发预设填充
      } else {
        $("lPaper").value = presetId;
        $("lPaperInput").value = `试卷 #${presetId}`;
      }
    }
  }
  // 只读查看：锁全部输入、藏保存键。查看的是已落库内容，不存在「未保存的修改」。
  for (const el of $("linkModal").querySelectorAll("input, textarea, select")) el.disabled = viewOnly;
  syncModeVisibility(); // 上面一刀切会把联动禁用（截断策略/必须阅读等）冲掉，重跑一遍联动
  $("linkSaveBtn").hidden = viewOnly;
  $("linkCancel").textContent = viewOnly ? "关闭" : "取消";
  snapshotAtOpen = snapshot();
  releaseLink = openMask(linkMask, { focusSelector: viewOnly ? "#linkCancel" : "#lName" });
}

// 选中试卷后按卷型填充链接层预设（paper-presets.js 是纯数据表，这里只调统一入口）。
function applyPaperPreset() {
  if (editingLink) return;
  // 组合框选中的卷可能不在前 100 条缓存里（远程搜索结果），优先用选中对象。
  const paper = selectedPaper ?? papers.find((item) => String(item.id) === $("lPaper").value);
  if (!paper) return;
  const linkState = {};
  const preset = applyPreset({}, linkState, paper.paper_type);
  if (!preset) return;
  const current = readForm();
  fillForm({
    ...current,
    duration_minutes: linkState.duration_minutes ?? "",
    // 预设给的是字段值，模式要跟着显式切换，否则「填了时长却仍是不限时模式」，
    // 有效值一收拢时长就丢了。配了候考时间的预设是定时考试：切到定时开放，
    // 开放时间留空由预览区提醒老师补——这正是显式模式比「留空猜意图」强的地方。
    duration_mode: linkState.duration_minutes ? "limited" : "unlimited",
    open_mode: Number(linkState.entry_open_minutes) > 0 ? "scheduled" : current.open_mode,
    attempt_limit: linkState.attempt_limit,
    shuffle_questions: linkState.shuffle_questions,
    show_analysis: linkState.show_analysis,
    feedback_mode: linkState.feedback_mode,
    entry_open_minutes: linkState.entry_open_minutes,
    remind_minutes: linkState.remind_minutes,
    notice_ack_required: linkState.notice_ack_required,
  });
  $("lPaperHint").textContent = `已按「${preset.paper_type}」填充，可逐项调整`;
}

async function closeLinkModal() {
  if (!readOnly && snapshot() !== snapshotAtOpen) {
    const ok = await confirmDialog({
      title: "放弃未保存的修改？",
      message: "链接配置有改动尚未保存。",
      confirmText: "放弃修改",
      danger: true,
    });
    if (!ok) return;
  }
  closeMask(linkMask, releaseLink);
  releaseLink = null;
  readOnly = false;
}

async function saveLink() {
  const form = readForm();
  if (!editingLink && !form.paper_id) return toast("请搜索并从结果中点选所属试卷。", "error");
  if (!form.name) return toast("请填写链接名称。", "error");
  // 右栏已实时亮出全部冲突；保存时仍拦第一条——预检与后端同语义，省一次往返。
  const issues = collectIssues(form);
  if (issues.length) return toast(issues[0], "error");
  const eff = effectiveForm(form);
  const payload = {
    name: form.name,
    open_at: toIso(eff.open_at),
    close_at: toIso(eff.close_at),
    duration_minutes: eff.duration_minutes === "" ? null : Number(eff.duration_minutes),
    late_start_policy: form.late_start_policy,
    attempt_limit: Number(form.attempt_limit) || 0,
    score_policy: form.score_policy,
    penalty_minutes: 0,
    feedback_mode: form.feedback_mode,
    show_analysis: form.show_analysis,
    show_score: form.show_score,
    shuffle_questions: form.shuffle_questions,
    shuffle_options: form.shuffle_options,
    notice: form.notice,
    // 须知为空时勾选框禁用但状态保留（预设可能已选中）：提交按未勾选落库。
    notice_ack_required: form.notice.trim() ? form.notice_ack_required : false,
    entry_open_minutes: Number(eff.entry_open_minutes) || 0,
    remind_minutes: form.remind_minutes,
    warn_unanswered: form.warn_unanswered,
  };
  $("linkSaveBtn").disabled = true;
  $("linkState").textContent = "处理中…";
  try {
    if (editingLink) {
      await adminRequest(`/links/${editingLink.id}`, { method: "PUT", headers: ifMatch(editingLink.revision), body: JSON.stringify(payload) });
    } else {
      await adminRequest(`/papers/${form.paper_id}/links`, { method: "POST", body: JSON.stringify(payload) });
    }
    toast("已保存。", "success");
    closeMask(linkMask, releaseLink);
    releaseLink = null;
    list.reload();
  } catch (error) {
    toast(error.message || "保存失败。", "error");
  } finally {
    $("linkSaveBtn").disabled = false;
    $("linkState").textContent = "";
  }
}

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
  for (const id of ["sKeyword", "sPhase", "sOwner"]) $(id).value = "";
  clearPaperChip(); // 内含 setPaperFilter("")：组合框的 id/标签/清除钮一起复位
  list.page = 1;
  list.reload();
});
$("sKeyword").addEventListener("keydown", (e) => { if (e.key === "Enter") { list.page = 1; list.reload(); } });

$("newLinkBtn").addEventListener("click", () => openLinkModal(null));
$("linkClose").addEventListener("click", closeLinkModal);
$("linkCancel").addEventListener("click", closeLinkModal);
linkMask.addEventListener("click", (e) => { if (e.target === linkMask) closeLinkModal(); });
$("linkSaveBtn").addEventListener("click", saveLink);
// ==================== 筛选栏的所属试卷组合框 ====================
// 与新建 Modal 同一个 createPaperPicker：不限制 status（归档/草稿卷的链接也要能筛）。
// 点选即应用筛选并刷新；右侧 ✕ 清除。dataset.label 记录当前选中标签，供失焦还原。
function setPaperFilter(id, label = "") {
  $("sPaper").value = id || "";
  $("sPaperInput").value = label;
  $("sPaperInput").dataset.label = label;
  $("sPaperClear").hidden = !id;
}

createPaperPicker({
  input: $("sPaperInput"),
  list: $("sPaperList"),
  onSelect: (paper) => {
    setPaperFilter(paper.id, paperLabel(paper));
    list.page = 1;
    list.reload();
  },
  revertLabel: () => $("sPaperInput").dataset.label || "",
});

$("sPaperClear").addEventListener("click", () => {
  setPaperFilter("");
  $("paperChip").hidden = true; // 手动清除时连跳入芯片一起收掉，语义一致
  history.replaceState(null, "", location.pathname);
  list.page = 1;
  list.reload();
});
// 学员体验预览随表单实时重算：Modal 内任何输入都可能改变结论。
$("linkModal").addEventListener("input", refreshPreview);
$("linkModal").addEventListener("change", refreshPreview);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && isMaskOpen(linkMask)) closeLinkModal();
});

// 行操作：复制三件套 + 编辑 / 重置 / 删除（启停走开关的 change 事件，见下）。
rows.addEventListener("click", async (event) => {
  const btn = event.target.closest("button[data-copy-name],button[data-copy-url],button[data-copy-notice],button[data-view],button[data-edit],button[data-reset],button[data-delete]");
  if (!btn) return;
  const { copyName, copyUrl, copyNotice, view, edit, reset, delete: del } = btn.dataset;
  const id = copyName || copyUrl || copyNotice || view || edit || reset || del;
  const link = list.items.find((item) => String(item.id) === id);
  if (!link) return;
  try {
    if (copyName) {
      await copyText(link.name, "名称");
    } else if (copyUrl) {
      const { url, audited } = await resolveExamUrl(link);
      await copyText(url, "链接");
      // 明示优于暗记：被记了要当场知道，不能等事后翻审计才发现。
      if (audited) toast("本次取用已记入审计。", "info");
    } else if (copyNotice) {
      const { url, audited } = await resolveExamUrl(link);
      await copyText(buildNoticeText(link, url), "通知文案");
      if (audited) toast("本次取用已记入审计。", "info");
    } else if (edit) {
      openLinkModal(link);
    } else if (view) {
      openLinkModal(link, { viewOnly: true });
    } else if (reset) {
      const ok = await confirmDialog({ title: "重置链接", message: `确认重置「${link.name}」的链接？`, detail: "旧地址立即失效，同卷的其他链接不受影响。", confirmText: "确认重置", danger: true });
      if (!ok) return;
      await adminRequest(`/links/${link.id}/reset-token`, { method: "POST", headers: ifMatch(link.revision), body: "{}" });
      toast("已重置，请重新分发新地址。", "success");
      list.reload();
    } else if (del) {
      // 确认文案必须把「停用」这条退路写出来：老师想要的十有八九是暂停，不是销毁。
      const ok = await confirmDialog({
        title: "删除链接",
        message: `确认删除「${link.name}」？`,
        detail: "删除后不可恢复。只是想暂停请用「停用」——停用保留链接与后续的作答归属。",
        confirmText: "确认删除",
        danger: true,
      });
      if (!ok) return;
      await adminRequest(`/links/${link.id}`, { method: "DELETE", headers: ifMatch(link.revision) });
      toast("已删除。", "success");
      list.retreatIfEmpty();
      list.reload();
    }
  } catch (error) {
    toast(error.message || "操作失败。", "error");
    list.reload();
  }
});

// 启停开关：扳向「停」要确认（地址立即失效），取消就扳回去；扳向「开」不确认（可逆）。
// 能不能扳在渲染期就按 allowed_actions 决定了，这里不需要再判断权限。
rows.addEventListener("change", async (event) => {
  const toggle = event.target.closest("input[data-toggle]");
  if (!toggle) return;
  const link = list.items.find((item) => String(item.id) === toggle.dataset.toggle);
  if (!link) return;
  const turningOn = toggle.checked;
  try {
    if (turningOn) {
      await adminRequest(`/links/${link.id}/enable`, { method: "POST", headers: ifMatch(link.revision), body: "{}" });
      toast("已启用。", "success");
    } else {
      const ok = await confirmDialog({
        title: "停用链接",
        message: `确认停用「${link.name}」？`,
        detail: "停用后该地址立即失效，作答记录保留。",
        confirmText: "确认停用",
        danger: true,
      });
      if (!ok) {
        toggle.checked = true; // 取消：开关扳回原位
        return;
      }
      await adminRequest(`/links/${link.id}/disable`, { method: "POST", headers: ifMatch(link.revision), body: "{}" });
      toast("已停用。", "success");
    }
    list.reload();
  } catch (error) {
    toggle.checked = !turningOn; // 失败恢复原位（reload 也会重渲，双保险）
    toast(error.message || "操作失败。", "error");
    list.reload();
  }
});

// ==================== URL 参数（?paper_id= 从试卷页跳入） ====================

async function applyPaperParam() {
  const paperId = new URLSearchParams(location.search).get("paper_id");
  if (!paperId || !/^\d+$/.test(paperId)) return; // 非法参数直接忽略，照常加载全量列表
  // 卷可能对当前账号不可见：也要让筛选生效——标签退化成编号、芯片照常显示。
  // 绝不能静默回落到「全部」：那是没有异常提示的错误页面。
  let paper = papers.find((item) => String(item.id) === paperId);
  if (!paper) {
    try {
      paper = await adminRequest(`/papers/${paperId}`); // 拉得到就用真名，拉不到退化成编号
    } catch { /* 不可见或已删除：筛选照样按 id 生效 */ }
  }
  paramPaper = paper || null; // 新建链接时预选这卷（可能不在缓存里）
  const label = paper ? `${paper.paper_id_no || ""} ${paper.title}`.trim() : `试卷 #${paperId}`;
  // 组合框没有「补选项」的说法：id 进 hidden、标签进输入框，筛选照样按 id 生效。
  setPaperFilter(paperId, label);
  $("paperChipText").textContent = label;
  $("paperChip").hidden = false;
}

function clearPaperChip() {
  setPaperFilter("");
  $("paperChip").hidden = true;
  history.replaceState(null, "", location.pathname);
}

$("paperChipClose").addEventListener("click", () => {
  clearPaperChip();
  list.page = 1;
  list.reload();
});

// ==================== 启动 ====================
async function bootstrap() {
  syncZoneTabs();
  try {
    // 缓存仅供「新建时按筛选预选」兜底；筛选栏与 Modal 的组合框都走远程搜索。
    const data = await adminRequest("/papers?page=1&size=100");
    papers = data.items || [];
  } catch {
    /* 试卷清单失败不挡主列表 */
  }
  try {
    const { items } = await adminRequest("/paper-owners");
    $("sOwner").innerHTML = '<option value="">全部</option>' + items.map((o) => `<option value="${o.id}">${escapeHtml(o.display_name)}</option>`).join("");
  } catch {
    /* 负责人下拉失败不影响主列表 */
  }
  await applyPaperParam(); // 先落筛选，再加载列表——否则首屏会先闪一遍全量
  await Promise.allSettled([list.reload(), refreshCounts()]);}

bootstrap();
