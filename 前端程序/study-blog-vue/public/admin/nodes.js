// 节点管理页：课包目录编排（章节 / 课时两层，课时可跨章节拖动）。
//
// 布局是「左树右详情」而不是弹窗：编排目录是「改一节 → 看一眼树 → 再改一节」的连续
// 操作，每次弹窗遮住树会打断节奏。questions.html 用 Modal 是因为一道题的表单大到必须
// 独占屏幕，课时表单只有 6 个字段。
//
// 两种保存语义，刻意不同：
//   · 拖拽排序 = 立即保存（拖完就生效，不存在「忘了点保存」）；
//   · 课时表单 = 显式保存（切走时若有未保存改动会拦一次）。

import { initLayout } from "./admin-layout.js";
import { adminRequest, adminMe } from "./admin-api.js";
import { createSortable, destroyAll } from "./admin-dnd.js";
import { confirmDialog, escapeHtml, promptDialog, toast } from "./admin-ui.js";
import { renderMarkdown } from "./admin-markdown.js";
import { blocksRequest, scratchRequest, scratchMockEnabled } from "./admin-scratch-api.js";
import { scratchBlockConfigured, scratchBlockMeta, scratchDetailPayload, studioPreviewBase, studioPreviewUrl } from "./admin-scratch-core.js";

initLayout();

const $ = (id) => document.getElementById(id);
const courseId = Number(new URLSearchParams(location.search).get("course"));

let course = null;
let sections = [];
let videos = []; // GET /videos/options 的缓存
let selectedLessonId = null;
let original = ""; // 打开课时时的表单快照，用于脏检查
let readOnly = false;
let lessonBlocks = [];
let selectedBlockId = null;
let draftBlock = null;
let blockSortable = null;
let selectedLessonRecord = null;
let lessonModal = null;
let blockModal = null;
let blockDirty = false; // 编辑内容块弹窗的脏标记（与课时表单的 original 快照分开）
let deadlineDirty = false; // 截止时间可走普通保存或独立延长，单独跟踪避免误判其他设置
// 已发布课包的编辑锁定（阶段 1 口径：先下架再编辑）。reviewer 只读是 readOnly，
// 这是第二个独立开关——两者都禁编辑，但提示语不同。
let lockedByStatus = false;
const sortables = [];

// ==================== 入口守卫 ====================

if (!courseId) {
  $("noCourseTip").hidden = false;
  $("addSectionBtn").disabled = true;
  $("publishBtn").disabled = true;
  document.querySelector(".composer-stage-rail").hidden = true;
} else {
  $("nodesLayout").hidden = false;
  installLessonModal();
  installBlockModal();
  installComposerLayout();
  boot();
}

async function boot() {
  // 必须先拿到角色再渲染树：readOnly 决定拖拽装不装、按钮禁不禁用。
  // 放到 .then() 里并行会留一个窗口——reviewer 在那几百毫秒里能拖动，
  // 后端当然会 403，但让人拖了再报错是很差的体验。
  try {
    const me = await adminMe();
    readOnly = me?.capabilities?.content_edit !== true;
  } catch {
    /* 未登录时 admin-api 已跳登录页 */
  }
  if (readOnly) {
    for (const id of ["addSectionBtn", "publishBtn", "lessonSave", "lessonDelete"]) {
      $(id).disabled = true;
      $(id).title = "只读角色";
    }
  }
  try {
    videos = await adminRequest("/videos/options");
  } catch {
    videos = []; // 视频列表拿不到不该挡住整页；选择器会显示空态
  }
  await reloadTree();
}

// ==================== 目录树 ====================

async function reloadTree() {
  let data;
  try {
    data = await adminRequest(`/courses/${courseId}/sections`);
  } catch (error) {
    toast(error.message, "error");
    return;
  }
  course = data.course;
  sections = data.sections;
  // 已发布 = 锁编辑（阶段 1 口径）；下架后自动解锁，refresh 即生效
  lockedByStatus = course.status === "published";
  const locked = readOnly || lockedByStatus;

  $("courseTitle").textContent = course.title;
  const statusText = { draft: "草稿", published: "已发布", off_shelf: "已下架" }[course.status] || course.status;
  const minutes = sections.reduce(
    (sum, s) => sum + s.lessons.reduce((acc, l) => acc + (l.duration_minutes || 0), 0),
    0,
  );
  $("courseMeta").textContent = `${statusText} · ${sections.length} 章 · ${course.lesson_count} 节 · 约 ${minutes} 分钟`;
  $("publishBtn").textContent = course.status === "published" ? "已发布" : "发布课包";
  $("publishBtn").disabled = readOnly || course.status === "published";
  // 页面级操作按钮随锁定状态统一刷新（reviewer 或已发布都禁）
  for (const id of ["addSectionBtn", "lessonSave", "lessonDelete"]) {
    $(id).disabled = locked;
    $(id).title = locked ? (readOnly || lockedByStatus ? "只读角色" : "已发布课包请先下架再编辑") : "";
  }
  for (const id of ["composerAddBtn", "composerBatchBtn", "composerDropAdd", "readinessSaveBtn"]) {
    $(id).disabled = locked;
    $(id).title = locked ? (readOnly ? "只读角色" : "已发布课包请先下架再编辑") : "";
  }

  renderTree();
  refreshReadiness();
}

function lessonBadges(lesson) {
  const badges = [];
  const policy = lesson.open_policy || (lesson.is_trial ? "whole" : "closed");
  if (policy === "whole") badges.push('<span class="node-badge trial">试看</span>');
  if (policy === "first_n")
    badges.push(`<span class="node-badge trial" title="前 ${lesson.trial_block_count || 0} 个内容块可试看，其余需开通">前 ${lesson.trial_block_count || 0} 块试看</span>`);
  if (lesson.video && !lesson.video.playable) {
    const label = { draft: "待上传", uploaded: "待转码", transcoding: "转码中", failed: "转码失败" }[
      lesson.video.status
    ] || lesson.video.status;
    badges.push(`<span class="node-badge warn" title="视频${label}">⏳ ${escapeHtml(label)}</span>`);
  }
  if (lesson.id === selectedLessonId && lessonBlocks.length) {
    if (!lessonBlocks.every(blockConfigured)) {
      badges.push('<span class="node-badge err" title="当前课时仍有待配置内容块">待配置</span>');
    }
  } else if (!lesson.content_md && !lesson.video_id && !lesson.video_url) {
    // 未打开过的课时无法在目录接口里拿到 block 明细，不能误报“未配置”。
    badges.push('<span class="node-badge warn" title="打开课时检查内容块">待检查</span>');
  }
  return badges.join("");
}

function renderTree() {
  destroyAll(sortables);
  $("treeEmpty").hidden = sections.length > 0;

  $("sectionList").innerHTML = sections
    .map(
      (section) => `
      <li class="section-card dnd-item" data-id="${section.id}">
        <div class="section-head">
          <span class="drag-grip${readOnly || lockedByStatus ? " disabled" : ""}" title="拖拽调整章节顺序">⠿</span>
          <span class="section-title" data-act="rename-section" data-id="${section.id}">${escapeHtml(section.title)}</span>
          <span class="count">${section.lessons.length} 课时</span>
          <span class="spacer"></span>
          <button class="icon-btn" type="button" data-act="add-lesson" data-id="${section.id}" title="新增课时" ${
            readOnly || lockedByStatus ? "disabled" : ""
          }>＋</button>
          <button class="icon-btn" type="button" data-act="del-section" data-id="${section.id}" title="删除章节" ${
            readOnly || lockedByStatus ? "disabled" : ""
          }>✕</button>
        </div>
        <ul class="lesson-list" id="lessons-${section.id}">
          ${
            section.lessons.length
              ? section.lessons
                  .map(
                    (lesson) => `
                <li class="lesson-row dnd-item${lesson.id === selectedLessonId ? " selected" : ""}"
                    data-id="${lesson.id}" data-act="select-lesson">
                  <span class="drag-grip${readOnly || lockedByStatus ? " disabled" : ""}" title="拖拽排序，可拖到别的章节">⠿</span>
                  <span class="lesson-title">${escapeHtml(lesson.title)}</span>
                  ${lessonBadges(lesson)}
                </li>`,
                  )
                  .join("")
              : '<li class="lesson-empty">还没有课时，可以从别的章节拖进来</li>'
          }
        </ul>
      </li>`,
    )
    .join("");

  installSortables();
}

function installSortables() {
  if (readOnly || lockedByStatus) return;

  // 章节：只在自己内部排序
  sortables.push(
    createSortable($("sectionList"), {
      items: "li.section-card",
      group: "section",
      onReorder: async ({ orderedIds, revert }) => {
        await saveOrder(revert, () =>
          adminRequest(`/courses/${courseId}/sections/reorder`, {
            method: "POST",
            body: JSON.stringify({ ids: orderedIds.map(Number) }),
          }),
        );
      },
    }),
  );

  // 课时：所有章节的列表共享 group "lesson" → 可以互相拖
  for (const section of sections) {
    const container = $(`lessons-${section.id}`);
    if (!container) continue;
    sortables.push(
      createSortable(container, {
        items: "li.lesson-row",
        group: "lesson",
        parentId: section.id,
        onReorder: async (detail) => {
          await saveOrder(detail.revert, () =>
            detail.crossContainer
              ? adminRequest(`/lessons/${detail.movedId}/move`, {
                  method: "POST",
                  body: JSON.stringify({
                    target_section_id: Number(detail.toParentId),
                    ordered_ids: detail.orderedIds.map(Number),
                  }),
                })
              : adminRequest(`/sections/${detail.toParentId}/lessons/reorder`, {
                  method: "POST",
                  body: JSON.stringify({ ids: detail.orderedIds.map(Number) }),
                }),
          );
        },
      }),
    );
  }
}

