<script setup>
// PDF.js 自托管预览（交接文档 17 §5 批次3 S3-2）。
//
// 多页连续滚动模式（2026-08-11 按老板诉求定稿）：
//   ① 所有页纵向堆叠在一个滚动容器里，滑动查看（不是单页翻页）；
//   ② 默认显示 = 适应宽度再缩 6 档（fit − 1.2），整页可见无需手动缩放；
//   ③ 预览区可视高度刚好一页——看到一页，滚动看下一页（单页连续视图）；
//   ④ 每页 canvas 居中。
//
// 缓存策略：PDF document 对象缓存到模块级 pdf-cache.js（key = materialId 稳定标识），
// 组件销毁不销毁 document，切回时复用——配合 LessonPlayer 的 keep-alive，切走资料块
// 再切回来不会重新加载 PDF。
//
// worker 用 `new URL(..., import.meta.url)` 让 Vite 打进产物，不引 CDN。
// 样式全部用 lesson.css 已有令牌，一个新颜色都不加（文档 §7 划界）。
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import * as pdfjsLib from "pdfjs-dist";
import { takePdfDocument, releasePdfDocument } from "../../../services/pdf-cache";

pdfjsLib.GlobalWorkerOptions.workerPort = new Worker(
  new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url),
  { type: "module" },
);

const props = defineProps({
  url: { type: String, required: true }, // inline?proxy=1 同源流（fetch 不能跟 302 跨源到 MinIO，CORS 必拦）
  materialId: { type: [Number, String], required: true }, // 稳定标识，用于 document 缓存
  title: { type: String, default: "" },
});

// 老板 2026-08-12 实测定稿：默认 = 适应宽度再缩 6 档（fit − 6 × 0.2 = fit − 1.2）。
// 即「当前默认下还要点 7 下缩小」的宽度——整页可见、无需每次手动缩放。
// 初始 scale 有 0.3 下限保护，与 zoomOut 一致，窄窗口也不会缩到看不见。
const INITIAL_ZOOM_STEPS = -6;
const ZOOM_STEP = 0.2;

const scrollEl = ref(null); // 滚动容器（视窗，一页高）
const stackEl = ref(null); // 页面堆叠层（所有页占位）
const loading = ref(true);
const error = ref("");
const pageNum = ref(1);
const numPages = ref(0);
const scale = ref(1.0);

let pdfDoc = null;
let renderTasks = new Map(); // pageNumber → renderTask（取消用）
let observer = null;
let renderedPages = new Set();
let baseFitScale = 1.0; // 适应宽度的基准 scale，放大/缩小围绕它加减

// 适应宽度：按视窗宽 + 页面原始宽算 scale，让 PDF 占满预览区宽度。
function computeFitScale(page) {
  const viewport = page.getViewport({ scale: 1 });
  const containerWidth = scrollEl.value?.clientWidth || 800;
  return Math.max(0.3, (containerWidth - 4) / viewport.width);
}

// 渲染单页到对应的占位容器
async function renderPage(n) {
  if (!pdfDoc || renderedPages.has(n)) return;
  try {
    const page = await pdfDoc.getPage(n);
    const viewport = page.getViewport({ scale: scale.value });
    const wrap = stackEl.value?.querySelector(`[data-page="${n}"]`);
    if (!wrap) return;
    let canvas = wrap.querySelector("canvas");
    if (!canvas) {
      canvas = document.createElement("canvas");
      wrap.appendChild(canvas);
    }
    const ctx = canvas.getContext("2d");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;

    const old = renderTasks.get(n);
    if (old) old.cancel();
    const task = page.render({ canvasContext: ctx, viewport });
    renderTasks.set(n, task);
    await task.promise;
    renderedPages.add(n);
  } catch (e) {
    if (e?.name !== "RenderingCancelledException") {
      console.warn("[PdfReader] renderPage", n, e);
    }
  }
}

// 建所有页占位（只设高度，canvas 等滚到再渲染）+ 设视窗高度=一页高
async function buildPages() {
  if (!pdfDoc || !stackEl.value) return;
  // 取消所有进行中的渲染，清掉旧 canvas
  renderTasks.forEach((t) => t.cancel());
  renderTasks.clear();
  renderedPages.clear();
  stackEl.value.querySelectorAll(".pdf-page").forEach((el) => el.remove());

  const firstPage = await pdfDoc.getPage(1);
  const viewport = firstPage.getViewport({ scale: scale.value });
  // 视窗高度 = 一页高度 + 间距，刚好看到一页（滚动看下一页）
  if (scrollEl.value) {
    scrollEl.value.style.height = `${viewport.height + 16}px`;
  }

  for (let i = 1; i <= pdfDoc.numPages; i++) {
    const page = await pdfDoc.getPage(i);
    const vp = page.getViewport({ scale: scale.value });
    const wrap = document.createElement("div");
    wrap.className = "pdf-page";
    wrap.dataset.page = i;
    wrap.style.height = `${vp.height}px`;
    stackEl.value.appendChild(wrap);
  }
  await nextTick();
  setupObserver();
  renderPage(1); // 首页立刻渲染
}

