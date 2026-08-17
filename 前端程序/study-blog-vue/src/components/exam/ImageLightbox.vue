<script setup>
// 题干配图的大图查看器：遮罩 + 滚轮缩放 + 拖动平移 + 双指捏合。
//
// 为什么不用 ExamModal：那是 reka-ui 的 Dialog，内容跟着弹窗的内边距和滚动条走，
// 而看图要的恰好相反——整屏、无内边距、内容自己接管滚轮和拖动。
// 也不用 <Teleport>：ExamView 里那条注释记着传送门锚点在阶段切换时失效导致白屏的事故，
// 这个组件本来就是 ExamView 模板里的静态节点，position:fixed 已经够了，没必要冒那个险。
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { closeLightbox, lightbox } from "../../stores/lightbox";

const MIN_SCALE = 0.2;
const MAX_SCALE = 8;

const stage = ref(null); // 遮罩里那块承载图片的区域，缩放的坐标原点取它的中心
const image = ref(null);
const scale = ref(1);
const offset = ref({ x: 0, y: 0 });
const fitScale = ref(1); // 「适应屏幕」那一档，双击在它和 2× 之间来回
const ready = ref(false); // 图片尺寸拿到之前不显示，免得先闪一下原始大小

const open = computed(() => Boolean(lightbox.src));
const percent = computed(() => Math.round((scale.value / fitScale.value) * 100));

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

/** 按容器算出「整张图刚好放得下」的倍率。小图不放大——把 200px 的示意图拉满屏只会糊。 */
function fitToStage() {
  const node = image.value;
  const box = stage.value;
  if (!node || !box || !node.naturalWidth) return;
  const rect = box.getBoundingClientRect();
  const ratio = Math.min(rect.width / node.naturalWidth, rect.height / node.naturalHeight);
  fitScale.value = Math.min(1, ratio) || 1;
  scale.value = fitScale.value;
  offset.value = { x: 0, y: 0 };
  ready.value = true;
}

/**
 * 缩放到 next，并保持 (clientX, clientY) 下面压着的那个像素不动。
 * 不做这件事的话，滚轮缩放会一路把关注的位置推出视野，看细节全靠碰运气。
 */
function zoomAt(next, clientX, clientY) {
  const box = stage.value;
  if (!box) return;
  const target = clamp(next, MIN_SCALE * fitScale.value, MAX_SCALE);
  const rect = box.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  // 光标处对应的图片坐标（以图片中心为原点、未缩放）
  const px = (clientX - cx - offset.value.x) / scale.value;
  const py = (clientY - cy - offset.value.y) / scale.value;
  offset.value = { x: clientX - cx - target * px, y: clientY - cy - target * py };
  scale.value = target;
}

function zoomBy(factor) {
  const box = stage.value;
  if (!box) return;
  const rect = box.getBoundingClientRect();
  zoomAt(scale.value * factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
}

function reset() {
  scale.value = fitScale.value;
  offset.value = { x: 0, y: 0 };
}

function onWheel(event) {
  event.preventDefault();
  // deltaY 的量纲在触控板/鼠标/不同 deltaMode 之间差一个数量级，只取方向。
  zoomAt(scale.value * (event.deltaY < 0 ? 1.15 : 1 / 1.15), event.clientX, event.clientY);
}

function onDoubleClick(event) {
  if (scale.value > fitScale.value * 1.01) reset();
  else zoomAt(fitScale.value * 2, event.clientX, event.clientY);
}

// ---------- 拖动与捏合 ----------
// 统一走 Pointer Events：鼠标拖、单指拖、双指捏合三条路径共用一份指针表，
// 分别写 mouse* 和 touch* 会在混合输入设备（带触屏的笔记本）上打架。
const pointers = new Map();
let dragged = false; // 拖过之后那一下 click 不该被当成"点遮罩关闭"
let pinch = null; // { distance, scale, cx, cy }

function onPointerDown(event) {
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  dragged = false;
  if (pointers.size === 2) pinch = startPinch();
  // 指针捕获只是让手指/鼠标滑出舞台之后拖动不断——拿不到无所谓，但它会对"当前不活跃"
  // 的 pointerId 抛 NotFoundError，不接住的话整个 pointerdown 处理就在这里断了，
  // 后面的捏合初始化根本轮不到执行。所以放在最后，并且包起来。
  try {
    event.currentTarget.setPointerCapture?.(event.pointerId);
  } catch {
    /* 捕获不到就算了 */
  }
}

function pointerList() {
  return [...pointers.values()];
}

function startPinch() {
  const [a, b] = pointerList();
  return {
    distance: Math.hypot(a.x - b.x, a.y - b.y) || 1,
    scale: scale.value,
    cx: (a.x + b.x) / 2,
    cy: (a.y + b.y) / 2,
  };
}

function onPointerMove(event) {
  const previous = pointers.get(event.pointerId);
  if (!previous) return;
  const next = { x: event.clientX, y: event.clientY };
  pointers.set(event.pointerId, next);

  if (pointers.size >= 2 && pinch) {
    const [a, b] = pointerList();
    const distance = Math.hypot(a.x - b.x, a.y - b.y) || 1;
    dragged = true;
    zoomAt((distance / pinch.distance) * pinch.scale, pinch.cx, pinch.cy);
    return;
  }
  const dx = next.x - previous.x;
  const dy = next.y - previous.y;
  if (Math.abs(dx) + Math.abs(dy) > 2) dragged = true;
  offset.value = { x: offset.value.x + dx, y: offset.value.y + dy };
}

function onPointerUp(event) {
  pointers.delete(event.pointerId);
  if (pointers.size < 2) pinch = null;
}

/** 点遮罩关闭；点在图上不关（那一下多半是想拖或想双击放大）。 */
function onBackdropClick(event) {
  if (dragged) {
    dragged = false;
    return;
  }
  if (event.target === image.value) return;
  closeLightbox();
}

// ---------- 打开 / 关闭的副作用 ----------
// Esc 用捕获阶段 + stopPropagation：解析弹窗里点开的大图，不这么做一下 Esc
// 会把大图和它下面的 ExamModal 一起关掉。
function onKeydown(event) {
  if (event.key !== "Escape") return;
  event.stopPropagation();
  closeLightbox();
}

let restoreOverflow = null;

watch(open, (value) => {
  if (value) {
    ready.value = false;
    restoreOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeydown, true);
    window.addEventListener("resize", fitToStage);
    // 图缓存命中时 load 事件不会再来一次，这里补一次。
    nextTick(() => {
      if (image.value?.complete) fitToStage();
    });
  } else {
    pointers.clear();
    pinch = null;
    if (restoreOverflow !== null) document.body.style.overflow = restoreOverflow;
    restoreOverflow = null;
    window.removeEventListener("keydown", onKeydown, true);
    window.removeEventListener("resize", fitToStage);
  }
});

