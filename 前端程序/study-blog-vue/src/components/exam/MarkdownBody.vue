<script setup>
// 题干、选项、须知、解析的唯一渲染出口。渲染管线（空位标记 + DOMPurify）
// 与后台整卷预览同源，见 services/markdown.js。
import { computed } from "vue";
import { renderMarkdown } from "../../services/markdown";
import { openLightbox } from "../../stores/lightbox";

const props = defineProps({
  source: { type: String, default: "" },
  inline: { type: Boolean, default: false },
});

const html = computed(() => renderMarkdown(props.source));

/**
 * 点题干配图 → 开大图。用事件委托而不是给每个 <img> 绑事件：内容是 v-html 塞进来的，
 * 每次 source 变化整块都换新节点，直接绑必然绑到已经被替换掉的节点上。
 *
 * 题干里的图默认只占正文宽的 1/4（见下面的 CSS），几何题的辅助线、图形推理题的细节
 * 在那个尺寸下根本看不清——所以这不是锦上添花，是能不能答题的问题。
 */
function onClick(event) {
  // inline 模式只用在选项里，而选项整块是个 <button>：在那儿劫持点击，学员想看清
  // 图形选项反而先把这道题给答了。选项图的放大另做，别拿考试的作答动作换。
  if (props.inline) return;
  const image = event.target.closest?.("img");
  // src 被渲染出口白名单摘掉的坏图（外链 / data:）没什么可放大的。
  if (!image || !image.getAttribute("src")) return;
  openLightbox(image.getAttribute("src"), image.getAttribute("alt") || "");
}
</script>

<template>
  <!-- v-html 的内容已经过 DOMPurify；入库不净化是有意的（见 Problem.stem 注释）。 -->
  <span v-if="inline" class="md-body md-inline" v-html="html" @click="onClick" />
  <div v-else class="md-body" v-html="html" @click="onClick" />
</template>

<style scoped>
.md-inline :deep(p) {
  display: inline;
  margin: 0;
}
/* 题干配图。不设 max-height——几何图形被压扁比溢出更糟。 */
.md-body :deep(img) {
  max-width: 100%;
  height: auto;
}
/* 没显式设过尺寸的默认占正文宽的 1/4，与后台 admin.css 里那条是同一个值——
   两边不一致，老师预览看到的大小就和学员看到的不一样。
   :not([width]) 不能省：CSS 的 width 会盖过 HTML 属性，省了作者就调不动尺寸。 */
.md-body :deep(img:not([width]):not([style*="width"])) {
  width: 25%;
}
/* 题干图可点开看大图（见 onClick）。给个放大镜光标，否则没人知道点了会有反应。
   选项里的行内图不参与，光标也就不该变。 */
.md-body:not(.md-inline) :deep(img[src]) {
  cursor: zoom-in;
}
/* src 被白名单摘掉的图（外链 / data:）。留个看得出来的占位，别让一道题悄悄少张图。 */
.md-body :deep(img[data-blocked-src]) {
  min-width: 120px;
  min-height: 32px;
  border: 1px dashed currentColor;
  border-radius: 6px;
  opacity: 0.5;
}
</style>