async function saveOrder(revert, send) {
  $("treeSaving").hidden = false;
  try {
    await send();
    await reloadTree(); // 章节课时数、总时长要跟着变，整棵树重拉最省心
  } catch (error) {
    revert();
    toast(error.message, "error");
  } finally {
    $("treeSaving").hidden = true;
  }
}

// ==================== 树上的点击 ====================

$("sectionList").addEventListener("click", async (event) => {
  const trigger = event.target.closest("[data-act]");
  if (!trigger || trigger.disabled) return;
  const act = trigger.dataset.act;
  const id = Number(trigger.dataset.id);

  if (act === "select-lesson") {
    await selectLesson(id);
    return;
  }
  if (readOnly) return;

  if (act === "rename-section") {
    const section = sections.find((s) => s.id === id);
    const title = await promptDialog({
      title: "重命名章节",
      label: "章节名称",
      placeholder: section?.title || "",
      maxLength: 200,
      confirmText: "保存",
    });
    if (!title) return;
    await call(() => adminRequest(`/sections/${id}`, { method: "PUT", body: JSON.stringify({ title }) }), "已重命名");
    return;
  }

  if (act === "add-lesson") {
    const title = await promptDialog({
      title: "新增课时",
      label: "课时标题",
      placeholder: "如：1.1 什么是变量",
      maxLength: 200,
      confirmText: "创建",
    });
    if (!title) return;
    try {
      const created = await adminRequest(`/sections/${id}/lessons`, {
        method: "POST",
        body: JSON.stringify({ title, duration_minutes: 0, open_policy: "closed" }),
      });
      await reloadTree();
      await selectLesson(created.id, { force: true });
      $("lTitle").focus();
    } catch (error) {
      toast(error.message, "error");
    }
    return;
  }

  if (act === "del-section") {
    const section = sections.find((s) => s.id === id);
    const count = section?.lessons.length || 0;
    const ok = await confirmDialog({
      title: "删除章节",
      message: count ? `将同时删除其下 ${count} 个课时，不可恢复。` : "该章节下没有课时。",
      detail: "已上传的视频记录不受影响，只是失去与课时的绑定。",
      confirmText: "删除",
      danger: true,
    });
    if (!ok) return;
    if (section?.lessons.some((l) => l.id === selectedLessonId)) clearLessonForm();
    await call(() => adminRequest(`/sections/${id}`, { method: "DELETE" }), "已删除章节");
  }
});

$("addSectionBtn").addEventListener("click", async () => {
  const title = await promptDialog({
    title: "新建章节",
    label: "章节名称",
    placeholder: "如：第一章 · 入门",
    maxLength: 200,
    confirmText: "创建",
  });
  if (!title) return;
  await call(
    () => adminRequest(`/courses/${courseId}/sections`, { method: "POST", body: JSON.stringify({ title }) }),
    "已新建章节",
  );
});

$("publishBtn").addEventListener("click", async () => {
  try {
    await adminRequest(`/courses/${courseId}/publish`, { method: "POST", body: "{}" });
    toast("已发布");
    await reloadTree();
  } catch (error) {
    // 422 的 detail 是后端 _publish_checks 拼的中文清单，原样展示
    await confirmDialog({
      title: "还不能发布",
      message: "这个课包还差一些内容：",
      detail: error.message,
      confirmText: "知道了",
    });
  }
});

async function call(send, okText) {
  try {
    await send();
    toast(okText);
    await reloadTree();
  } catch (error) {
    toast(error.message, "error");
  }
}

// ==================== 课时表单 ====================

function findLesson(id) {
  for (const section of sections) {
    const hit = section.lessons.find((l) => l.id === id);
    if (hit) return hit;
  }
  return null;
}

// ==================== 内容编排工作区（真实内容块接口） ====================

// 5 种题型全开（与题库枚举 models.py:220 对齐），选题面板按 type 过滤走同一端点。
const PROBLEM_TYPES = ["choice", "multi_choice", "judge", "fill", "programming"];
const TYPE_LABEL = { choice: "选择", multi_choice: "多选", judge: "判断", fill: "填空", programming: "编程" };
// 题型 tab：第一项「全部」type 为空串（不传 type 即不过滤）
const PROBLEM_TABS = [{ label: "全部", type: "" }, ...PROBLEM_TYPES.map((t) => ({ label: TYPE_LABEL[t], type: t }))];
// 选题面板筛选状态：type / keyword / 分页。块表单重渲染时保持，避免切换题型后丢失已选上下文。
// loaded 标记：首开即拉一页；失败也置 true，避免渲染循环里反复请求。
// size=20（一屏滚动，减少翻页次数；后端 /problems/pickable size 上限 100）。cache 为本次弹窗会话内的
// 「type+keyword+page」组合缓存，弹窗关闭时清空（closeBlockModal），避免切回同条件重复请求。
let problemPicker = { type: "", keyword: "", page: 1, size: 20, total: 0, items: [], loaded: false, cache: new Map() };
let problemPickerReqSeq = 0; // 递增请求序号：快速切 tab/翻页时丢弃过期响应
let problemSearchTimer = null; // 关键词输入 300ms 防抖

const blockLabels = { markdown: "图文内容", video: "视频资源", practice: "课中练习（单题）", homework: "课后练习（试卷）", materials: "阅读资料", scratch: "Scratch 编程挑战" };
const blockIcons = { markdown: "▤", video: "▣", practice: "✎", homework: "✓", materials: "▱", scratch: "🧩" };

function newBlock(type) {
  const block = {
    block_type: type,
    title: blockLabels[type],
    required: true,
    // Gate B 路径闸（0034 起）：free=任意顺序学（默认）/ sequential=前面「必修且有权限」
    // 的块完成后才开。默认 free —— 闯关是老师主动开的开关，不是新建块的默认行为。
    unlock_rule: "free",
    markdown: { content_md: "" },
    video: { source_type: "platform", video_id: null, video_url: "", completion_percent: 100 },
    materials: [],
  };
  if (type === "scratch") {
    // 块配置只保存 challenge_id（任务书 21c）；title/status 是服务端回填的展示快照
    block.scratch = { challenge_id: null, challenge_title: null, challenge_status: null };
  } else if (type === "practice") {
    // v2 单题化：课中练习块挂 problem 单题明细（不再绑卷）。problem_type 由服务端回填快照。
    block.problem = { problem_id_no: null, problem_type: null, display_no: null, score: 0, attempt_limit: null, shuffle_options: true, show_analysis: true };
  } else {
    block.paper = { paper_id: null, mode: type, attempt_limit: null, shuffle_questions: true, shuffle_options: true, show_score: true, show_analysis: true, due_at: null };
  }
  return block;
}

function blockMeta(block) {
  if (block.block_type === "scratch") return scratchBlockMeta(block.scratch);
  if (block.block_type === "markdown") return "Markdown 图文";
  if (block.block_type === "video") {
    if (block.video?.source_type === "embed") return "外链视频 · iframe 嵌入";
    if (block.video?.source_type === "direct") return "外链视频 · MP4/HLS 直链";
    return block.video?.playable ? "平台视频 · 可播放" : "平台视频 · 待配置或转码";
  }
  if (block.block_type === "materials") return `${block.materials?.length || 0} 份已绑定资料`;
  if (block.block_type === "practice") {
    // 快照仅用于管理端列表展示（题型以题库实际值为准，见实现计划 v2 §3.1 说明 4）
    const p = block.problem;
    return p?.problem_id_no
      ? `题号 ${p.display_no || "自动"} · ${TYPE_LABEL[p.problem_type] || p.problem_type || "题目"} · ${p.score ?? 0} 分`
      : "尚未绑定题目";
  }
  return block.paper?.paper_id ? `已绑定试卷 #${block.paper.paper_id}` : "尚未绑定试卷";
}

function blockConfigured(block) {
  // scratch：未绑定「已发布」挑战一律待配置（草稿/已撤回也不算配好）
  if (block.block_type === "scratch") return scratchBlockConfigured(block.scratch);
  if (block.block_type === "markdown") return Boolean(block.markdown?.content_md?.trim());
  if (block.block_type === "video") {
    if (block.video?.source_type === "platform") return Boolean(block.video?.video_id);
    return Boolean(block.video?.video_url); // embed / direct 都要求外链地址
  }
  if (block.block_type === "materials") return (block.materials?.length || 0) > 0;
  // practice 绑定单题、homework 绑定试卷，各自独立判配置完成
  if (block.block_type === "practice") return Boolean(block.problem?.problem_id_no);
  return Boolean(block.paper?.paper_id);
}

async function loadLessonBlocks() {
  if (!selectedLessonId) return;
  const data = await blocksRequest(`/lessons/${selectedLessonId}/blocks`);
  lessonBlocks = data.blocks || [];
  if (selectedBlockId && !lessonBlocks.some((block) => block.id === selectedBlockId)) selectedBlockId = null;
  renderLessonComposer(data.lesson);
  renderBlockInspector();
}

