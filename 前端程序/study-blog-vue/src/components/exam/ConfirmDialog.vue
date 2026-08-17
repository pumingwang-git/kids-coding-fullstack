<script setup>
// 交卷确认 / 须知确认 / 判题异常告警共用。壳子走 ExamModal（焦点陷阱、ESC、
// 背景滚动锁、aria-modal 都在那里），这里只管两个按钮和 tone。
import ExamModal from "./ExamModal.vue";

defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "" },
  confirmText: { type: String, default: "确定" },
  cancelText: { type: String, default: "取消" },
  tone: { type: String, default: "primary" }, // primary / danger
  busy: { type: Boolean, default: false },
  portalTarget: { type: String, default: ".exam-modal-layer" },
});
const emit = defineEmits(["update:open", "confirm"]);
</script>

<template>
  <ExamModal
    :open="open"
    :title="title"
    :portal-target="portalTarget"
    @update:open="emit('update:open', $event)"
  >
    <slot />
    <template #actions>
      <button class="btn" type="button" @click="emit('update:open', false)">
        {{ cancelText }}
      </button>
      <button
        class="btn"
        :class="tone === 'danger' ? 'btn-danger' : 'btn-primary'"
        type="button"
        :disabled="busy"
        @click="emit('confirm')"
      >
        {{ busy ? "处理中…" : confirmText }}
      </button>
    </template>
  </ExamModal>
</template>
