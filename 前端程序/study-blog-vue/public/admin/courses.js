// 课包管理页：列表（三分区 + 检索 + 分页）+ 课包编辑 Modal + 分类维护 Modal。
//
// 边界：本页只管课包这个对象本身（基本信息 + 发布生命周期）。章节/课时的编排在
// nodes.html——同 papers.html / exam-links.html 的两页拆分，一页管对象、一页管内容。
//
// ⚠️ 发布能不能点，由后端说了算。_publish_checks（admin_courses.py）是完整性校验的
// 唯一实现，前端**不复刻**规则、也不预先灰掉按钮：点下去拿 422，把后端返回的中文清单
// 原样展示。前端复刻一份，规则一改两边就不一致，而且不一致时用户看到的是错的那份。

import { initLayout } from "./admin-layout.js";
import { adminRequest, adminMe, adminUpload } from "./admin-api.js";
import { createPagedList } from "./admin-list.js";
import { closeMask, confirmDialog, escapeHtml, fmtTime, openMask, toast } from "./admin-ui.js";
import { sanitizeRenderedHtml } from "./admin-markdown.js";

initLayout();

const $ = (id) => document.getElementById(id);

const DIFFICULTY = [
  ["beginner", "入门"],
  ["intermediate", "进阶"],
  ["advanced", "高阶"],
];
const DIFFICULTY_LABEL = Object.fromEntries(DIFFICULTY);
const STATUS_LABEL = {
  draft: ["草稿", "warn"],
  published: ["已发布", ""],
  off_shelf: ["已下架", "gray"],
};

// 默认落在「已发布」分区：运营打开后台第一眼看到的是对外可见的课包，草稿是少数。
let zone = "published";
let readOnly = false; // reviewer：只读
let categories = [];
let areas = [];
let courseTypes = [];
let courseTags = [];
let editingId = null;
let releaseCourse = null;
let releaseCategory = null;
// 封面：上传后存相对 URL（/course-covers/…），提交时写进 cover_url。
let coverUrl = "";
// 课包简介：Vditor 实例跟随编辑 Modal 的生命周期（打开挂载、关闭销毁）。
let descriptionEditor = null;

// ==================== 角色 ====================
// 先拿角色再首次渲染（见页尾的启动段）：readOnly 决定行里画按钮还是画「只读」。
// 并行拿会先画出一排能点的按钮，reviewer 点了才被后端 403——不该让人点了再说。

async function loadRole() {
  try {
    const me = await adminMe();
    readOnly = me?.role === "reviewer";
  } catch {
    /* 未登录时 admin-api 已经跳登录页，这里不必再处理 */
  }
  if (readOnly) {
    for (const id of ["newCourseBtn", "manageCategoryBtn"]) {
      $(id).disabled = true;
      $(id).title = "只读角色";
    }
  }
}

// ==================== 分类 ====================

async function loadCategories() {
  categories = await adminRequest("/course-categories");
  const areaKey = $("sArea")?.value || "";
  const visible = areaKey ? categories.filter((c) => c.area_key === areaKey) : categories;
  const options = ['<option value="">全部</option>'].concat(
    visible.map((c) => `<option value="${c.id}">${escapeHtml(categoryLabel(c))}</option>`),
  );
  const keep = $("sCategory").value;
  $("sCategory").innerHTML = options.join("");
  $("sCategory").value = keep;
  return categories;
}

function categoryLabel(category) {
  const names = [category.name];
  let parent = categories.find((item) => item.id === category.parent_id);
  const seen = new Set([category.id]);
  while (parent && !seen.has(parent.id)) {
    seen.add(parent.id);
    names.unshift(parent.name);
    parent = categories.find((item) => item.id === parent.parent_id);
  }
  return names.join(" / ");
}

