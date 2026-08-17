<script setup>
// 阅读资料块：清单 + 内嵌预览（交接文档 15 §7.2、17 §5 批次3 S3-1）。
//
// 清单来自块内容 DTO 的 materials 数组（含 material_id/display_name/asset_type/
// mime_type/size_bytes，服务端已按 status=ready 过滤并按 sort_order 排序）；
// 下载/内嵌走学生端两个接口，路径带 lesson_id + block_id（§7.3 安全红线）。
//
// 布局（17 批次3）：
// - 资料 ≤ 4 份 → 清单收成顶部一排 chips，把 260px 左栏还给预览区；
// - 资料 > 4 份 → 保留左栏，可折叠（记 localStorage），折叠后等同 chips 模式；
// - 预览区 flex:1 撑满，不再写死 min(60vh,560px)；
// - 右上角工具栏：全屏阅读 + 下载当前选中。
//
// 完成口径按 §5.1：学生点底部「完成，继续」（块壳统一上报，本组件不调接口）。
import { computed, onBeforeUnmount, ref, watch } from "vue";
import MaterialViewer from "./MaterialViewer.vue";
import LessonIcon from "../LessonIcon.vue";

// keep-alive include 需要组件 name：资料块切走不销毁，切回复用 PdfReader 实例
// 和已渲染页面（交接文档 17 §5）。编程题/视频/练习不缓存——状态复杂，缓存反而生 bug。
defineOptions({ name: "BlockMaterials" });

const props = defineProps({
  block: { type: Object, required: true },
  lessonId: { type: Number, required: true },
});

const materials = computed(() => props.block.materials || []);
const apiBase = import.meta.env.VITE_API_BASE_URL || "";

/** 可内嵌判定与 MaterialViewer 里同一份口径（§7.1 的 mime 分派表）。 */
function canEmbed(material) {
  const mime = (material.mime_type || "").toLowerCase();
  return (
    /^image\//.test(mime) ||
    /^text\/(markdown|plain|x-markdown)/.test(mime) ||
    mime === "application/pdf" ||
    /^video\//.test(mime) ||
    /^audio\//.test(mime)
  );
}

const firstEmbeddable = computed(() => materials.value.find(canEmbed) || null);
const hasEmbeddable = computed(() => firstEmbeddable.value != null);

const selectedId = ref(null);
const selected = computed(
  () => materials.value.find((m) => m.material_id === selectedId.value) || null,
);
// 当前选中是否为 PDF：mat-preview-bar 据此决定是否在文件名旁渲染翻页/缩放按钮。
// 这里的 mime 口径与 MaterialViewer 内 mime 分派一致（§7.1）。
const isPdfSelected = computed(() => {
  const mime = (selected.value?.mime_type || "").toLowerCase();
  return mime === "application/pdf";
});
// 拿到内部 MaterialViewer，进而访问它暴露的 PdfReader ref —— 在 mat-preview-bar
// 里直接复用 PdfReader 的翻页/缩放状态，把工具栏合并进文件名列，腾一行高度。
// 异步组件加载完成前为 null，工具栏自然不渲染（v-if 守卫）。
const viewerRef = ref(null);
const pdf = computed(() => viewerRef.value?.pdfRef ?? null);

// 默认选中第一份可内嵌；列表变化（换块/重载）且当前选中项已失效时重置。
watch(
  materials,
  (list) => {
    if (!list.some((m) => m.material_id === selectedId.value)) {
      selectedId.value = firstEmbeddable.value?.material_id ?? null;
    }
  },
  { immediate: true },
);

function formatBytes(size) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
}

function downloadUrl(material) {
  return `${apiBase}/api/lessons/${props.lessonId}/blocks/${props.block.id}/materials/${material.material_id}/download`;
}

const isEmpty = computed(() => materials.value.length === 0);

// 顶栏 PDF 工具按钮的事件代理：跳转指定页。
function onPdfPageInput(e) {
  pdf.value?.goToPage(Number(e.target.value));
}

// 资料清单：不再常驻占行（chips/左栏），收成顶栏「资料」按钮，点按弹出下拉抽屉。
// 切换选中后自动收起；遮罩点击也可关闭。资料只有一份时不需要抽屉按钮。
const listOpen = ref(false);
function toggleList() {
  listOpen.value = !listOpen.value;
}
function selectMaterial(material) {
  selectedId.value = material.material_id;
  listOpen.value = false;
}