function renderLessonComposer(lesson) {
  if (!lesson) return;
  blockSortable?.destroy?.();
  blockSortable = null;
  $("composerEmptyState").hidden = true;
  $("lessonComposer").hidden = false;
  $("composerLessonTitle").textContent = lesson.title || "未命名课时";
  $("composerLessonMeta").textContent = `${lesson.duration_minutes || 0} 分钟 · ${lessonBlocks.length} 个内容块 · 拖拽即时保存`;
  $("lessonBlockList").innerHTML = lessonBlocks.length
    ? lessonBlocks.map((block, index) => `
        <li class="lesson-block-card dnd-item${block.id === selectedBlockId ? " selected" : ""}" data-id="${block.id}">
          <span class="drag-grip${readOnly || lockedByStatus ? " disabled" : ""}" title="拖拽调整顺序">⠿</span>
          <span class="block-order">${index + 1}</span>
          <span class="block-icon" aria-hidden="true">${blockIcons[block.block_type]}</span>
          <span class="block-copy"><strong>${escapeHtml(block.title || blockLabels[block.block_type])}</strong><small>${escapeHtml(blockMeta(block))}</small></span>
          ${block.unlock_rule === "sequential" ? '<span class="block-state" title="按顺序解锁：学完前面全部必修内容后才开放">⇥ 顺序</span>' : ""}
          <span class="block-state${blockConfigured(block) ? "" : " warning"}">${blockConfigured(block) ? "已配置" : "待配置"}</span>
        </li>`).join("")
    : '<li class="composer-no-blocks">该课时还没有内容。通过右上角添加视频、图文、练习、作业或阅读资料。</li>';

  if (!readOnly && !lockedByStatus && lessonBlocks.length > 1) {
    blockSortable = createSortable($("lessonBlockList"), {
      items: "li.lesson-block-card",
      group: "lesson-block",
      onReorder: async ({ orderedIds, revert }) => {
        try {
          await blocksRequest(`/lessons/${selectedLessonId}/blocks/reorder`, { method: "POST", body: JSON.stringify({ ids: orderedIds.map(Number) }) });
          await loadLessonBlocks();
        } catch (error) {
          revert();
          toast(error.message, "error");
        }
      },
    });
  }
}

function addComposerBlock(type) {
  $("composerAddMenu").hidden = true;
  if (!selectedLessonId || readOnly || lockedByStatus) return;
  draftBlock = newBlock(type);
  selectedBlockId = null;
  renderLessonComposer(selectedLessonRecord);
  renderBlockInspector();
  openBlockModal();
  $("blockTitle")?.focus();
}

$("composerAddBtn").addEventListener("click", () => {
  $("composerAddMenu").hidden = !$("composerAddMenu").hidden;
});
$("composerDropAdd").addEventListener("click", () => addComposerBlock("markdown"));
$("composerAddMenu").addEventListener("click", (event) => {
  const button = event.target.closest("[data-add-block]");
  if (button) addComposerBlock(button.dataset.addBlock);
});
$("composerBatchBtn").addEventListener("click", () => {
  toast("批量删除/批量标签会放到资料库页；当前画布支持逐块编辑与拖拽排序。");
});
$("lessonBlockList").addEventListener("click", (event) => {
  const card = event.target.closest("[data-id]");
  if (!card) return;
  // 只读角色 / 已发布课包：入口拦截并提示，避免打开一个全部控件 disabled 的编辑弹窗
  // （此前弹窗照常打开，用户会看到题目列表却点不动——见选题面板 disabled 的误用反馈）
  if (readOnly || lockedByStatus) {
    toast(readOnly ? "只读角色，无法编辑内容块。" : "已发布课包请先下架再编辑。", "error");
    return;
  }
  draftBlock = null;
  selectedBlockId = Number(card.dataset.id);
  renderLessonComposer(selectedLessonRecord);
  renderBlockInspector();
  openBlockModal();
});

$("composerEditLesson").addEventListener("click", () => openLessonModal());

function refreshReadiness() {
  if (!course) return;
  const lessons = sections.flatMap((section) => section.lessons);
  const checks = [
    { ok: Boolean(course.title), text: "基本信息" },
    { ok: sections.length > 0, text: "目录结构" },
    { ok: lessons.length > 0, text: "课时目录" },
    { ok: lessonBlocks.length > 0 && lessonBlocks.every(blockConfigured), text: "当前课时内容" },
    { ok: lessonBlocks.some((block) => block.block_type === "practice" || block.block_type === "homework" || block.block_type === "scratch"), text: "当前课时练习或作业" },
  ];
  const passed = checks.filter((check) => check.ok).length;
  const percent = Math.round((passed / checks.length) * 100);
  $("readinessPercent").textContent = `${percent}%`;
  $("readinessSummary").textContent = `${passed} / ${checks.length} 项已完成`;
  $("readinessTrack").style.width = `${percent}%`;
  $("readinessItems").innerHTML = checks
    .map((check) => `<span class="${check.ok ? "done" : "pending"}">${check.ok ? "✓" : "!"} ${escapeHtml(check.text)}</span>`)
    .join("");
}

$("readinessSaveBtn").addEventListener("click", () => {
  if (isDirty()) {
    toast("当前课时还有未保存修改，请先保存。", "error");
    return;
  }
  toast("当前课时已保存。正式发布时仍由服务端对整包进行全量校验。");
});

function installComposerLayout() {
  const root = $("nodesLayout");
  const defaults = { tree: 280 };
  const setWidth = (name, value) => {
    root.style.setProperty(`--nodes-${name}-width`, `${value}px`);
    const handle = name === "tree" ? $("treeResizer") : null;
    if (handle) handle.setAttribute("aria-valuenow", String(value));
  };
  setWidth("tree", defaults.tree);

  const installHandle = (handle, name, min, max, invert = false) => {
    let value = name === "tree" ? defaults.tree : defaults.inspector;
    const update = (next) => {
      value = Math.max(min, Math.min(max, next));
      setWidth(name, value);
    };
    handle.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      const startX = event.clientX;
      const startValue = value;
      handle.setPointerCapture(event.pointerId);
      const move = (moveEvent) => update(startValue + (invert ? startX - moveEvent.clientX : moveEvent.clientX - startX));
      const end = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", end);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", end, { once: true });
    });
    handle.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const delta = event.key === "ArrowRight" ? 12 : -12;
      update(value + (invert ? -delta : delta));
    });
  };
  installHandle($("treeResizer"), "tree", 230, 420);
}

function installLessonModal() {
  // 「编辑课时」弹窗：只放课时设置（标题/摘要/时长/开放策略 + 删除/保存课时）。
  // 内容块配置已拆到独立的「编辑内容块」弹窗（installBlockModal），两层不再混在一起。
  const pane = document.querySelector(".lesson-pane");
  lessonModal = document.createElement("div");
  lessonModal.className = "modal-mask lesson-config-modal";
  lessonModal.hidden = true;
  lessonModal.innerHTML = `<section class="modal" role="dialog" aria-modal="true" aria-labelledby="lessonConfigTitle"><div class="modal-head"><h2 id="lessonConfigTitle">编辑课时</h2><button class="modal-close" type="button" aria-label="关闭" data-close-lesson-modal>×</button></div><div class="modal-body form-only"></div></section>`;
  lessonModal.querySelector(".modal-body").append(pane);
  document.body.append(lessonModal);
  lessonModal.addEventListener("click", async (event) => {
    if (event.target !== lessonModal && !event.target.closest("[data-close-lesson-modal]")) return;
    if (isDirty()) {
      const ok = await confirmDialog({ title: "关闭配置？", message: "课时基本信息有未保存修改。", confirmText: "放弃修改", danger: true });
      if (!ok) return;
      const lesson = findLesson(selectedLessonId);
      if (lesson) resetLessonForm(lesson);
    }
    lessonModal.classList.remove("show");
    lessonModal.hidden = true;
  });
}

function installBlockModal() {
  // 「编辑内容块」弹窗：只配置当前图文/视频/练习/作业/资料块，底部固定 删除/保存内容块。
  const pane = $("blockPane");
  // HTML 初始把它隐藏，避免旧三栏布局占位；移入独立弹窗后必须解除隐藏，
  // 否则 inspector 虽已渲染，仍会被祖先元素的 hidden 属性整体遮住。
  pane.hidden = false;
  blockModal = document.createElement("div");
  blockModal.className = "modal-mask block-config-modal";
  blockModal.hidden = true;
  blockModal.innerHTML = `<section class="modal" role="dialog" aria-modal="true" aria-labelledby="blockConfigTitle"><div class="modal-head"><h2 id="blockConfigTitle">编辑内容块</h2><button class="modal-close" type="button" aria-label="关闭" data-close-block-modal>×</button></div><div class="modal-body form-only"></div></section>`;
  blockModal.querySelector(".modal-body").append(pane);
  document.body.append(blockModal);
  blockModal.addEventListener("click", async (event) => {
    if (event.target !== blockModal && !event.target.closest("[data-close-block-modal]")) return;
    if (blockDirty || deadlineDirty) {
      const ok = await confirmDialog({ title: "关闭配置？", message: "当前内容块有未保存修改。", confirmText: "放弃修改", danger: true });
      if (!ok) return;
    }
    closeBlockModal();
  });
}

function openLessonModal() {
  if (!lessonModal || !selectedLessonId) return;
  lessonModal.hidden = false;
  requestAnimationFrame(() => lessonModal.classList.add("show"));
}

function openBlockModal() {
  if (!blockModal) return;
  blockDirty = false;
  deadlineDirty = false;
  blockModal.hidden = false;
  requestAnimationFrame(() => blockModal.classList.add("show"));
}

