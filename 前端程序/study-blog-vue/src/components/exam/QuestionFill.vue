<script setup>
// 填空题。题干里的空位由 markBlanksInHtml 渲染成可见的虚线条，
// 输入框单独列在下方按 blank_key 对应——把输入框注进题干里要处理光标、
// 换行、代码块内误命中等一堆边界，收益却只是"看起来更像卷子"。
import { computed } from "vue";

const props = defineProps({
  question: { type: Object, required: true },
  answer: { type: Object, default: null },
});
const emit = defineEmits(["change"]);

const blanks = computed(() => props.question.blank_keys || []);
const values = computed(() => props.answer?.blanks || {});

function update(key, value) {
  emit("change", { type: "fill", blanks: { ...values.value, [key]: value } });
}
</script>

<template>
  <div>
    <!-- 空位横排：两三个空并排一行，而不是每空独占一整行——三空题以内不会再
         在题干下面拖出一片空白。空位多了自然换行。 -->
    <div class="blank-list">
      <div class="blank-item" v-for="(key, index) in blanks" :key="key">
        <label :for="`blank-${question.uid ?? question.problem_id_no}-${key}`"
          >第 {{ index + 1 }} 空</label
        >
        <input
          :id="`blank-${question.uid ?? question.problem_id_no}-${key}`"
          class="blank-input"
          type="text"
          autocomplete="off"
          :value="values[key] || ''"
          placeholder="在这里输入答案…"
          @input="update(key, $event.target.value)"
        />
      </div>
    </div>
    <p v-if="!blanks.length" class="muted">这道题没有可填写的空位，请联系老师。</p>
    <p v-else class="hint-line" style="margin: 12px 0 0">
      大小写、首尾空格、全角半角都会自动忽略，放心填。
    </p>
  </div>
</template>