// 全屏阅读：纯 CSS 浮层（position:fixed; inset:0）。不走浏览器原生 Fullscreen API，
// 否则浏览器会在底部强制弹出「按 Esc 退出全屏 - http://host:port」提示条，
// 既丑又会在生产页暴露 dev server 地址。
// 顺带自己监听 Esc 关闭，补回原生 Fullscreen 的快捷键习惯。
const isFullscreen = ref(false);
function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value;
}
function onFsKeydown(e) {
  if (e.key === "Escape" && isFullscreen.value) {
    isFullscreen.value = false;
    e.preventDefault();
  }
}
if (typeof window !== "undefined") {
  window.addEventListener("keydown", onFsKeydown);
}
onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("keydown", onFsKeydown);
  }
});
</script>

<template>
  <div class="block-materials">
    <div v-if="!isEmpty" class="lcard mat-layout">
      <!-- 预览区：撑满全部区域（无块标题行，全部高度给阅读区），
           顶栏「资料」按钮弹抽屉切换清单 -->
      <div class="mat-preview" :class="{ 'is-fullscreen': isFullscreen }">
        <div v-if="selected" class="mat-preview-bar">
          <!-- 资料清单按钮：当前文件名 + 份数 badge + 下拉箭头，点击弹出抽屉。
               badge 让学生一眼看到「不止这一份」；单份时退化为纯标题展示（disable）。 -->
          <button
            type="button"
            class="mat-list-toggle"
            :class="{ 'is-open': listOpen }"
            :disabled="materials.length <= 1"
            :aria-haspopup="materials.length > 1 ? 'listbox' : undefined"
            :aria-expanded="listOpen"
            :title="
              materials.length > 1
                ? `共 ${materials.length} 份资料，点击切换`
                : selected.display_name
            "
            @click="toggleList"
          >
            <LessonIcon name="materials" :size="14" class="mat-ico" />
            <span class="mat-item-name" :title="selected.display_name">
              {{ selected.display_name }}
            </span>
            <span class="ltag mat-count">{{ materials.length }}份</span>
            <span v-if="materials.length > 1" class="mat-caret">{{ listOpen ? "▴" : "▾" }}</span>
          </button>

          <!-- 合并自 PdfReader 工具栏：翻页 + 缩放。状态/方法来自 pdf.value
               （viewerRef.pdfRef，defineExpose 透传）。异步组件加载完成前不渲染。 -->
          <span v-if="isPdfSelected && pdf" class="mat-pdf-tools">
            <button
              type="button"
              class="pdf-btn"
              :disabled="!pdf.pageNum || pdf.pageNum <= 1"
              title="上一页"
              @click="pdf.prevPage"
            >
              ‹
            </button>
            <span class="pdf-page-info">
              <input
                type="number"
                class="pdf-page-input"
                :value="pdf.pageNum ?? 1"
                :min="1"
                :max="pdf.numPages || 1"
                @change="onPdfPageInput"
              />
              <span class="pdf-page-sep">/</span>
              <span class="pdf-page-total">{{ pdf.numPages || "—" }}</span>
            </span>
            <button
              type="button"
              class="pdf-btn"
              :disabled="!pdf.numPages || pdf.pageNum >= pdf.numPages"
              title="下一页"
              @click="pdf.nextPage"
            >
              ›
            </button>
            <span class="pdf-sep"></span>
            <button type="button" class="pdf-btn" title="缩小" @click="pdf.zoomOut">−</button>
            <button type="button" class="pdf-btn" title="适应宽度" @click="pdf.fitToWidth">
              ⤢
            </button>
            <button type="button" class="pdf-btn" title="放大" @click="pdf.zoomIn">+</button>
          </span>

          <span class="mat-preview-actions">
            <a
              class="mat-bar-btn"
              :href="downloadUrl(selected)"
              :download="selected.display_name"
              :aria-label="`下载 ${selected.display_name}`"
              title="下载"
            >
              <LessonIcon name="materials" :size="15" />
            </a>
            <button
              type="button"
              class="mat-bar-btn"
              :title="isFullscreen ? '退出全屏' : '全屏阅读'"
              :aria-label="isFullscreen ? '退出全屏' : '全屏阅读'"
              @click="toggleFullscreen"
            >
              {{ isFullscreen ? "✕" : "⛶" }}
            </button>
          </span>

          <!-- 资料清单下拉抽屉：挂在工具栏（bar，position:relative）内部，top:100%
               正好落在工具栏正下方。之前挂在预览卡片上导致 top:100% 定位到卡片底部
               （视口外）被 overflow:hidden 裁掉，抽屉完全不可见 —— 已修复。 -->
          <div
            v-if="listOpen"
            class="mat-drawer"
            role="listbox"
            :aria-label="`资料清单（${materials.length} 份）`"
          >
            <div
              v-for="m in materials"
              :key="m.material_id"
              class="mat-drawer-row"
              :class="{ 'is-selected': m.material_id === selectedId }"
              role="option"
              :aria-selected="m.material_id === selectedId"
            >
              <button
                type="button"
                class="mat-drawer-item"
                :disabled="m.material_id === selectedId"
                :title="m.material_id === selectedId ? '当前正在显示' : m.display_name"
                @click="selectMaterial(m)"
              >
                <LessonIcon name="materials" :size="14" class="mat-ico" />
                <span class="mat-item-name" :title="m.display_name">{{ m.display_name }}</span>
                <span v-if="m.material_id === selectedId" class="mat-current-tag">当前</span>
                <span class="mat-item-meta">
                  <span class="ltag">{{ m.asset_type }}</span>
                  <span class="mat-size">{{ formatBytes(m.size_bytes) }}</span>
                </span>
              </button>
              <!-- 下载是兄弟节点不是子节点：<a> 嵌 <button> 是非法 HTML -->
              <a
                class="mat-dl"
                :href="downloadUrl(m)"
                :download="m.display_name"
                :title="`下载 ${m.display_name}`"
                :aria-label="`下载 ${m.display_name}`"
              >
                ↓
              </a>
            </div>
          </div>
        </div>

        <!-- 遮罩：盖住阅读区（不含工具栏），点击关闭。挂在预览卡片上，
             z-index 低于工具栏（工具栏整体 z-27，其内抽屉随之高于遮罩）。 -->
        <div v-if="listOpen" class="mat-drawer-scrim" @click="listOpen = false"></div>

        <div class="mat-preview-body">
          <MaterialViewer
            v-if="selected"
            ref="viewerRef"
            :key="selected.material_id"
            :material="selected"
            :lesson-id="lessonId"
            :block-id="block.id"
          />
          <div v-else class="mat-empty">
            <LessonIcon name="materials" :size="22" />
            <p>
              {{
                hasEmbeddable ? "点击上方「资料」按钮查看预览" : "这些资料需下载后用本地软件打开。"
              }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="block-placeholder">
      <LessonIcon name="materials" :size="20" /><span>本块还没有绑定资料。</span>
    </div>
  </div>
</template>

<style scoped>
/* 布局：清单不再常驻（chips 行 / 260px 左栏都删了），预览区独占整块。
   is-reader 模式下外层 .block-wrap.is-reader 已让 .block-materials flex:1，
   这里 .mat-layout 吃满它。省下来的每一行高度都归 PDF 阅读区。 */
.mat-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
}