async function loadCatalogOptions(areaKey = null, selected = {}) {
  if (!areas.length) areas = await adminRequest("/learning-catalog/areas");
  const activeAreas = areas.filter((item) => item.status !== "hidden");
  $("sArea").innerHTML = '<option value="">全部</option>' + activeAreas.map((area) =>
    `<option value="${escapeHtml(area.key)}">${escapeHtml(area.name)}</option>`).join("");
  const key = areaKey || selected.area_key || activeAreas[0]?.key || "";
  $("cAreaKey").innerHTML = activeAreas.map((area) =>
    `<option value="${escapeHtml(area.key)}">${escapeHtml(area.name)}</option>`).join("");
  $("cAreaKey").value = key;
  if (!key) return;
  [courseTypes, courseTags] = await Promise.all([
    adminRequest(`/learning-catalog/types?area_key=${encodeURIComponent(key)}`),
    adminRequest(`/learning-catalog/tags?area_key=${encodeURIComponent(key)}`),
  ]);
  fillCategorySelect(selected.category_id ?? null, key);
  $("cCourseKind").innerHTML = courseTypes.filter((item) => item.is_active).map((item) =>
    `<option value="${escapeHtml(item.key)}">${escapeHtml(item.name)}</option>`).join("");
  $("cCourseKind").value = selected.course_kind || courseTypes.find((item) => item.is_active)?.key || "";
  const selectedTags = new Set(selected.tag_ids || []);
  $("cTags").innerHTML = courseTags.filter((item) => item.is_active).map((tag) =>
    `<label class="course-tag-option"><input type="checkbox" value="${tag.id}" ${selectedTags.has(tag.id) ? "checked" : ""} /><span class="dot" aria-hidden="true"></span><span class="txt">${escapeHtml(tag.name)}</span></label>`).join("") || '<span class="muted">当前专区还没有标签</span>';
}

function fillCategorySelect(value, areaKey = $("cAreaKey").value) {
  const visible = categories.filter((item) => item.area_key === areaKey && item.is_active);
  const hasCategories = visible.length > 0;
  const empty = hasCategories
    ? '<option value="">请选择分类</option>'
    : '<option value="">请先创建分类，再新建课包</option>';
  $("cCategory").innerHTML =
    empty + visible.map((c) => `<option value="${c.id}">${escapeHtml(categoryLabel(c))}</option>`).join("");
  $("cCategory").value = value == null ? "" : String(value);
  // 分类为空时禁选：引导先去「分类维护」建分类，而不是选出一个空值提交
  $("cCategory").disabled = !hasCategories;
}

// ==================== 列表 ====================

// 行操作：沿用 papers.js 的 .row-actions + .btn-text.link 范式（flex + gap 自带间隔，
// 不需要自造分隔符）。「编排目录」用 <a>：中键新开标签是这里的常见动作
// ——一边看课包列表、一边在另一个标签里排目录。
function actionButtons(course) {
  if (readOnly) return '<span class="muted">只读</span>';
  // 阶段 1 口径：已发布课包必须先下架才能编排/编辑（后端同样拦截，这里只是不让人点到 409）
  const published = course.status === "published";
  const lockedTip = "已发布课包请先下架再编辑";
  const actions = [
    published
      ? `<button class="btn-text link" type="button" disabled title="${lockedTip}">编排目录</button>`
      : `<a class="btn-text link" href="nodes.html?course=${course.id}">编排目录</a>`,
    published
      ? `<button class="btn-text link" type="button" disabled title="${lockedTip}">编辑</button>`
      : `<button class="btn-text link" type="button" data-act="edit" data-id="${course.id}">编辑</button>`,
    course.status === "published"
      ? `<button class="btn-text link" type="button" data-act="off-shelf" data-id="${course.id}">下架</button>`
      : `<button class="btn-text link" type="button" data-act="publish" data-id="${course.id}">${
          course.status === "off_shelf" ? "重新发布" : "发布"
        }</button>`,
    course.status === "published"
      ? '<button class="btn-text link danger" type="button" disabled title="已发布的课包不能删除，请先下架">删除</button>'
      : `<button class="btn-text link danger" type="button" data-act="delete" data-id="${course.id}">删除</button>`,
  ].join("");
  return `<div class="row-actions">${actions}</div>`;
}

