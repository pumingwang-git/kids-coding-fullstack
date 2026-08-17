<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import MarkdownBody from "../components/exam/MarkdownBody.vue";
import { request } from "../services/auth";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const detail = ref(null);
const loading = ref(true);
const error = ref("");
const submitting = ref(false);
const result = ref(null);
const picked = ref([]);
const blanks = ref({});
const isMulti = computed(() => detail.value?.question.type === "multi_choice");
const canReview = computed(() => detail.value?.mistake.can_review_here);
async function load() {
  loading.value = true;
  error.value = "";
  result.value = null;
  picked.value = [];
  blanks.value = {};
  try {
    detail.value = await request(`/api/student/mistakes/${route.params.mistakeId}`);
  } catch (reason) {
    error.value = reason.message || "这道错题暂时无法打开。";
  } finally {
    loading.value = false;
  }
}
function choose(label) {
  if (isMulti.value)
    picked.value = picked.value.includes(label)
      ? picked.value.filter((item) => item !== label)
      : [...picked.value, label];
  else picked.value = [label];
}
function answerPayload() {
  return detail.value.question.type === "fill"
    ? { blanks: blanks.value }
    : { picked: isMulti.value ? picked.value : picked.value[0] || "" };
}
async function submit() {
  submitting.value = true;
  error.value = "";
  try {
    result.value = await request(`/api/student/mistakes/${route.params.mistakeId}/review`, {
      method: "POST",
      body: JSON.stringify({ answer: answerPayload(), source: "single" }),
    });
    await loadHistory();
  } catch (reason) {
    error.value = reason.message || "提交失败，请检查答案后重试。";
  } finally {
    submitting.value = false;
  }
}
async function loadHistory() {
  const fresh = await request(`/api/student/mistakes/${route.params.mistakeId}`);
  detail.value.reviews = fresh.reviews;
  detail.value.mistake = fresh.mistake;
}
function dateTime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-";
}
watch(() => route.params.mistakeId, load);
onMounted(load);
</script>

<template>
  <main class="kids-page mistake-detail-page">
    <RouterLink class="back-link" :to="`/areas/${areaKey}/tasks/mistakes`"
      ><AppIcon name="arrow-left" :size="18" /> 返回我的错题</RouterLink
    >
    <p v-if="loading" class="detail-message">正在加载错题...</p>
    <section v-else-if="error && !detail" class="detail-message detail-error" role="alert">
      <p>{{ error }}</p>
      <button class="button button-primary" @click="load">重新加载</button>
    </section>
    <template v-else-if="detail">
      <header class="detail-heading">
        <div>
          <h1>{{ detail.mistake.title }}</h1>
          <p>
            {{ detail.mistake.source_label }} · 已答错 {{ detail.mistake.wrong_count }} 次 · 当前{{
              detail.mistake.mastery_level === "mastered" ? "已掌握" : "待复习"
            }}
          </p>
        </div>
        <span class="detail-status">{{
          detail.mistake.can_review_here ? "重做此题" : "回原入口重做"
        }}</span>
      </header>
      <section class="question-surface">
        <MarkdownBody :source="detail.question.stem" />
        <div
          v-if="canReview && detail.question.type !== 'fill'"
          class="answer-options"
          role="group"
          aria-label="选择答案"
        >
          <button
            v-for="option in detail.question.options"
            :key="option.label"
            type="button"
            :class="{ selected: picked.includes(option.label) }"
            @click="choose(option.label)"
          >
            <b>{{ option.label }}</b
            ><MarkdownBody inline :source="option.content" />
          </button>
        </div>
        <div v-else-if="canReview" class="fill-answers">
          <label v-for="key in detail.question.blank_keys" :key="key"
            >填写 {{ key }}<input v-model="blanks[key]" :name="key" autocomplete="off"
          /></label>
        </div>
        <p v-else class="code-note">
          这道编程题已归入错题本。为了继续使用原题的测试数据与判题规则，请从它原来的课程、作业或考试入口重新提交代码。
        </p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button
          v-if="canReview"
          class="button button-primary submit-answer"
          type="button"
          :disabled="submitting"
          @click="submit"
        >
          {{ submitting ? "正在判定..." : "提交重做" }}
        </button>
      </section>
      <section
        v-if="result"
        class="review-result"
        :class="result.is_correct ? 'result-correct' : 'result-wrong'"
      >
        <h2>{{ result.is_correct ? "这次答对了" : "这次还需要再想一想" }}</h2>
        <p>掌握度已更新，下次建议复习：{{ dateTime(result.next_review_at) }}。</p>
        <div v-if="result.analysis">
          <h3>题目解析</h3>
          <MarkdownBody :source="result.analysis" />
        </div>
      </section>
      <section class="review-history">
        <h2>复习记录</h2>
        <p v-if="!detail.reviews.length">还没有重做记录。</p>
        <ol v-else>
          <li v-for="review in detail.reviews" :key="review.id">
            <span :class="review.is_correct ? 'history-correct' : 'history-wrong'">{{
              review.is_correct ? "答对" : "答错"
            }}</span
            ><time>{{ dateTime(review.reviewed_at) }}</time>
          </li>
        </ol>
      </section>
    </template>
  </main>