/* ---- 顶栏：资料按钮 | PDF 工具 | 下载/全屏 ---- */
.mat-preview {
  position: relative; /* 抽屉 absolute 的定位参照 */
  min-width: 0;
  min-height: 520px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--surface);
}
.mat-preview-bar {
  flex: none;
  position: relative; /* 高于抽屉遮罩：抽屉开着时顶栏按钮仍可点击（再点一次=关闭） */
  z-index: 27;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--line);
  background: var(--paper);
  font-size: 12px;
}
/* 资料清单按钮：原 chips/左栏行合并进这 28px 按钮，点击弹抽屉切换。
   显示当前文件名 + 份数 badge（让学生知道不止这一份）。 */
.mat-list-toggle {
  flex: none;
  max-width: 52%;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
}
.mat-list-toggle:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.mat-list-toggle.is-open {
  border-color: var(--accent);
  color: var(--accent);
}
.mat-list-toggle:disabled {
  cursor: default;
}
.mat-list-toggle .mat-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mat-list-toggle .mat-count {
  flex: none;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--mint);
  color: var(--muted);
}
.mat-caret {
  flex: none;
  color: var(--muted);
  font-size: 10px;
}
.mat-list-toggle .mat-ico {
  color: var(--muted);
}

/* ---- 资料下拉抽屉 ---- */
/* 遮罩：盖住阅读区（不含工具栏），点击关闭。工具栏 z-27 整体在其上，
   所以工具栏按钮与抽屉（bar 子元素）都不受影响，仍可点击。 */