const list = createPagedList({
  els: {
    rows: $("courseRows"),
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
  initialPageSize: 10,
  fetchPage: ({ page, size }) => {
    const params = new URLSearchParams({ status: zone, page: String(page), page_size: String(size) });
    const keyword = $("sKeyword").value.trim();
    if (keyword) params.set("keyword", keyword);
    if ($("sCategory").value) params.set("category_id", $("sCategory").value);
    if ($("sArea").value) params.set("area_key", $("sArea").value);
    return adminRequest(`/courses?${params}`);
  },
  renderRows: (items) => {
    // 难度在服务端没有筛选参数（列表接口只有 keyword/category/status），本页在前端过滤。
    // 数据量是几十条、且已分页，前端过滤够用；真到需要跨页筛难度时再让后端加参数。
    const want = $("sDifficulty").value;
    const rows = want ? items.filter((c) => c.difficulty === want) : items;
    $("courseRows").innerHTML = rows
      .map((c) => {
        const [label, cls] = STATUS_LABEL[c.status] || [c.status, ""];
        return `<tr>
          <td>${c.id}</td>
          <td>
            <div>${escapeHtml(c.title)}</div>
            ${c.subtitle ? `<div class="muted">${escapeHtml(c.subtitle)}</div>` : ""}
          </td>
          <td>${c.category_name ? escapeHtml(c.category_name) : '<span class="muted">未分类</span>'}</td>
          <td>${DIFFICULTY_LABEL[c.difficulty] || c.difficulty}</td>
          <td>${c.section_count} 章 / ${c.lesson_count} 节</td>
          <td><span class="tag ${cls}">${label}</span></td>
          <td>${fmtTime(c.updated_at)}</td>
          <td>${actionButtons(c)}</td>
        </tr>`;
      })
      .join("");
  },
  onLoaded: () => refreshCounts(),
});

// 三个分区计数：各打一次 page_size=1 只取 total。失败不打断列表，显示 —。
async function refreshCounts() {
  const targets = [
    ["draft", "draftCount"],
    ["published", "publishedCount"],
    ["off_shelf", "offShelfCount"],
  ];
  await Promise.all(
    targets.map(async ([status, elId]) => {
      try {
        const data = await adminRequest(`/courses?status=${status}&page=1&page_size=1`);
        $(elId).textContent = String(data.total ?? 0);
      } catch {
        $(elId).textContent = "—";
      }
    }),
  );
}

for (const btn of document.querySelectorAll(".zone-tabs button")) {
  btn.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".zone-tabs button")) other.classList.remove("active");
    btn.classList.add("active");
    zone = btn.dataset.zone;
    list.page = 1;
    list.reload();
  });
}

$("searchBtn").addEventListener("click", () => {
  list.page = 1;
  list.reload();
});
$("resetBtn").addEventListener("click", () => {
  $("sKeyword").value = "";
  $("sCategory").value = "";
  $("sArea").value = "";
  $("sDifficulty").value = "";
  list.page = 1;
  list.reload();
});
$("sKeyword").addEventListener("keydown", (event) => {
  if (event.key === "Enter") $("searchBtn").click();
});
$("sDifficulty").addEventListener("change", () => list.reload());
$("sArea").addEventListener("change", async () => {
  await loadCategories();
  list.page = 1;
  list.reload();
});

// ==================== 行操作 ====================

