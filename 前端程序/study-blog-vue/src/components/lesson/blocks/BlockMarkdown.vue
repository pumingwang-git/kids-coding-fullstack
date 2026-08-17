<script setup>
// 图文块。完成口径：学生点底部「完成，继续下一块」（source=manual，交接文档 14 §5.1）。
// 本组件不调接口、不改路由——只 emit("complete")，由壳统一上报（§7.3）。
import { renderMarkdown } from "../../../services/markdown";

defineProps({ block: { type: Object, required: true } });
</script>

<template>
  <article
    class="lcard block-article markdown-body"
    v-html="renderMarkdown(block.content_md)"
  ></article>
</template>

<style scoped>
.block-article :deep(h1),
.block-article :deep(h2),
.block-article :deep(h3) {
  font-family: var(--font-display);
  font-weight: 500;
  letter-spacing: -0.8px;
  line-height: 1.3;
  margin: 1.2em 0 0.5em;
}
.block-article :deep(h1:first-child),
.block-article :deep(h2:first-child) {
  margin-top: 0;
}
.block-article :deep(p) {
  margin: 0.8em 0;
}
.block-article :deep(ul),
.block-article :deep(ol) {
  padding-left: 1.6em;
  margin: 0.8em 0;
}
.block-article :deep(li) {
  margin: 0.3em 0;
}
.block-article :deep(pre) {
  background: var(--editor-bg);
  color: var(--editor-fg);
  border-radius: var(--card-radius);
  padding: 14px 18px;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.8;
  margin: 14px 0;
}
.block-article :deep(code) {
  font-family: var(--font-mono);
  background: var(--mint);
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 0.92em;
}
.block-article :deep(pre code) {
  background: none;
  padding: 0;
}
.block-article :deep(blockquote) {
  margin: 0.8em 0;
  padding: 0.2em 1em;
  border-left: 2px solid var(--accent);
  color: var(--muted);
}
.block-article :deep(table) {
  border-collapse: collapse;
  margin: 1em 0;
  width: 100%;
  font-size: 13px;
}
.block-article :deep(th),
.block-article :deep(td) {
  border: 1px solid var(--line);
  padding: 8px 12px;
  text-align: left;
}
.block-article :deep(th) {
  background: var(--paper);
}
.block-article :deep(img) {
  max-width: 100%;
  border-radius: var(--card-radius);
}
.block-article :deep(a) {
  color: var(--accent);
}
</style>