.mat-drawer-scrim {
  position: absolute;
  inset: 0;
  z-index: 25;
  background: transparent;
}
.mat-drawer {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 26;
  width: min(340px, 92%);
  max-height: min(50vh, 420px);
  overflow-y: auto;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-top: 0;
  border-radius: 0 0 var(--card-radius, 8px) var(--card-radius, 8px);
  box-shadow: var(--shadow, 0 6px 24px rgba(34, 43, 40, 0.16));
}
.mat-drawer-row {
  display: flex;
  align-items: stretch;
  border-radius: 6px;
  transition: background 0.12s;
}
.mat-drawer-row:hover {
  background: var(--mint);
}
.mat-drawer-row.is-selected {
  background: var(--mint);
  box-shadow: inset 2px 0 0 var(--accent);
}
.mat-drawer-item {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 0;
  background: transparent;
  color: var(--ink);
  text-align: left;
}
/* 当前正在显示的项：不可再选（禁用），保留高亮 + 「当前」标签 */
.mat-drawer-item:disabled {
  cursor: default;
  opacity: 0.75;
}
.mat-drawer-item:disabled .mat-current-tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  line-height: 1.4;
}
.mat-drawer-item:focus-visible,
.mat-dl:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.mat-drawer-item .mat-item-name {
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mat-drawer-item .mat-ico {
  flex: none;
  color: var(--muted);
}
.mat-drawer-row.is-selected .mat-ico {
  color: var(--accent);
}
.mat-item-meta {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.mat-size {
  font-size: 10px;
  color: var(--muted);
  font-family: var(--font-mono);
}
.mat-dl {
  flex: none;
  display: grid;
  place-items: center;
  padding: 0 10px;
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
  line-height: 1;
}
.mat-dl:hover {
  text-decoration: underline;
}

/* ---- 预览区 ---- */
/* 合并自 PdfReader 工具栏（翻页 + 缩放）。PdfReader 自身 defineExpose 状态，
   这里直接复用——按钮状态与阅读区严格同步，没有跨组件滞后。 */
.mat-pdf-tools {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
}
.mat-pdf-tools .pdf-btn {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: var(--card-radius, 8px);
  background: var(--surface);
  color: var(--ink);
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  padding: 0;
}
.mat-pdf-tools .pdf-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.mat-pdf-tools .pdf-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
.mat-pdf-tools .pdf-page-info {
  display: flex;
  align-items: center;
  gap: 2px;
  color: var(--muted);
}
.mat-pdf-tools .pdf-page-input {
  width: 38px;
  height: 24px;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--surface);
  color: var(--ink);
  font-size: 12px;
  font-family: var(--font-mono);
  -moz-appearance: textfield;
}
.mat-pdf-tools .pdf-page-input::-webkit-outer-spin-button,
.mat-pdf-tools .pdf-page-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.mat-pdf-tools .pdf-page-sep {
  color: var(--muted);
}
.mat-pdf-tools .pdf-sep {
  width: 1px;
  height: 18px;
  background: var(--line);
  margin: 0 4px;
}

.mat-preview-actions {
  flex: none;
  display: flex;
  gap: 4px;
}
.mat-bar-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--line);
  border-radius: var(--card-radius, 8px);
  background: var(--surface);
  color: var(--ink);
  text-decoration: none;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}
.mat-bar-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.mat-preview-body {
  flex: 1;
  min-height: 0;
  padding: 12px 16px;
  display: flex;
}

/* 全屏浮层：纯 CSS 方案（不调浏览器原生 Fullscreen API，
   否则浏览器底部会弹出「按 Esc 退出全屏 - http://host:port」提示条）。
   走 fixed 撑满视口，PDF.js / iframe 自然跟着容器重新自适应。 */
.mat-preview.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  border-radius: 0;
}
.mat-preview.is-fullscreen .mat-preview-body {
  padding: 16px;
}

.mat-empty {
  margin: auto;
  text-align: center;
  color: var(--muted);
  display: grid;
  gap: 10px;
  justify-items: center;
  font-size: 12.5px;
}
.mat-empty p {
  margin: 0;
}

@media (max-width: 720px) {
  .mat-list-toggle {
    max-width: 60%;
  }
  .mat-preview {
    min-height: 360px;
  }
}
</style>