function closeBlockModal() {
  blockDirty = false;
  deadlineDirty = false;
  clearTimeout(problemSearchTimer);
  // 选题面板缓存只在本次弹窗会话内有效：关闭后失效，重开重新请求
  problemPicker.cache.clear();
  problemPicker.loaded = false;
  blockModal.classList.remove("show");
  blockModal.hidden = true;
}

function resetLessonForm(lesson) {
  $("lTitle").value = lesson.title;
  $("lSummary").value = lesson.summary || "";
  $("lDuration").value = String(lesson.duration_minutes || 0);
  const policy = lesson.open_policy || (lesson.is_trial ? "whole" : "closed");
  $("lOpenPolicy").value = policy;
  $("lTrialBlocks").value = String(lesson.trial_block_count || 1);
  $("lTrialBlocksField").hidden = policy !== "first_n";
  original = JSON.stringify(collect());
}

function collect() {
  // 课时元数据仍由旧 lesson endpoint 保存；内容已迁到 lesson blocks，必须原样带回
  // 旧字段，避免仅改标题/时长时误清历史课时内容。
  const legacy = selectedLessonRecord || {};
  const policy = $("lOpenPolicy").value;
  return {
    title: $("lTitle").value.trim(),
    summary: $("lSummary").value.trim() || null,
    content_md: legacy.content_md || null,
    video_id: legacy.video_id || null,
    video_url: legacy.video_url || null,
    duration_minutes: Number($("lDuration").value) || 0,
    open_policy: policy,
    trial_block_count: policy === "first_n" ? Number($("lTrialBlocks").value) || 1 : 0,
    trial_minutes: 0,
  };
}

const isDirty = () => $("lessonForm").hidden === false && JSON.stringify(collect()) !== original;

async function selectLesson(id, { force = false } = {}) {
  if (!force && id !== selectedLessonId && isDirty()) {
    const ok = await confirmDialog({
      title: "放弃未保存的修改？",
      message: "当前课时有未保存的修改，切换后会丢失。",
      confirmText: "放弃修改",
      danger: true,
    });
    if (!ok) return;
  }

  const lesson = findLesson(id);
  if (!lesson) return;
  selectedLessonId = id;
  selectedLessonRecord = lesson;
  lessonBlocks = [];
  selectedBlockId = null;
  draftBlock = null;

  $("lessonEmptyState").hidden = true;
  $("lessonForm").hidden = false;
  $("lTitle").value = lesson.title;
  $("lSummary").value = lesson.summary || "";
  $("lDuration").value = String(lesson.duration_minutes || 0);
  const policy = lesson.open_policy || (lesson.is_trial ? "whole" : "closed");
  $("lOpenPolicy").value = policy;
  $("lTrialBlocks").value = String(lesson.trial_block_count || 1);
  $("lTrialBlocksField").hidden = policy !== "first_n";
  renderLessonComposer(lesson);
  renderBlockInspector();
  original = JSON.stringify(collect());
  $("lessonSaveHint").textContent = "";

  for (const row of document.querySelectorAll(".lesson-row")) {
    row.classList.toggle("selected", Number(row.dataset.id) === id);
  }
  for (const el of ["lessonSave", "lessonDelete"]) $(el).disabled = readOnly || lockedByStatus;
  try {
    await loadLessonBlocks();
    refreshReadiness();
  } catch (error) {
    toast(`内容块载入失败：${error.message}`, "error");
  }
}

function clearLessonForm() {
  blockSortable?.destroy?.();
  blockSortable = null;
  selectedLessonId = null;
  selectedLessonRecord = null;
  lessonBlocks = [];
  selectedBlockId = null;
  draftBlock = null;
  original = "";
  $("lessonForm").hidden = true;
  $("lessonEmptyState").hidden = false;
  $("lessonComposer").hidden = true;
  $("composerEmptyState").hidden = false;
}

function activeBlock() {
  return draftBlock || lessonBlocks.find((block) => block.id === selectedBlockId) || null;
}

function toDateTimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function dateTimeLocalToIso(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function readInspector(block) {
  const root = $("blockInspector");
  if (!block || !root.querySelector("#blockTitle")) return block;
  block.title = root.querySelector("#blockTitle").value.trim();
  block.required = root.querySelector("#blockRequired").checked;
  block.unlock_rule = root.querySelector("#blockUnlockSeq")?.checked ? "sequential" : "free";
  if (block.block_type === "markdown") block.markdown.content_md = root.querySelector("#blockMarkdown").value;
  if (block.block_type === "video") {
    block.video.source_type = root.querySelector("#blockVideoSource").value;
    block.video.video_id = Number(root.querySelector("#blockVideoId").value) || null;
    // embed / direct 是两个独立输入框（不再共用一个 id，避免读到隐藏框的旧值）
    const urlInput = block.video.source_type === "embed"
      ? root.querySelector("#blockVideoEmbedUrl")
      : block.video.source_type === "direct"
        ? root.querySelector("#blockVideoDirectUrl")
        : null;
    block.video.video_url = urlInput ? urlInput.value.trim() || null : null;
    block.video.completion_percent = Number(root.querySelector("#blockCompletion").value) || 0;
  }
  if (block.block_type === "scratch") {
    // 只读 challenge_id；title/status 从选中项的 data-* 回填，仅为保存前刷新卡片展示
    const select = root.querySelector("#blockScratchChallenge");
    const option = select?.selectedOptions?.[0];
    block.scratch.challenge_id = Number(select?.value) || null;
    block.scratch.challenge_title = block.scratch.challenge_id ? option?.dataset.title || null : null;
    block.scratch.challenge_status = block.scratch.challenge_id ? option?.dataset.status || null : null;
  }
  if (block.block_type === "practice") {
    // 单题块：读取投放规则（problem_id_no/problem_type 走选题面板选中态，不在此读）
    const p = block.problem || (block.problem = {});
    p.display_no = root.querySelector("#blockDisplayNo").value.trim() || null;
    p.score = Number(root.querySelector("#blockScore").value) || 0;
    p.attempt_limit = Number(root.querySelector("#blockAttemptLimit").value) || null;
    p.shuffle_options = root.querySelector("#blockShuffleOptions").checked;
    p.show_analysis = root.querySelector("#blockShowAnalysis").checked;
  }
  if (block.block_type === "homework") {
    block.paper.paper_id = Number(root.querySelector("#blockPaperId").value) || null;
    block.paper.attempt_limit = Number(root.querySelector("#blockAttemptLimit").value) || null;
    block.paper.shuffle_questions = root.querySelector("#blockShuffleQuestions").checked;
    block.paper.shuffle_options = root.querySelector("#blockShuffleOptions").checked;
    block.paper.show_score = root.querySelector("#blockShowScore").checked;
    block.paper.show_analysis = root.querySelector("#blockShowAnalysis").checked;
    const dueInput = root.querySelector("#blockDueAt");
    if (dueInput.value !== dueInput.dataset.original) {
      block.paper.due_at = dateTimeLocalToIso(dueInput.value);
    }
  }
  return block;
}

function detailFor(block) {
  if (block.block_type === "scratch") return scratchDetailPayload(block.scratch);
  if (block.block_type === "markdown") return { markdown: block.markdown };
  if (block.block_type === "video") return { video: block.video };
  if (block.block_type === "practice") {
    // v2 单题化：practice 提交 problem 明细；problem_type 由服务端从题库回填，前端不传
    const p = block.problem || {};
    return {
      problem: {
        problem_id_no: p.problem_id_no,
        display_no: p.display_no || null, // 空 = 回退该课时内 practice 块间序号
        score: Number(p.score) || 0,
        attempt_limit: Number(p.attempt_limit) || null, // 0 = 不限（入库转 NULL）
        shuffle_options: p.shuffle_options !== false,
        show_analysis: p.show_analysis !== false,
      },
    };
  }
  if (block.block_type === "homework") return { paper: { ...block.paper, mode: block.block_type } };
  return null;
}

function renderBlockInspector() {
  const root = $("blockInspector");
  const block = activeBlock();
  if (!block) {
    root.innerHTML = '<div class="block-inspector-empty">从中间画布选择一个内容块，即可在这里配置。</div>';
    return;
  }
  const disabled = readOnly || lockedByStatus ? "disabled" : "";
  const isDraft = Boolean(draftBlock);
  const title = escapeHtml(block.title || blockLabels[block.block_type]);
  let detail = "";
  if (block.block_type === "markdown") {
    detail = `<div class="form-field"><label>图文正文 <b class="req">*</b></label><textarea id="blockMarkdown" rows="10" ${disabled}>${escapeHtml(block.markdown?.content_md || "")}</textarea><div class="md-preview" id="blockMarkdownPreview"></div></div>`;
  } else if (block.block_type === "video") {
    const videoOptions = videos.map((video) => `<option value="${video.id}" ${Number(video.id) === Number(block.video?.video_id) ? "selected" : ""}>${escapeHtml(video.title)}${video.playable ? "" : "（转码中）"}</option>`).join("");
    const source = block.video?.source_type || "platform";
    const isPlatform = source === "platform";
    detail = `<div class="form-field"><label>视频来源 <b class="req">*</b></label><select id="blockVideoSource" ${disabled}>
        <option value="platform" ${isPlatform ? "selected" : ""}>平台视频（自建，多码率 HLS）</option>
        <option value="embed" ${source === "embed" ? "selected" : ""}>外链 · 嵌入播放器（iframe，如 B 站/腾讯官方嵌入页）</option>
        <option value="direct" ${source === "direct" ? "selected" : ""}>外链 · 直链媒体（MP4 / HLS，交给 Video.js 播放）</option>
      </select></div>
      <div class="form-field" id="platformVideoField" ${isPlatform ? "" : "hidden"}><label>绑定平台视频 <b class="req">*</b></label><select id="blockVideoId" ${disabled}><option value="">请选择视频</option>${videoOptions}</select></div>
      <div class="form-field" id="embedVideoField" ${source === "embed" ? "" : "hidden"}><label>嵌入播放器地址 <b class="req">*</b></label><input id="blockVideoEmbedUrl" maxlength="512" value="${escapeHtml(block.video?.video_url || "")}" placeholder="https://player.bilibili.com/…（官方嵌入页）" ${disabled} /><span class="muted">学生端以 iframe 加载；直链 MP4 选「直链媒体」而不是这里，否则会报格式不支持。</span></div>
      <div class="form-field" id="directVideoField" ${source === "direct" ? "" : "hidden"}><label>直链媒体地址 <b class="req">*</b></label><input id="blockVideoDirectUrl" maxlength="512" value="${escapeHtml(block.video?.video_url || "")}" placeholder="https://…/lesson.mp4 或 …/index.m3u8" ${disabled} /><span class="muted">学生端交给 Video.js 播放，支持 MP4 / HLS。</span></div>
      <div class="form-field inline"><label>完成阈值</label><input id="blockCompletion" type="number" min="0" max="100" value="${block.video?.completion_percent ?? 100}" style="width:80px" ${disabled} /><span class="muted">%</span></div>
      <div class="form-field"><span class="muted">${isPlatform
        ? "学生看到这个百分比才算学完。观看时长由服务端按播放心跳记账，拖动进度条跳过的部分不计入。"
        : "⚠️ 完成阈值<b>对外链视频不生效</b>：第三方播放器的进度我们拿不到，服务端无从核对，学生点「完成」即算学完。需要按观看时长把关请改用平台视频。"}</span></div>`;
  } else if (block.block_type === "scratch") {
    // Scratch 块配置 = 绑定一个挑战（只存 challenge_id）。挑战内容在题库录入页的 Scratch 扩展维护。
    const s = block.scratch || {};
    const bound = Boolean(s.challenge_id);
    const published = s.challenge_status === "published";
    const statusHint = !bound
      ? "尚未绑定挑战，学生端会显示「尚未配置」。"
      : published
        ? `已绑定已发布挑战「${escapeHtml(s.challenge_title || `#${s.challenge_id}`)}」。`
        : `⚠️ 绑定的挑战尚未发布（当前状态：${escapeHtml(s.challenge_status || "未知")}），此块仍显示「待配置」，学生不可见。`;
    detail = `<div class="form-field"><label>绑定挑战 <b class="req">*</b></label>
        <div class="inline-picker">
          <select id="blockScratchChallenge" ${disabled}><option value="">加载挑战列表…</option></select>
          <a class="btn" href="questions.html?mode=scratch${scratchMockEnabled() ? "&scratch_mock=1" : ""}" target="_blank" rel="noopener">新建挑战</a>
        </div>
        <span class="muted">挑战的标题、规则、初始项目在「题库管理 → Scratch 挑战」维护；内容块只记录绑定关系。改动挑战状态后重新打开本弹窗可刷新状态。</span></div>
      <div class="form-field"><span class="muted">${statusHint}</span></div>
      <div class="form-field inline">
        <button class="btn" type="button" data-scratch-preview ${bound ? "" : "disabled"}>管理员预览</button>
        <a class="btn" href="scratch-submissions.html?challenge_id=${bound ? s.challenge_id : ""}${scratchMockEnabled() ? "&scratch_mock=1" : ""}" ${bound ? "" : "disabled aria-disabled='true'"}>查看学生作品</a>
        <span class="muted">预览为只读模式，不会写入任何学生项目。</span>
      </div>`;
  } else if (block.block_type === "materials") {
    const materials = block.materials || [];
    detail = `<div class="form-field"><label>已绑定资料 <span class="muted">（资料源文件保留在资料库）</span></label><ul class="bound-material-list">${materials.length ? materials.map((item) => `<li><span>${escapeHtml(item.display_name)}</span><button class="btn-text link danger" type="button" data-unbind-material="${item.material_id}" ${disabled}>解绑</button></li>`).join("") : '<li class="muted">还没有资料，发布会被拦截。</li>'}</ul><button class="btn" type="button" data-pick-material ${disabled}>＋ 从资料库选择</button></div>`;
  } else if (block.block_type === "practice") {
    // v2 单题化：课中练习弹窗 = 选题面板（复用 GET /problems/pickable）+ 单题投放规则
    const p = block.problem || {};
    const picked = p.problem_id_no
      ? { id_no: p.problem_id_no, type: p.problem_type, title: p.title || "" }
      : null;
    const maxPage = Math.max(1, Math.ceil(problemPicker.total / problemPicker.size));
    detail = `<div class="form-field"><label>绑定题目 <b class="req">*</b></label>
        <div class="problem-picker">
          <div class="problem-picker-tabs">${PROBLEM_TABS.map((tab) => `<button type="button" data-problem-type="${tab.type}" class="${problemPicker.type === tab.type ? "active" : ""}" ${disabled}>${tab.label}</button>`).join("")}</div>
          <div class="inline-picker"><input id="blockProblemKeyword" placeholder="按题号 / 题干 / 标题搜索" value="${escapeHtml(problemPicker.keyword)}" ${disabled} /><button class="btn" type="button" data-search-problems ${disabled}>搜索</button></div>
          <ul class="material-picker-results problem-picker-results">${renderProblemRows(picked, disabled)}</ul>
          <div class="problem-picker-pager"><button type="button" data-problem-page-prev ${problemPicker.page <= 1 || disabled ? "disabled" : ""}>‹ 上一页</button><span class="muted">第 ${problemPicker.page}/${maxPage} 页 · 共 ${problemPicker.total} 题</span><button type="button" data-problem-page-next ${problemPicker.page >= maxPage || disabled ? "disabled" : ""}>下一页 ›</button></div>
        </div>
        ${picked ? `<p class="muted">已绑定：${escapeHtml(picked.id_no)}（${TYPE_LABEL[picked.type] || picked.type || "题目"}）</p>` : ""}
        <span class="muted">⚠️ 选题面板只调已裁剪答案的只读端点，不会下发题目答案。</span></div>
      <div class="form-field"><label>题号（display_no）</label><input id="blockDisplayNo" maxlength="32" value="${escapeHtml(p.display_no || "")}" placeholder="留空 = 按该课时内练习块顺序自动编号" ${disabled} /><span class="muted">可填任意题号（如 3 / 3.1）；留空时学生端按本课时内练习块之间的顺序回退。</span></div>
      <div class="form-field inline"><label>分值</label><input id="blockScore" type="number" min="0" value="${p.score ?? 0}" style="width:80px" ${disabled} /><span class="muted">默认 0 分</span></div>
      <div class="form-field inline"><label>尝试次数</label><input id="blockAttemptLimit" type="number" min="0" value="${p.attempt_limit || 0}" style="width:80px" ${disabled} /><span class="muted">0 表示不限</span></div>
      <div class="check-grid"><label><input id="blockShuffleOptions" type="checkbox" ${p.shuffle_options !== false ? "checked" : ""} ${disabled} /> 选项乱序</label><label><input id="blockShowAnalysis" type="checkbox" ${p.show_analysis !== false ? "checked" : ""} ${disabled} /> 显示解析</label></div>`;
  } else {
    // homework —— 保持现状：课后练习弹窗仍走试卷选择器（绑卷）
    const paper = block.paper || {};
    const canExtendDeadline = !isDraft && Boolean(paper.due_at);
    const deadlineDisabled = canExtendDeadline ? (readOnly ? "disabled" : "") : disabled;
    detail = `<div class="form-field"><label>试卷 <b class="req">*</b></label><div class="inline-picker"><select id="blockPaperId" ${disabled}><option value="${paper.paper_id || ""}">${paper.paper_id ? `当前绑定：#${paper.paper_id}` : "请选择试卷"}</option></select><input id="blockPaperKeyword" placeholder="标题、数据库 ID 或卷号" ${disabled} /><button class="btn" type="button" data-search-papers ${disabled}>搜索</button></div><span class="muted">下拉默认仅显示最近 20 张已发布试卷；输入标题、ID 或卷号后再精确检索。</span></div>
      <div class="form-field"><label for="blockDueAt">作业截止时间</label><div class="inline-picker"><input id="blockDueAt" type="datetime-local" value="${toDateTimeLocal(paper.due_at)}" data-original="${toDateTimeLocal(paper.due_at)}" ${deadlineDisabled} />${canExtendDeadline ? `<button class="btn" type="button" data-extend-deadline ${readOnly ? "disabled" : ""}>延长截止时间</button>` : ""}</div><span class="muted">留空表示长期有效。已有作答后，普通保存不能修改此时间，请使用“延长截止时间”；已发布课包仍可执行延期。</span></div>
      <div class="form-field inline"><label>尝试次数</label><input id="blockAttemptLimit" type="number" min="0" value="${paper.attempt_limit || 0}" style="width:80px" ${disabled} /><span class="muted">0 表示不限</span></div>
      <div class="check-grid"><label><input id="blockShuffleQuestions" type="checkbox" ${paper.shuffle_questions !== false ? "checked" : ""} ${disabled} /> 题目乱序</label><label><input id="blockShuffleOptions" type="checkbox" ${paper.shuffle_options !== false ? "checked" : ""} ${disabled} /> 选项乱序</label><label><input id="blockShowScore" type="checkbox" ${paper.show_score !== false ? "checked" : ""} ${disabled} /> 显示分数</label><label><input id="blockShowAnalysis" type="checkbox" ${paper.show_analysis !== false ? "checked" : ""} ${disabled} /> 显示解析</label></div>`;
  }
  root.innerHTML = `<div class="block-inspector-head"><span class="eyebrow">${blockLabels[block.block_type]}</span><span class="muted">${isDraft ? "新建内容块" : `第 ${block.sort_order + 1} 块`}</span></div>
    <div class="form-field"><label>内容标题 <b class="req">*</b></label><input id="blockTitle" maxlength="200" value="${title}" ${disabled} /></div>
    <label class="check-line"><input id="blockRequired" type="checkbox" ${block.required !== false ? "checked" : ""} ${disabled} /> 必修（计入课时完成进度）</label>
    <label class="check-line"><input id="blockUnlockSeq" type="checkbox" ${block.unlock_rule === "sequential" ? "checked" : ""} ${disabled} /> 按顺序解锁（学完前面全部必修内容后才开放）</label>
    <span class="muted">「必修」决定进度分母；「按顺序解锁」决定能不能提前学。两者互不影响：选学块不会卡住后面的闯关块。</span>${detail}
    <div class="block-inspector-actions"><button class="btn danger" type="button" data-delete-block ${disabled}>${isDraft ? "取消新建" : "删除内容块"}</button><span class="spacer"></span><button class="btn primary" type="button" data-save-block ${disabled}>${isDraft ? "创建内容块" : "保存内容块"}</button></div>`;
  if (block.block_type === "markdown") renderBlockMarkdownPreview();
  if (block.block_type === "scratch") loadScratchOptions();
  if (block.block_type === "homework") loadPaperOptions();
  if (block.block_type === "practice") {
    // 首次打开选题面板：先渲染空列表，请求回来后重渲染填表
    // （重渲染前先 readInspector，防止请求期间用户已输入的值被覆盖）
    if (!problemPicker.loaded) {
      loadProblems().then(() => { readInspector(activeBlock()); renderBlockInspector(); });
    }
  }
}

// 选题面板题目列表渲染（单选行）。picked 为当前块已绑定题目的摘要。
function renderProblemRows(picked, disabled) {
  if (!problemPicker.items.length) {
    return '<li class="muted">没有可选的题目。</li>';
  }
  return problemPicker.items
    .map((item) => {
      const isPicked = picked && picked.id_no === item.problem_id_no;
      return `<li class="${isPicked ? "picked" : ""}"><button class="problem-row" type="button" data-pick-problem data-problem-no="${escapeHtml(item.problem_id_no)}" data-item-type="${escapeHtml(item.type)}" data-problem-title="${escapeHtml(item.title || item.stem_text || "")}" ${disabled}>${escapeHtml(item.problem_id_no)} · ${escapeHtml(item.title || item.stem_text || "")}<small>${TYPE_LABEL[item.type] || item.type} · ${escapeHtml(item.difficulty || "")}</small></button></li>`;
    })
    .join("");
}

// 选题面板数据源：⚠️ 安全红线（papers.js:9-11）——只调已裁剪答案的 /problems/pickable，
// 绝不调 GET /problems/{id}（返回完整答案/解析/参考代码）。需要更多题干字段时找后端扩展 pickable。
async function loadProblems() {
  // 竞态保护：每次请求取递增序号，响应回来时若已不是最新则直接丢弃，防止旧响应覆盖新列表
  const seq = ++problemPickerReqSeq;
  const key = JSON.stringify([problemPicker.type, problemPicker.keyword, problemPicker.page]);
  const cached = problemPicker.cache.get(key);
  if (cached) {
    problemPicker.total = cached.total;
    problemPicker.items = cached.items;
    problemPicker.loaded = true;
    return;
  }
  problemPicker.loaded = true;
  try {
    const params = new URLSearchParams({ page: String(problemPicker.page), size: String(problemPicker.size) });
    if (problemPicker.type) params.set("type", problemPicker.type);
    if (problemPicker.keyword) params.set("keyword", problemPicker.keyword);
    const data = await adminRequest(`/problems/pickable?${params}`);
    if (seq !== problemPickerReqSeq) return; // 过期响应直接丢弃
    problemPicker.total = data.total || 0;
    problemPicker.items = data.items || [];
    problemPicker.cache.set(key, { items: problemPicker.items, total: problemPicker.total });
  } catch (error) {
    if (seq !== problemPickerReqSeq) return;
    problemPicker.items = [];
    problemPicker.total = 0;
    toast(error.message, "error");
  }
}

// 挑战绑定下拉：列出全部挑战并标注状态；未发布挑战可绑但块仍「待配置」，
// 防止老师误以为绑上草稿就配好了（任务书 21c：未绑定已发布挑战时显示「待配置」）。
async function loadScratchOptions() {
  const select = $("blockScratchChallenge");
  if (!select) return;
  const block = activeBlock();
  const chosen = String(block?.scratch?.challenge_id || "");
  try {
    const data = await scratchRequest("/scratch/challenges/options");
    const items = data.items || [];
    const statusText = { draft: "草稿", published: "已发布", withdrawn: "已撤回" };
    select.innerHTML = `<option value="">请选择挑战</option>${items
      .map((c) => `<option value="${c.id}" data-title="${escapeHtml(c.title)}" data-status="${escapeHtml(c.status)}" ${String(c.id) === chosen ? "selected" : ""}>#${c.id} ${escapeHtml(c.title)}（${statusText[c.status] || c.status}）</option>`)
      .join("")}`;
    if (chosen && !items.some((c) => String(c.id) === chosen)) {
      // 已绑定的挑战被删了：保留原值并明示，保存时由老师决定去留
      select.insertAdjacentHTML("beforeend", `<option value="${chosen}" selected>当前绑定：#${chosen}（挑战已不存在）</option>`);
    }
  } catch (error) {
    select.innerHTML = `<option value="${chosen}">挑战列表加载失败</option>`;
    toast(error.message, "error");
  }
}

