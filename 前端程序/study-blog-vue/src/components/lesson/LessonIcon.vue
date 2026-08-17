<script setup>
// 学习页图标集：内联 SVG，1.6px 描边，与纸面细线风格一致。
// 单独抽一个组件而不是每处写 SVG——同一个图标在顶栏、抽屉、锁定页各出现一次，
// 三处各画一遍必然慢慢长歪。
//
// 两个锁的区分是有语义的（交接文档 14 §4.5）：
//   lock  = 权限锁（Gate A，没开通）—— 实心锁
//   steps = 顺序锁（Gate B，没轮到）—— 阶梯，一级一级来
import { computed } from "vue";

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
});

const PATHS = {
  arrowLeft: '<path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>',
  arrowRight: '<path d="M5 12h14"/><path d="M12 5l7 7-7 7"/>',
  chevronLeft: '<path d="M15 18l-6-6 6-6"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  exit: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
  moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
  steps: '<path d="M3 20h5v-5h5v-5h5V5h3"/>',
  unlockCart:
    '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 7.6-1.8"/>',
  cert: '<circle cx="12" cy="9" r="5"/><path d="M8.5 13.5L7 21l5-2.5L17 21l-1.5-7.5"/>',
  spinner: '<circle cx="12" cy="12" r="9" opacity=".2"/><path d="M12 3a9 9 0 0 1 9 9"/>',
  // 块类型
  video: '<rect x="3" y="5.5" width="13" height="13" rx="2"/><path d="M16 10.5l5-3v9l-5-3z"/>',
  markdown:
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  practice:
    '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9.4 9.2a2.6 2.6 0 1 1 3.4 2.5c-.6.2-1 .8-1 1.5v.3"/><path d="M11.8 16.4h.01"/>',
  homework: '<path d="M9 17l-5-5 5-5"/><path d="M15 7l5 5-5 5"/>',
  materials:
    '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5"/>',
};

const inner = computed(() => PATHS[props.name] || PATHS.markdown);
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="inner"
  ></svg>
</template>