function setupObserver() {
  if (observer) observer.disconnect();
  if (!scrollEl.value || !stackEl.value) return;
  observer = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          const n = Number(e.target.dataset.page);
          if (n && !renderedPages.has(n)) renderPage(n);
        }
      }
    },
    { root: scrollEl.value, rootMargin: "200px 0px" },
  );
  stackEl.value.querySelectorAll("[data-page]").forEach((el) => observer.observe(el));
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    pdfDoc = await takePdfDocument(props.materialId, props.url);
    numPages.value = pdfDoc.numPages;
    pageNum.value = 1;
    const page = await pdfDoc.getPage(1);
    baseFitScale = computeFitScale(page);
    scale.value = Math.max(0.3, baseFitScale + INITIAL_ZOOM_STEPS * ZOOM_STEP);
    await nextTick();
    await buildPages();
  } catch (e) {
    console.error("[PdfReader] load failed", e);
    error.value = "PDF 加载失败，尝试用浏览器内置阅读器打开。";
  } finally {
    loading.value = false;
  }
}

// ---- 工具栏 ----
async function goToPage(n) {
  const target = Math.max(1, Math.min(n, numPages.value));
  pageNum.value = target;
  const el = stackEl.value?.querySelector(`[data-page="${target}"]`);
  el?.scrollIntoView({ behavior: "smooth", block: "start" });
  renderPage(target);
}
function prevPage() {
  goToPage(pageNum.value - 1);
}
function nextPage() {
  goToPage(pageNum.value + 1);
}
async function rerender() {
  renderedPages.clear();
  await buildPages();
}
function zoomOut() {
  scale.value = Math.max(0.3, scale.value - ZOOM_STEP);
  rerender();
}
function zoomIn() {
  scale.value = Math.min(5.0, scale.value + ZOOM_STEP);
  rerender();
}
function fitToWidth() {
  scale.value = baseFitScale;
  rerender();
}

// 跟踪当前页码（滚动到哪页高亮哪页）
function onScroll() {
  if (!stackEl.value || !scrollEl.value) return;
  const wraps = stackEl.value.querySelectorAll("[data-page]");
  const containerTop = scrollEl.value.getBoundingClientRect().top;
  for (const w of wraps) {
    const rect = w.getBoundingClientRect();
    if (rect.top - containerTop >= -2 && rect.top - containerTop < 80) {
      pageNum.value = Number(w.dataset.page);
      break;
    }
  }
}

watch(
  () => [props.materialId, props.url],
  () => load(),
  { immediate: true },
);

let resizeTimer = null;
function onResize() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(async () => {
    if (!pdfDoc) return;
    const page = await pdfDoc.getPage(1);
    const newBase = computeFitScale(page);
    const delta = scale.value - baseFitScale; // 保留用户加的档位
    baseFitScale = newBase;
    scale.value = newBase + delta;
    rerender();
  }, 200);
}
window.addEventListener("resize", onResize);
if (typeof document !== "undefined") {
  document.addEventListener("fullscreenchange", onResize);
}

onBeforeUnmount(() => {
  renderTasks.forEach((t) => t.cancel());
  observer?.disconnect();
  window.removeEventListener("resize", onResize);
  releasePdfDocument(props.materialId);
});

// 把响应式状态与翻页/缩放方法暴露给父组件（BlockMaterials → mat-preview-bar
// 在统一顶栏渲染这些按钮，原 .pdf-toolbar 已合并进文件名列，腾一行高度给阅读区）。
// defineAsyncComponent 是异步加载的，被引用方需要先挂载完成才能拿到 ref.value，
// 上层用 v-if 守卫即可，无值期间按钮自然不渲染。
defineExpose({
  pageNum,
  numPages,
  scale,
  prevPage,
  nextPage,
  zoomOut,
  zoomIn,
  fitToWidth,
  goToPage,
});
</script>

<template>
  <div class="pdf-reader">
    <!-- 工具栏已合并到 BlockMaterials.mat-preview-bar（文件名同行右侧）。
         这里只保留阅读区本身，状态与方法通过 defineExpose 暴露给上层。 -->
    <div ref="scrollEl" class="pdf-scroll" @scroll.passive="onScroll">
      <div ref="stackEl" class="pdf-stack">
        <p v-if="loading" class="pdf-hint">正在加载 PDF…</p>
        <p v-else-if="error" class="pdf-hint pdf-error">{{ error }}</p>
        <!-- .pdf-page 占位由 buildPages 动态创建 -->
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-reader {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--surface);
}

/* 工具栏相关样式（.pdf-toolbar/.pdf-btn/.pdf-page-info 等）已随工具栏整体迁移
   到 BlockMaterials.mat-preview-bar 内的 .mat-pdf-tools —— 在统一顶栏渲染。
   PdfReader 只保留阅读区（视窗+堆叠层+提示）。 */

/* 视窗：高度由 buildPages 动态设为一页高，内部滚动。
   横向也允许滚动（放大后 PDF 宽度溢出）。 */
.pdf-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px;
}
/* 页面堆叠：纵向排列，每页宽度撑满让内部 canvas 居中 */
.pdf-stack {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
/* 页面居中用 margin:auto 而不是 flex 居中：放大后 canvas 比视窗宽时，
   flex 居中会让左侧溢出部分永远滚不到（scrollLeft 不能为负）；margin:auto
   在溢出时自动退化为 0、只向右溢出可滚，不溢出时正好水平居中（相对整屏）。 */
.pdf-stack :deep(.pdf-page) {
  width: 100%;
}
.pdf-stack :deep(.pdf-page canvas) {
  display: block;
  margin: 0 auto;
  box-shadow: 0 2px 12px rgba(34, 43, 40, 0.14);
  background: #fff;
  border-radius: 2px;
  flex: none;
}

.pdf-hint {
  margin: 40px auto;
  color: var(--muted);
  font-size: 12.5px;
  text-align: center;
}
.pdf-error {
  color: var(--danger);
}
</style>