async function renderBlockMarkdownPreview() {
  const textarea = $("blockMarkdown");
  const preview = $("blockMarkdownPreview");
  if (!textarea || !preview) return;
  try { await renderMarkdown(preview, textarea.value || ""); } catch { preview.textContent = "预览渲染失败（不影响保存）。"; }
}

async function loadPaperOptions(keyword = $("blockPaperKeyword")?.value.trim() || "") {
  try {
    const data = await adminRequest(`/papers/options?keyword=${encodeURIComponent(keyword)}&page_size=20`);
    const select = $("blockPaperId");
    if (!select) return;
    const chosen = select.value;
    const rows = data.items || [];
    const keep = chosen && !rows.some((paper) => String(paper.id) === chosen) ? `<option value="${chosen}">当前绑定：#${chosen}</option>` : "";
    select.innerHTML = `<option value="">请选择试卷</option>${keep}${rows.map((paper) => `<option value="${paper.id}" ${String(paper.id) === chosen ? "selected" : ""}>${escapeHtml(paper.paper_id_no || `#${paper.id}`)} · ${escapeHtml(paper.title)}（${paper.question_count} 题）</option>`).join("")}`;
    if (keyword && !rows.length) toast("没有匹配的已发布试卷。", "error");
  } catch (error) { toast(error.message, "error"); }
}

async function saveActiveBlock() {
  const block = readInspector(activeBlock());
  if (!block || !block.title) { toast("请填写内容标题。", "error"); $("blockTitle")?.focus(); return; }
  if (block.block_type === "markdown" && !block.markdown.content_md.trim()) { toast("请填写图文正文。", "error"); return; }
  if (block.block_type === "video") {
    const ok = block.video.source_type === "platform" ? Boolean(block.video.video_id) : Boolean(block.video.video_url);
    if (!ok) { toast("请完整配置视频来源。", "error"); return; }
  }
  if (block.block_type === "practice" && !block.problem?.problem_id_no) { toast("请先绑定一道题目。", "error"); return; }
  if (block.block_type === "homework" && !block.paper?.paper_id) { toast("请绑定一张试卷。", "error"); return; }
  const payload = { block_type: block.block_type, title: block.title, required: block.required, unlock_rule: block.unlock_rule || "free", detail: detailFor(block) };
  try {
    const saved = draftBlock
      ? await blocksRequest(`/lessons/${selectedLessonId}/blocks`, { method: "POST", body: JSON.stringify(payload) })
      : await blocksRequest(`/lesson-blocks/${block.id}`, { method: "PUT", body: JSON.stringify(payload) });
    draftBlock = null;
    selectedBlockId = saved.id;
    toast("内容块已保存");
    await loadLessonBlocks();
  } catch (error) { toast(error.message, "error"); }
}

