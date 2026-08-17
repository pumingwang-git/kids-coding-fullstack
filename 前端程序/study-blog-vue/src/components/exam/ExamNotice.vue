<script setup>
// 考试须知页。notice_ack_required 为真时必须勾选才能继续——这是链接上配的规则，
// 前端只负责呈现与拦截，规则本身由后台设定（见《4、后台考试链接-管理模块》5.2）。
import { ref } from "vue";
import MarkdownBody from "./MarkdownBody.vue";

const props = defineProps({
  notice: { type: String, default: "" },
  ackRequired: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["accept", "back"]);

const acked = ref(false);
const canGo = () => !props.ackRequired || acked.value;
</script>

<template>
  <div class="exam-narrow">
    <div class="sticker" style="padding: 2rem">
      <h1 style="margin-top: 0">考试须知</h1>
      <MarkdownBody :source="notice" />

      <label
        v-if="ackRequired"
        style="
          display: flex;
          gap: 0.6rem;
          align-items: center;
          margin-top: 1.5rem;
          font-weight: 700;
        "
      >
        <input v-model="acked" type="checkbox" style="width: 1.1rem; height: 1.1rem" />
        我已阅读并同意以上须知
      </label>

      <div style="display: flex; gap: 1rem; margin-top: 1.5rem; flex-wrap: wrap">
        <button class="btn-chunky" type="button" @click="emit('back')">返回</button>
        <button
          class="btn-chunky btn-primary"
          type="button"
          :disabled="!canGo() || busy"
          @click="emit('accept')"
        >
          开始作答
        </button>
      </div>
    </div>
  </div>
</template>