onBeforeUnmount(() => {
  // 组件先于 lightbox 被销毁时（路由跳走），别把 body 锁在 hidden 上。
  if (restoreOverflow !== null) document.body.style.overflow = restoreOverflow;
  window.removeEventListener("keydown", onKeydown, true);
  window.removeEventListener("resize", fitToStage);
});
</script>

<template>
  <div
    v-if="open"
    class="lightbox"
    role="dialog"
    aria-modal="true"
    aria-label="查看图片"
    @click="onBackdropClick"
  >
    <div class="lightbox-bar" @click.stop>
      <span class="lightbox-name">{{ lightbox.alt || "题目配图" }}</span>
      <span class="lightbox-zoom">{{ percent }}%</span>
      <button type="button" aria-label="缩小" @click="zoomBy(1 / 1.4)">−</button>
      <button type="button" aria-label="放大" @click="zoomBy(1.4)">＋</button>
      <button type="button" @click="reset">复位</button>
      <button type="button" class="is-close" aria-label="关闭" @click="closeLightbox">✕</button>
    </div>

    <div
      ref="stage"
      class="lightbox-stage"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @dblclick="onDoubleClick"
    >
      <img
        ref="image"
        :src="lightbox.src"
        :alt="lightbox.alt"
        :style="{
          transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
          visibility: ready ? 'visible' : 'hidden',
        }"
        draggable="false"
        @load="fitToStage"
        @error="ready = true"
      />
    </div>

    <p class="lightbox-hint">滚轮缩放 · 拖动平移 · 双击复位 · Esc 关闭</p>
  </div>
</template>

<style scoped>
/* 200：压过 .exam-overlay/.exam-dialog 的 100/101——解析弹窗里点开的图要盖在弹窗之上。 */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  flex-direction: column;
  background: rgba(20, 26, 24, 0.88);
  user-select: none;
  touch-action: none; /* 交给 pointer 事件，否则移动端会被浏览器的滚动/缩放抢走 */
}
.lightbox-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  color: #edf4ee;
  font-size: 12px;
}
.lightbox-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lightbox-zoom {
  min-width: 46px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}
.lightbox-bar button {
  min-width: 30px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid rgba(237, 244, 238, 0.3);
  border-radius: var(--control-radius, 4px);
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  line-height: 1;
}
.lightbox-bar button:hover {
  background: rgba(237, 244, 238, 0.14);
}
.lightbox-bar button.is-close {
  margin-left: 4px;
}
.lightbox-stage {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: grab;
}
.lightbox-stage:active {
  cursor: grabbing;
}
.lightbox-stage img {
  max-width: none; /* 全局那条 max-width:100% 会在这里把缩放钳死 */
  transform-origin: center center;
  will-change: transform;
}
.lightbox-hint {
  margin: 0;
  padding: 6px 12px 10px;
  color: rgba(237, 244, 238, 0.55);
  font-size: 11px;
  text-align: center;
}
@media (max-width: 640px) {
  .lightbox-hint {
    display: none; /* 手机上没有滚轮，这行提示只是占地方 */
  }
}
</style>