async function extendActiveDeadline() {
  const block = activeBlock();
  if (!block || draftBlock || block.block_type !== "homework") return;
  if (blockDirty) {
    toast("请先保存其他作业设置，再单独延长截止时间。", "error");
    return;
  }
  const dueAt = dateTimeLocalToIso($("blockDueAt")?.value);
  if (!dueAt) {
    toast("请选择新的作业截止时间。", "error");
    $("blockDueAt")?.focus();
    return;
  }
  const current = new Date(block.paper.due_at).getTime();
  const next = new Date(dueAt).getTime();
  if (!Number.isFinite(next) || next <= current || next <= Date.now()) {
    toast("新的作业截止时间必须晚于当前截止时间和当前时间。", "error");
    $("blockDueAt")?.focus();
    return;
  }
  const confirmed = await confirmDialog({
    title: "延长作业截止时间",
    message: `确认延长至 ${new Date(dueAt).toLocaleString("zh-CN")}？`,
    detail: "系统会同时更新所有尚未提交的作答；已提交和已收卷记录保持不变。",
    confirmText: "确认延长",
  });
  if (!confirmed) return;
  try {
    const result = await adminRequest(`/lesson-blocks/${block.id}/extend-deadline`, {
      method: "POST", body: JSON.stringify({ due_at: dueAt }),
    });
    block.paper.due_at = result.block.paper.due_at;
    blockDirty = false;
    deadlineDirty = false;
    toast(`截止时间已延长，已同步 ${result.updated_ongoing_attempts} 份未提交作答`);
    renderBlockInspector();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function deleteActiveBlock() {
  const block = activeBlock();
  if (!block) return;
  if (draftBlock) { draftBlock = null; renderBlockInspector(); return; }
  const ok = await confirmDialog({ title: "删除内容块", message: `确定删除「${block.title || blockLabels[block.block_type]}」吗？`, detail: "仅删除课时内的编排与关联，不会删除视频、试卷、题库题目或资料库源文件。", confirmText: "删除", danger: true });
  if (!ok) return;
  try {
    await blocksRequest(`/lesson-blocks/${block.id}`, { method: "DELETE" });
    selectedBlockId = null;
    blockDirty = false;
    toast("内容块已删除");
    closeBlockModal();
    await loadLessonBlocks();
  } catch (error) { toast(error.message, "error"); }
}

function formatBytes(size) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

// 从资料库选择（2026-08-10 改造）：目录树懒加载 + 按文件夹按需加载。
// 之前是打开即全库检索，资料量大了既不友好也不符合「先目录后文件、按需加载」的标准。现在：
//   1. 左侧目录树：打开只拉根层（GET /material-folders?parent_id=），点带子节点的文件夹才按
//      parent_id 懒加载直接子目录，并缓存到 folderChildren（同 materials.js 范式），收起再展开不重复请求；
//   2. 右侧资料列表：按所选文件夹 GET /materials?folder_id=…&page=… 分页加载，底部「加载更多」追加；
//   3. 搜索框兜底：输入关键词走全库检索，顶部显示「搜索：xxx」上下文，可一键清空回到目录浏览。
// 默认视图为「全部资料」（不传 folder_id）：与改造前打开即见全部的行为一致，用户再沿目录逐层下钻；
// 不默认「未分类」——未分类只适合专门筛选，作默认会让多数用户一进来就看不到已分类资料。
async function openMaterialPicker(block) {
  if (!block?.id) { toast("请先创建内容块，再绑定资料。", "error"); return; }
  const mask = document.createElement("div");
  mask.className = "modal-mask show material-picker-mask";
  mask.innerHTML = `<section class="modal narrow" role="dialog" aria-modal="true" aria-label="从资料库选择"><div class="modal-head"><h2>从资料库选择</h2><button class="modal-close" type="button" data-close-picker>×</button></div><div class="modal-body form-only">
    <div class="inline-picker"><input data-material-keyword placeholder="按文件名搜索资料" /><button class="btn" type="button" data-search-material>搜索</button></div>
    <p class="muted material-picker-hint">仅可选择已就绪资料；资料不会被复制，解绑不会删除资料库源文件。</p>
    <p class="material-picker-context" data-material-context></p>
    <div class="material-picker-body">
      <div class="material-picker-folders import-folder-picker"><ol data-material-tree></ol></div>
      <div class="material-picker-main">
        <ul class="material-picker-results" data-material-results></ul>
        <button class="btn" type="button" data-load-more hidden>加载更多</button>
      </div>
    </div>
  </div><div class="modal-foot"><button class="btn" type="button" data-close-picker>取消</button><span class="spacer"></span><button class="btn primary" type="button" data-apply-material>绑定所选资料</button></div></section>`;
  document.body.append(mask);
  const selected = new Set((block.materials || []).map((item) => Number(item.material_id)));
  const results = mask.querySelector("[data-material-results]");
  const tree = mask.querySelector("[data-material-tree]");
  const context = mask.querySelector("[data-material-context]");
  const loadMoreBtn = mask.querySelector("[data-load-more]");

  // ---- 目录树状态：folderChildren 缓存「父 id → 直接子文件夹列表」，expanded 记展开态 ----
  const folderChildren = new Map();
  const expanded = new Set();
  let folderId = "";   // 当前资料视图：""=全部、-1=未分类、>0=文件夹 id
  let folderName = "全部资料";
  let searching = "";  // 非空 = 处于全库搜索模式
  let page = 1;
  let total = 0;
  let reqSeq = 0;      // 请求序号：切换文件夹/搜索时丢弃过期响应

  // 渲染目录树（「全部/未分类」两个固定节点 + 各层文件夹；有子节点的才渲染展开箭头）
  const folderRows = (parentId, depth) =>
    (folderChildren.get(String(parentId)) || []).map((folder) => {
      const open = expanded.has(folder.id);
      const children = open ? folderRows(folder.id, depth + 1) : "";
      const toggle = folder.child_count
        ? `<button class="folder-toggle" type="button" data-toggle-folder="${folder.id}" aria-label="展开或收起">${open ? "▾" : "▸"}</button>`
        : '<span class="folder-toggle-placeholder"></span>';
      const active = String(folder.id) === String(folderId);
      return `<li>${toggle}<button class="folder-name ${active ? "active" : ""}" style="padding-left:${8 + depth * 16}px" type="button" data-pick-folder="${folder.id}" data-folder-label="${escapeHtml(folder.name)}" title="${escapeHtml(folder.name)}">📁 ${escapeHtml(folder.name)}<small>${folder.asset_count || 0}</small></button>${children ? `<ol>${children}</ol>` : ""}</li>`;
    }).join("");

  const renderTree = () => {
    tree.innerHTML = `<li><span class="folder-toggle-placeholder"></span><button class="folder-name ${folderId === "" ? "active" : ""}" style="padding-left:8px" type="button" data-pick-folder="" data-folder-label="全部资料">🗂 全部资料</button></li><li><span class="folder-toggle-placeholder"></span><button class="folder-name ${folderId === -1 ? "active" : ""}" style="padding-left:8px" type="button" data-pick-folder="-1" data-folder-label="未分类">🗂 未分类</button></li>${folderRows("", 0)}`;
  };

  // 按 parent_id 拉取直接子目录并缓存（parent_id=""=根层）；成功后刷新树
  const loadFolders = async (parentId) => {
    try {
      const data = await adminRequest(`/material-folders?parent_id=${encodeURIComponent(parentId)}`);
      folderChildren.set(String(parentId), data.items || []);
      renderTree();
    } catch (error) { toast(error.message, "error"); }
  };

  const materialRow = (item) => `<li><label><input type="checkbox" value="${item.id}" ${selected.has(Number(item.id)) ? "checked" : ""} ${item.status !== "ready" ? "disabled" : ""} /><span><strong>${escapeHtml(item.display_name)}</strong><small>${escapeHtml(item.asset_type)} · ${formatBytes(item.size_bytes)} · ${item.status === "ready" ? "可用" : "处理中"}</small></span></label></li>`;

  // 按当前「搜索关键词 / 文件夹」拉取资料列表；append=true 时追加上一页
  const loadMaterials = async ({ append = false } = {}) => {
    const seq = ++reqSeq;
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (searching) params.set("keyword", searching);
    else if (folderId !== "") params.set("folder_id", String(folderId));
    if (!append) { results.innerHTML = '<li class="muted">正在载入资料…</li>'; loadMoreBtn.hidden = true; }
    try {
      const data = await adminRequest(`/materials?${params}`);
      if (seq !== reqSeq) return; // 已切换到别的文件夹/搜索，丢弃过期响应
      total = data.total || 0;
      const rows = (data.items || []).map(materialRow).join("");
      if (append) { if (rows) results.insertAdjacentHTML("beforeend", rows); }
      else results.innerHTML = rows || `<li class="muted">${searching ? "没有匹配的搜索结果。" : "这个文件夹还没有资料。"}</li>`;
      loadMoreBtn.hidden = page * 50 >= total;
      if (!loadMoreBtn.hidden) loadMoreBtn.textContent = `加载更多（已显示 ${Math.min(page * 50, total)} / ${total}）`;
      renderContext();
    } catch (error) {
      if (seq !== reqSeq) return;
      if (append) toast(error.message, "error");
      else results.innerHTML = `<li class="field-error">${escapeHtml(error.message)}</li>`;
    }
  };

  // 顶部上下文：搜索模式显示「搜索：xxx + 清空」，目录模式显示当前文件夹
  const renderContext = () => {
    context.hidden = false;
    context.innerHTML = searching
      ? `搜索：<strong>“${escapeHtml(searching)}”</strong> <button class="btn-text link" type="button" data-clear-search>清空并回到目录浏览</button>`
      : `当前：<strong>${escapeHtml(folderName)}</strong>（${total ? `共 ${total} 份资料` : "暂无资料"}）`;
  };

  const close = () => mask.remove();
  const search = () => {
    const keyword = mask.querySelector("[data-material-keyword]").value.trim();
    if (!keyword) { toast("请输入搜索关键词。", "error"); return; }
    searching = keyword;
    page = 1;
    renderTree();
    loadMaterials();
  };

  mask.addEventListener("click", async (event) => {
    if (event.target === mask || event.target.closest("[data-close-picker]")) { close(); return; }
    if (event.target.closest("[data-search-material]")) { search(); return; }
    if (event.target.closest("[data-clear-search]")) {
      searching = "";
      mask.querySelector("[data-material-keyword]").value = "";
      page = 1;
      renderTree();
      await loadMaterials();
      return;
    }
    // 目录树：展开/收起（首次展开时按需拉取直接子目录并缓存）
    const toggle = event.target.closest("[data-toggle-folder]");
    if (toggle) {
      const id = Number(toggle.dataset.toggleFolder);
      if (expanded.has(id)) { expanded.delete(id); renderTree(); } // 收起不清缓存，再展开不重复请求
      else {
        expanded.add(id);
        if (!folderChildren.has(String(id))) await loadFolders(id);
        else renderTree();
      }
      return;
    }
    // 目录树：选中文件夹 → 按需加载该文件夹资料
    const pick = event.target.closest("[data-pick-folder]");
    if (pick) {
      const raw = pick.dataset.pickFolder;
      folderId = raw === "" ? "" : Number(raw);
      folderName = pick.dataset.folderLabel || "资料";
      searching = "";
      mask.querySelector("[data-material-keyword]").value = "";
      page = 1;
      renderTree();
      await loadMaterials();
      return;
    }
    if (event.target.closest("[data-load-more]")) {
      // 追加中禁用按钮，避免快速连点造成同页重复追加
      if (page * 50 >= total || loadMoreBtn.disabled) return;
      page += 1;
      loadMoreBtn.disabled = true;
      await loadMaterials({ append: true });
      loadMoreBtn.disabled = false;
      return;
    }
    if (event.target.closest("[data-apply-material]")) {
      const ids = [...mask.querySelectorAll("input[type=checkbox]:checked")].map((input) => Number(input.value));
      if (!ids.length) { toast("请至少选择一份资料。", "error"); return; }
      try { await adminRequest(`/lesson-blocks/${block.id}/materials`, { method: "POST", body: JSON.stringify({ material_ids: ids }) }); close(); toast("资料已绑定"); await loadLessonBlocks(); } catch (error) { toast(error.message, "error"); }
    }
  });
  mask.querySelector("[data-material-keyword]").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); search(); } });
  renderTree();
  // 打开弹窗并行加载：根层目录 + 默认「全部资料」第一页
  await Promise.all([loadFolders(""), loadMaterials()]);
}

