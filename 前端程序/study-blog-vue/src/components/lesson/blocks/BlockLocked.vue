<script setup>
// 锁定态：两种 lock_reason，两套文案 + 两个出口（交接文档 14 §4.5）。
//
// 合并成一句「尚未解锁」是不行的——学生看到锁不知道该去掏钱还是该去学习：
//   not_enrolled 权限锁 → 去课包详情页开通
//   sequential   顺序锁 → 回到未完成的块继续学
import { computed } from "vue";
import LessonIcon from "../LessonIcon.vue";

const props = defineProps({
  block: { type: Object, required: true },
  lesson: { type: Object, required: true },
});
defineEmits(["go-course", "goto-next-todo"]);

const paywalled = computed(() => props.block.lock_reason === "not_enrolled");

const policyText = computed(() => {
  if (props.lesson.open_policy === "first_n" && props.lesson.trial_block_count) {
    return `本课时按「前 ${props.lesson.trial_block_count} 块试看」开放，后面的内容需要开通课包。`;
  }
  return "本课时未对未开通的用户开放。";
});

const total = computed(() => props.lesson.progress?.total ?? 0);
const done = computed(() => props.lesson.progress?.done ?? 0);
</script>

<template>
  <div class="locked-state">
    <div class="lk-ico"><LessonIcon :name="paywalled ? 'lock' : 'steps'" :size="24" /></div>
    <p class="leyebrow">{{ paywalled ? "需要开通" : "按顺序解锁" }}</p>
    <h3 tabindex="-1" class="block-anchor">{{ block.title }}</h3>

    <p v-if="paywalled">
      {{ policyText }}<br />
      开通后可学习本课包全部内容块。
    </p>
    <p v-else>
      本块设置为按教学顺序解锁，完成前面全部内容块后自动开放。<br />
      当前进度 {{ done }} / {{ total }}。
    </p>

    <button
      v-if="paywalled"
      class="lbtn lbtn-chunky lbtn-accent"
      type="button"
      @click="$emit('go-course')"
    >
      <LessonIcon name="unlockCart" :size="14" />查看课包并开通
    </button>
    <button
      v-else
      class="lbtn lbtn-chunky lbtn-accent"
      type="button"
      @click="$emit('goto-next-todo')"
    >
      回到未完成的内容块
    </button>
  </div>
</template>