$("courseRows").addEventListener("click", async (event) => {
  const btn = event.target.closest("button[data-act]");
  if (!btn || btn.disabled) return;
  const id = Number(btn.dataset.id);
  const act = btn.dataset.act;

  if (act === "nodes") {
    location.href = `nodes.html?course=${id}`;
    return;
  }
  if (act === "edit") {
    openCourseModal(id);
    return;
  }
  if (act === "publish") {
    await publishCourse(id);
    return;
  }
  if (act === "off-shelf") {
    const ok = await confirmDialog({
      title: "下架课包",
      message: "下架后学员端立即看不到这个课包，已产生的学习记录保留。",
      confirmText: "下架",
    });
    if (!ok) return;
    try {
      await adminRequest(`/courses/${id}/off-shelf`, { method: "POST", body: "{}" });
      toast("已下架");
      list.reload();
    } catch (error) {
      toast(error.message, "error");
    }
    return;
  }
  if (act === "delete") {
    const ok = await confirmDialog({
      title: "删除课包",
      message: "将同时删除它下面的全部章节与课时，不可恢复。",
      detail: "已上传的视频记录不受影响，只是失去与课时的绑定。",
      confirmText: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await adminRequest(`/courses/${id}`, { method: "DELETE" });
      toast("已删除");
      list.retreatIfEmpty();
      list.reload();
    } catch (error) {
      toast(error.message, "error");
    }
  }
});

async function publishCourse(id) {
  try {
    await adminRequest(`/courses/${id}/publish`, {
      method: "POST",
      body: "{}",
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    toast("已发布");
    list.reload();
  } catch (error) {
    // 422 = 完整性校验没过，detail 是分号连接的中文清单。原样展示，不做二次加工。
    await confirmDialog({
      title: "还不能发布",
      message: "这个课包还差一些内容：",
      detail: error.message,
      confirmText: "去补全",
    }).then((go) => {
      if (go) location.href = `nodes.html?course=${id}`;
    });
  }
}

// ==================== 课包编辑 Modal ====================

function renderDots(container, name, options, value) {
  container.innerHTML = options
    .map(
      ([val, label]) =>
        `<label class="rdot"><input type="radio" name="${name}" value="${escapeHtml(String(val))}"${
          String(val) === String(value) ? " checked" : ""
        } /><span class="dot"></span><span class="txt">${escapeHtml(label)}</span></label>`,
    )
    .join("");
}

// ==================== 封面（应用内上传，独立存储区域） ====================

function renderCoverPreview() {
  $("cCoverPreview").hidden = !coverUrl;
  if (coverUrl) $("cCoverImg").src = coverUrl;
  else $("cCoverImg").removeAttribute("src");
}

$("cCoverPick").addEventListener("click", () => $("cCoverFile").click());

$("cCoverFile").addEventListener("change", async () => {
  const file = $("cCoverFile").files?.[0];
  $("cCoverFile").value = ""; // 同一张图再次选择也要触发 change
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  $("cCoverPick").disabled = true;
  try {
    const asset = await adminUpload("/course-covers", form);
    coverUrl = asset.url;
    renderCoverPreview();
    toast("封面上传成功，保存后生效");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    $("cCoverPick").disabled = false;
  }
});

$("cCoverRemove").addEventListener("click", () => {
  coverUrl = "";
  renderCoverPreview();
});

// ==================== 课包简介（Vditor，与题库录入同一套） ====================

// 插图按钮的图标：复用题库那朵「图片」而不是 Vditor 默认的云朵。
const DESCRIPTION_IMAGE_ICON_SVG =
  '<svg viewBox="0 0 1024 1024" width="16" height="16"><path fill="currentColor" d="M896 128H128a64 64 0 0 0-64 64v640a64 64 0 0 0 64 64h768a64 64 0 0 0 64-64V192a64 64 0 0 0-64-64zm0 704H128V192h768v640zM352 448a64 64 0 1 0 0-128 64 64 0 0 0 0 128zm448 256L608 448 448 640l-96-96-160 160h608z"/></svg>';

const DESCRIPTION_TOOLBAR = [
  "headings", "bold", "italic", "strike", "inline-code", "code", "table",
  "list", "ordered-list", "quote", "link",
  { name: "upload", tip: "插入图片", icon: DESCRIPTION_IMAGE_ICON_SVG },
  "undo", "redo", "fullscreen", "edit-mode",
];

/**
 * 简介插图：走 adminUpload()（带 CSRF 轮换与 401 自动续期），而不是 Vditor 自带的
 * upload.url（两样都没有）。与题库录题的 uploadInlineImage 同一套理由。
 * 插图落在题干配图的 /media/ 区域——cleanup_media.py 已把 Course.description 计入
 * 扫描列，简介里的图不会被当孤儿删掉。
 */
async function uploadDescriptionImage(editor, files) {
  const file = (files || [])[0];
  if (!file) return null;
  try {
    const form = new FormData();
    form.append("file", file);
    const asset = await adminUpload("/media/images", form);
    editor.insertValue(`![](${asset.url})`);
    return null;
  } catch (error) {
    const message = error?.message || "图片上传失败。";
    toast(message, "error");
    return message;
  }
}

function mountDescriptionEditor(initialMarkdown) {
  const container = $("cDescriptionEditor");
  container.innerHTML = "";
  if (!window.Vditor) {
    container.textContent = "文本编辑器未加载，请检查本地 vendor 资源。";
    return;
  }
  descriptionEditor = new window.Vditor(container, {
    value: initialMarkdown || "",
    mode: "ir",
    height: 260,
    cdn: "/admin/vendor/vditor",
    placeholder: "学员在课包详情页看到的介绍…",
    cache: { enable: false },
    toolbar: DESCRIPTION_TOOLBAR,
    // accept 只管文件选择框，真正的类型校验在服务端（只信 Pillow 解码结果）
    upload: {
      accept: "image/png,image/jpeg,image/gif,image/webp",
      multiple: false,
      handler: (files) => uploadDescriptionImage(descriptionEditor, files),
    },
    preview: { transform: sanitizeRenderedHtml },
  });
}

function destroyDescriptionEditor() {
  descriptionEditor?.destroy();
  descriptionEditor = null;
}

function clearErrors() {
  for (const el of document.querySelectorAll("#courseModal .field-error")) el.hidden = true;
}

function showError(field, message) {
  const el = document.querySelector(`#courseModal .field-error[data-err="${field}"]`);
  if (el) {
    el.textContent = message;
    el.hidden = false;
  }
}

async function openCourseModal(id) {
  if (readOnly) return;
  clearErrors();
  editingId = id ?? null;
  await loadCategories();

  let course = null;
  if (id) {
    try {
      course = await adminRequest(`/courses/${id}`);
    } catch (error) {
      toast(error.message, "error");
      list.reload();
      return;
    }
  }

  $("courseModalTitle").textContent = course ? "编辑课包" : "新建课包";
  $("courseModalHint").textContent = course
    ? `当前状态：${(STATUS_LABEL[course.status] || [course.status])[0]}（发布/下架在列表里操作）`
    : categories.length
      ? "创建后停在草稿，配完目录再发布"
      : "还没有分类——请先创建分类，再新建课包（右上角「分类维护」）。";
  $("cTitle").value = course?.title ?? "";
  $("cSubtitle").value = course?.subtitle ?? "";
  coverUrl = course?.cover_url ?? "";
  renderCoverPreview();
  await loadCatalogOptions(course?.area_key, course || {});
  renderDots($("cDifficultyGroup"), "cDifficulty", DIFFICULTY, course?.difficulty ?? "beginner");

  releaseCourse = openMask($("courseMask"), { focusSelector: "#cTitle" });
  // Vditor 必须在 Modal 可见后才能初始化（隐藏容器量不出宽度）。
  destroyDescriptionEditor();
  mountDescriptionEditor(course?.description ?? "");
}

function closeCourseModal() {
  destroyDescriptionEditor();
  closeMask($("courseMask"), releaseCourse);
  releaseCourse = null;
  editingId = null;
  coverUrl = "";
}

$("newCourseBtn").addEventListener("click", () => openCourseModal(null));
$("courseClose").addEventListener("click", closeCourseModal);
$("courseCancel").addEventListener("click", closeCourseModal);
$("cAreaKey").addEventListener("change", async () => {
  try {
    await loadCatalogOptions($("cAreaKey").value, {});
  } catch (error) {
    toast(error.message, "error");
  }
});

$("courseSave").addEventListener("click", async () => {
  clearErrors();
  const title = $("cTitle").value.trim();
  if (!title) {
    showError("title", "请填写课包名称。");
    $("cTitle").focus();
    return;
  }
  const categoryId = $("cCategory").value;
  if (!categoryId) {
    // 后端允许分类为空，但发布时会拦（_publish_checks 要求分类非空）。
    // 与其让人建完再被拒，不如在这里就要求填——这不是复刻规则，是提前满足它。
    // 分类一个都没有时，提示先建分类而不是「请选择分类」。
    showError("category_id", categories.length ? "请选择分类（发布时必填）。" : "请先创建分类，再新建课包。");
    return;
  }

  // 注意：PUT /courses/{id} 是**全量覆盖**（逐字段赋值，不是 PATCH），
  // 所有字段必须一起提交，包括这次没改的。
  const payload = {
    title,
    subtitle: $("cSubtitle").value.trim() || null,
    description: (descriptionEditor?.getValue() || "").trim() || null,
    cover_url: coverUrl || null,
    category_id: Number(categoryId),
    area_key: $("cAreaKey").value,
    course_kind: $("cCourseKind").value,
    tag_ids: [...$("cTags").querySelectorAll('input[type="checkbox"]:checked')].map((item) => Number(item.value)),
    difficulty: document.querySelector('input[name="cDifficulty"]:checked')?.value || "beginner",
    price_cents: 0, // B2B 开通制，前台不谈价；字段保留给未来
  };

  $("courseSave").disabled = true;
  try {
    if (editingId) {
      await adminRequest(`/courses/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
      toast("已保存");
    } else {
      const created = await adminRequest("/courses", { method: "POST", body: JSON.stringify(payload) });
      toast("已创建，接下来去编排目录");
      closeCourseModal();
      location.href = `nodes.html?course=${created.id}`;
      return;
    }
    closeCourseModal();
    list.reload();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    $("courseSave").disabled = false;
  }
});

// ==================== 分类维护 Modal ====================

function renderCategoryRows() {
  $("categoryEmpty").hidden = categories.length > 0;
  $("categoryRows").innerHTML = categories
    .map(
      (c) => `<tr data-id="${c.id}">
        <td><input class="cat-name" value="${escapeHtml(c.name)}" maxlength="50" /></td>
        <td><input class="cat-sort" type="number" value="${c.sort_order}" style="width: 70px" /></td>
        <td>
          <button class="btn-text link" type="button" data-cat="save">保存</button>
          <span class="sep">·</span>
          <button class="btn-text link danger" type="button" data-cat="delete">删除</button>
        </td>
      </tr>`,
    )
    .join("");
}

$("manageCategoryBtn").addEventListener("click", async () => {
  location.href = "learning-catalog.html";
});

$("categoryClose").addEventListener("click", () => {
  closeMask($("categoryMask"), releaseCategory);
  releaseCategory = null;
  list.reload(); // 分类名可能改过，列表里的分类列要跟着变
});

$("addCategoryBtn").addEventListener("click", async () => {
  const name = $("newCategoryName").value.trim();
  if (!name) {
    toast("请填写分类名称", "error");
    return;
  }
  try {
    await adminRequest("/course-categories", {
      method: "POST",
      body: JSON.stringify({ name, sort_order: Number($("newCategorySort").value) || 0 }),
    });
    $("newCategoryName").value = "";
    $("newCategorySort").value = "0";
    await loadCategories();
    renderCategoryRows();
    toast("已添加");
  } catch (error) {
    toast(error.message, "error");
  }
});

$("categoryRows").addEventListener("click", async (event) => {
  const btn = event.target.closest("button[data-cat]");
  if (!btn) return;
  const tr = btn.closest("tr");
  const id = Number(tr.dataset.id);

  if (btn.dataset.cat === "save") {
    const name = tr.querySelector(".cat-name").value.trim();
    if (!name) {
      toast("分类名称不能为空", "error");
      return;
    }
    try {
      await adminRequest(`/course-categories/${id}`, {
        method: "PUT",
        body: JSON.stringify({ name, sort_order: Number(tr.querySelector(".cat-sort").value) || 0 }),
      });
      await loadCategories();
      renderCategoryRows();
      toast("已保存");
    } catch (error) {
      toast(error.message, "error");
    }
    return;
  }

  const ok = await confirmDialog({
    title: "删除分类",
    message: "仍被课包使用的分类不能删除。",
    confirmText: "删除",
    danger: true,
  });
  if (!ok) return;
  try {
    await adminRequest(`/course-categories/${id}`, { method: "DELETE" });
    await loadCategories();
    renderCategoryRows();
    toast("已删除");
  } catch (error) {
    // 409：仍有 N 个课包在用。后端文案已经说清楚数量，原样展示。
    toast(error.message, "error");
  }
});

// ==================== 启动 ====================

(async () => {
  await loadRole();
  try {
    await loadCatalogOptions();
    await loadCategories();
  } catch {
    toast("分类加载失败，筛选栏可能不完整", "error");
  }
  list.reload();
})();