$("blockInspector").addEventListener("click", async (event) => {
  if (event.target.closest("[data-save-block]")) { blockDirty = false; deadlineDirty = false; return saveActiveBlock(); }
  if (event.target.closest("[data-delete-block]")) return deleteActiveBlock();
  if (event.target.closest("[data-scratch-preview]")) {
    // 管理员预览：只读打开 Studio 预览模式，不写任何学生项目
    const block = activeBlock();
    if (!block?.scratch?.challenge_id) { toast("请先绑定挑战。", "error"); return; }
    const extra = scratchMockEnabled() ? { scratch_mock: "1" } : {};
    window.open(studioPreviewUrl(block.scratch.challenge_id, { studioBase: studioPreviewBase(), extra }), "_blank", "noopener");
    return;
  }
  if (event.target.closest("[data-search-papers]")) return loadPaperOptions();
  if (event.target.closest("[data-extend-deadline]")) return extendActiveDeadline();
  // ---- 选题面板交互（practice 单题块）：题型过滤 / 搜索 / 翻页 / 选中 ----
  const tabBtn = event.target.closest(".problem-picker-tabs [data-problem-type]");
  if (tabBtn) {
    if (problemPicker.type !== tabBtn.dataset.problemType) {
      clearTimeout(problemSearchTimer);
      readInspector(activeBlock());
      problemPicker.type = tabBtn.dataset.problemType;
      problemPicker.page = 1;
      loadProblems().then(() => renderBlockInspector());
    }
    return;
  }
  if (event.target.closest("[data-search-problems]")) {
    clearTimeout(problemSearchTimer);
    readInspector(activeBlock());
    problemPicker.keyword = $("blockProblemKeyword")?.value.trim() || "";
    problemPicker.page = 1;
    loadProblems().then(() => renderBlockInspector());
    return;
  }
  if (event.target.closest("[data-problem-page-prev]")) {
    if (problemPicker.page > 1) {
      clearTimeout(problemSearchTimer);
      readInspector(activeBlock());
      problemPicker.page -= 1;
      loadProblems().then(() => renderBlockInspector());
    }
    return;
  }
  if (event.target.closest("[data-problem-page-next]")) {
    const maxPage = Math.max(1, Math.ceil(problemPicker.total / problemPicker.size));
    if (problemPicker.page < maxPage) {
      clearTimeout(problemSearchTimer);
      readInspector(activeBlock());
      problemPicker.page += 1;
      loadProblems().then(() => renderBlockInspector());
    }
    return;
  }
  if (event.target.closest("[data-pick-problem]")) {
    const row = event.target.closest("[data-pick-problem]");
    // 先保存已输入的投放规则（题号/分值/尝试次数等），再重渲染，否则会被清空
    readInspector(activeBlock());
    const block = activeBlock();
    if (!block.problem) block.problem = {};
    block.problem.problem_id_no = row.dataset.problemNo;
    block.problem.problem_type = row.dataset.itemType;
    block.problem.title = row.dataset.problemTitle; // 仅管理端展示用，不随保存载荷提交
    blockDirty = true;
    renderBlockInspector();
    return;
  }
  const remove = event.target.closest("[data-unbind-material]");
  if (remove) {
    const block = activeBlock();
    try { await adminRequest(`/lesson-blocks/${block.id}/materials/${remove.dataset.unbindMaterial}`, { method: "DELETE" }); toast("资料已解绑"); blockDirty = false; await loadLessonBlocks(); } catch (error) { toast(error.message, "error"); }
    return;
  }
  if (event.target.closest("[data-pick-material]")) {
    if (draftBlock) {
      await saveActiveBlock();   // 内部 POST 并置 selectedBlockId = 新 id；失败已 toast
      if (draftBlock) return;    // 保存失败（draftBlock 仍在）则不再继续
    }
    return openMaterialPicker(activeBlock());
  }
});
$("blockInspector").addEventListener("change", (event) => {
  if (event.target.id === "blockDueAt") { deadlineDirty = true; return; }
  blockDirty = true;
  if (event.target.id === "blockVideoSource") { readInspector(activeBlock()); renderBlockInspector(); }
});
$("blockInspector").addEventListener("input", (event) => {
  if (event.target.id === "blockDueAt") { deadlineDirty = true; return; }
  blockDirty = true;
  if (event.target.id === "blockMarkdown") renderBlockMarkdownPreview();
  // 选题面板关键词：300ms 防抖自动搜索（搜索按钮仍保留兜底）
  if (event.target.id === "blockProblemKeyword") {
    clearTimeout(problemSearchTimer);
    problemSearchTimer = setTimeout(() => {
      readInspector(activeBlock());
      problemPicker.keyword = $("blockProblemKeyword")?.value.trim() || "";
      problemPicker.page = 1;
      loadProblems().then(() => renderBlockInspector());
    }, 300);
  }
});

// ---- 保存 / 删除 ----

$("lessonSave").addEventListener("click", async () => {
  const payload = collect();
  const err = document.querySelector('#lessonForm .field-error[data-err="title"]');
  if (!payload.title) {
    err.textContent = "请填写课时标题。";
    err.hidden = false;
    $("lTitle").focus();
    return;
  }
  err.hidden = true;

  // PUT /lessons/{id} 是全量覆盖（逐字段赋值，不是 PATCH），必须整份提交。
  $("lessonSave").disabled = true;
  try {
    await adminRequest(`/lessons/${selectedLessonId}`, { method: "PUT", body: JSON.stringify(payload) });
    selectedLessonRecord = { ...selectedLessonRecord, ...payload };
    original = JSON.stringify(payload);
    $("lessonSaveHint").textContent = "已保存";
    toast("课时已保存");
    await reloadTree();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    $("lessonSave").disabled = readOnly || lockedByStatus;
  }
});

$("lessonDelete").addEventListener("click", async () => {
  const lesson = findLesson(selectedLessonId);
  if (!lesson) return;
  const ok = await confirmDialog({
    title: "删除课时",
    message: `确定删除《${lesson.title}》吗？`,
    confirmText: "删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await adminRequest(`/lessons/${selectedLessonId}`, { method: "DELETE" });
    clearLessonForm();
    toast("已删除");
    await reloadTree();
  } catch (error) {
    toast(error.message, "error");
  }
});

// 离开页面前的兜底：拖拽是即时保存的，只有课时表单与内容块弹窗会丢
window.addEventListener("beforeunload", (event) => {
  if (!isDirty() && !blockDirty && !deadlineDirty) return;
  event.preventDefault();
  event.returnValue = "";
});

// 学习开放策略切换：first_n 才显示「试看块数 N」输入
$("lOpenPolicy").addEventListener("change", () => {
  $("lTrialBlocksField").hidden = $("lOpenPolicy").value !== "first_n";
});
