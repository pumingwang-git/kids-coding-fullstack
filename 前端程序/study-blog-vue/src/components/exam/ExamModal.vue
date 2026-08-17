<script setup>
// 考试页通用弹窗：提交记录、判定详情、交卷确认都走这一个。
//
// 用 reka-ui 的 Dialog 而不是自己写：焦点陷阱、ESC 关闭、背景滚动锁、aria-modal
// 这四样自己写十有八九会漏一样，而这是考试流程里最不能出错的交互。
//
// Portal 指向 .exam-root 内专用的 .exam-modal-layer，而不是默认的 body——弹窗里要渲染
// 判定横幅、测试点卡片、代码块，这些样式全都作用域在 .exam-root 之内。挂到 body 上
// 就得在组件里再抄一份颜色，改主题必漏。
// 为什么不能直接指 .exam-root：传送门节点会跟 ExamView 阶段切换（候考/作答/结果）
// 插拔的节点共用同一个父容器，同一次渲染冲刷里两边一起动，锚点失效整页白屏。
// 专用挂载层是静态节点，阶段切换永远碰不到它。
import { DialogContent, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from "reka-ui";

defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "" },
  wide: { type: Boolean, default: false },
  portalTarget: { type: String, default: ".exam-modal-layer" },
});
const emit = defineEmits(["update:open"]);
</script>

<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal :to="portalTarget">
      <DialogOverlay class="exam-overlay" />
      <DialogContent class="exam-dialog" :class="{ 'is-wide': wide }">
        <div class="dialog-head">
          <DialogTitle as="h2">{{ title }}</DialogTitle>
          <button
            class="dialog-close"
            type="button"
            aria-label="关闭"
            @click="emit('update:open', false)"
          >
            ✕
          </button>
        </div>
        <div class="dialog-body"><slot /></div>
        <div v-if="$slots.actions" class="dialog-actions"><slot name="actions" /></div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