</template>

<style scoped>
.mistake-detail-page {
  max-width: 920px;
}
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 20px;
  color: var(--accent);
  font-weight: 800;
}
.detail-heading {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: start;
  padding: 26px 28px;
  border-radius: 20px 8px 20px 8px;
  background: var(--area-surface);
  color: #203c5b;
}
.detail-heading h1 {
  margin: 0;
  font: 800 30px/1.28 var(--font-display);
  letter-spacing: 0;
}
.detail-heading p {
  margin: 9px 0 0;
  color: #54708d;
}
.detail-status {
  flex: 0 0 auto;
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(239, 107, 74, 0.14);
  color: #a44731;
  font-size: 12px;
  font-weight: 800;
}
.question-surface,
.review-history,
.review-result,
.detail-message {
  margin-top: 18px;
  padding: 26px 28px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--kids-panel);
}
.answer-options {
  display: grid;
  gap: 10px;
  margin-top: 25px;
}
.answer-options button {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  min-height: 48px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--ink);
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.answer-options button:hover,
.answer-options button.selected {
  border-color: var(--accent);
  background: var(--mint);
}
.answer-options b {
  display: grid;
  place-items: center;
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: rgba(47, 128, 110, 0.12);
  color: var(--accent);
}
.fill-answers {
  display: grid;
  gap: 14px;
  margin-top: 22px;
}
.fill-answers label {
  display: grid;
  gap: 7px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
}
.fill-answers input {
  min-height: 44px;
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: transparent;
  color: var(--ink);
}
.submit-answer {
  margin-top: 24px;
}
.form-error {
  margin: 14px 0 0;
  color: var(--danger);
}
.code-note {
  margin: 22px 0 0;
  padding: 14px;
  border-radius: 4px;
  background: rgba(244, 189, 91, 0.16);
  color: #6f541e;
  line-height: 1.7;
}
.review-result h2,
.review-history h2 {
  margin: 0;
  font: 800 22px/1.25 var(--font-display);
  letter-spacing: 0;
}
.review-result p {
  margin: 8px 0 0;
  color: var(--muted);
}
.review-result h3 {
  margin: 22px 0 10px;
  font-size: 16px;
}
.result-correct {
  border-color: rgba(47, 128, 110, 0.35);
}
.result-wrong {
  border-color: rgba(185, 92, 80, 0.36);
}
.review-history ol {
  display: grid;
  gap: 9px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}
.review-history li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 9px;
  border-bottom: 1px solid var(--line);
}
.review-history time {
  color: var(--muted);
  font-size: 13px;
}
.history-correct,
.history-wrong {
  font-weight: 800;
}
.history-correct {
  color: var(--accent);
}
.history-wrong {
  color: var(--danger);
}
.detail-message {
  text-align: center;
  color: var(--muted);
}
.detail-error {
  color: var(--danger);
}
@media (max-width: 600px) {
  .detail-heading {
    padding: 22px 20px;
    flex-direction: column;
  }
  .detail-heading h1 {
    font-size: 25px;
  }
  .question-surface,
  .review-history,
  .review-result,
  .detail-message {
    padding: 20px 16px;
  }
  .review-history li {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }
}
</style>
