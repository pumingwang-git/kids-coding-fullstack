<script setup>
// 课时加载页（交接文档 14 §3.2）。
//
// 三段文案对应真实动作：① 发出 GET /api/lessons/{id} ② 响应到达、解析 lock_reason
// ③ 计算落点块。不是假进度条——每段由父组件推进。
//
// 失败时停在失败的那一段变红 + 重试按钮，**不跳转**：跳到一个空壳比停在加载页更难排查。
import LessonIcon from "./LessonIcon.vue";

defineProps({
  // 0..3；3 = 全部完成
  step: { type: Number, default: 0 },
  error: { type: String, default: "" },
  lessonTitle: { type: String, default: "" },
  courseTitle: { type: String, default: "" },
  gone: { type: Boolean, default: false },
});
defineEmits(["retry"]);

const STEPS = ["拉取课时内容", "校验学习权限", "定位到第一个内容块"];
</script>

<template>
  <div class="lesson-loading" :class="{ 'is-gone': gone }" role="status" aria-live="polite">
    <LessonIcon
      v-if="!error"
      name="spinner"
      :size="56"
      class="ring-spin"
      style="color: var(--accent)"
    />
    <div>
      <p class="load-title">{{ error ? "课时加载失败" : "正在准备课时" }}</p>
      <p class="load-sub">
        {{ courseTitle }}<template v-if="courseTitle && lessonTitle"> · </template>{{ lessonTitle }}
      </p>
    </div>

    <div class="load-steps">
      <div
        v-for="(text, i) in STEPS"
        :key="text"
        class="load-step"
        :class="{ 'is-done': i < step, 'is-active': i === step && !error }"
      >
        <span class="load-dot"><LessonIcon name="check" :size="9" /></span>
        <span :class="{ 'load-error': error && i === step }">{{ text }}</span>
      </div>
    </div>

    <div class="load-bar">
      <i :style="{ transform: `scaleX(${Math.min(1, step / STEPS.length)})` }"></i>
    </div>

    <p v-if="error" class="load-error" style="font-size: 12px">{{ error }}</p>
    <button v-if="error" class="lbtn lbtn-chunky lbtn-accent" type="button" @click="$emit('retry')">
      重新加载
    </button>
  </div>
</template>
