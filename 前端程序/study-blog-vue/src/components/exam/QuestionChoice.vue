<script setup>
// 单选 / 多选 / 判断三种共用。
//
// 与参考 DEMO 最根本的差别：DEMO 是闯关——答错抖一下并复位，答对才准进下一关；
// 这里是考试——选了就存，不给任何对错反馈，答错也能往下走。
import { computed } from "vue";
import MarkdownBody from "./MarkdownBody.vue";

const props = defineProps({
  question: { type: Object, required: true },
  answer: { type: Object, default: null },
});
const emit = defineEmits(["change"]);

const multiple = computed(() => props.question.type === "multi_choice");
// 判断题只有对/错两个选项，排成两栏比竖着叠两行更像卷子，也省掉半屏空白。
const judge = computed(() => props.question.type === "judge");
const picked = computed(() => {
  const value = props.answer?.picked;
  if (multiple.value) return Array.isArray(value) ? value : [];
  return value ? [value] : [];
});

function toggle(label) {
  if (!multiple.value) {
    emit("change", { type: props.question.type, picked: label });
    return;
  }
  const next = new Set(picked.value);
  if (next.has(label)) next.delete(label);
  else next.add(label);
  emit("change", { type: "multi_choice", picked: [...next].sort() });
}
</script>

<template>
  <div>
    <p v-if="multiple" class="hint-line">多选题：选出全部正确选项。</p>
    <div class="option-list" :class="{ 'is-judge': judge }" role="group">
      <button
        v-for="option in question.options"
        :key="option.label"
        type="button"
        class="option"
        :class="{ 'is-picked': picked.includes(option.label), 'is-multi': multiple }"
        :aria-pressed="picked.includes(option.label)"
        @click="toggle(option.label)"
      >
        <span class="badge">{{ option.label }}</span>
        <span class="opt-text"><MarkdownBody :source="option.content" inline /></span>
      </button>
    </div>
  </div>
</template>
