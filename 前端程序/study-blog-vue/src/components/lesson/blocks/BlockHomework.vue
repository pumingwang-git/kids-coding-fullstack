<script setup>
// 课后练习块（绑卷）：题目列表看板直接嵌在课时页里，不再有中间入口卡片。
//
// 看板数据从候考接口现拉（fetchLessonHomeworkEntry）：块 DTO 按保密口径只有投放规则，
// 题目大纲只在作答入口的 entry 里下发。加载失败时回退成原来的入口卡片——
// 学生能进作业比看到看板重要。
//
// 点「开始挑战 / 开始作答」仍跳到独立作答页（autostart=1 直接开考，anchor 锚定题目），
// 作答需要整页的编程题工作区，嵌在课时页里展不开。
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import LessonIcon from "../LessonIcon.vue";
import HomeworkBoard from "../../exam/HomeworkBoard.vue";
import { fetchLessonHomeworkEntry, fetchLessonHomeworkHistory } from "../../../services/exam";

const props = defineProps({
  block: { type: Object, required: true },
  lessonId: { type: Number, required: true },
});
const router = useRouter();

const entry = ref(null);
const loadFailed = ref(false);

onMounted(async () => {
  try {
    entry.value = await fetchLessonHomeworkEntry(props.lessonId, props.block.id);
  } catch {
    // 401 由全局 session:expired 接管；其余失败回退到入口卡片，不挡学生进作业。
    loadFailed.value = true;
  }
});

// 看板只在拿到题目大纲时启用；旧后端没有 paper.questions，自动回退。
const boardReady = computed(
  () => entry.value && (entry.value.paper.questions || []).length > 0,
);

function enter(query = {}) {
  router.push({
    name: "lesson-homework",
    params: { lessonId: props.lessonId, blockId: props.block.id },
    query,
  });
}

function onStart(problemIdNo) {
  // autostart 让作答页跳过自己的看板直接开考；anchor 锚到被点的那道题。
  enter({ autostart: "1", ...(problemIdNo ? { anchor: problemIdNo } : {}) });
}

function onReview(attemptId) {
  enter({ review: String(attemptId) });
}

// ---------- 回退卡片（加载失败 / 旧后端） ----------

const done = computed(() => !!props.block.completed);
const attemptText = computed(() =>
  props.block.attempt_limit ? `最多作答 ${props.block.attempt_limit} 次` : "作答次数不限",
);
const dueText = computed(() => {
  if (!props.block.due_at) return "不限截止时间";
  const due = new Date(props.block.due_at);
  const overdue = due.getTime() < Date.now();
  const when = due.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return overdue ? `已过截止时间（${when}）` : `截止 ${when}`;
});
</script>

<template>
  <div class="block-homework">
    <!-- 看板嵌在课时页里：exam-root/qz 提供样式令牌与按钮皮肤，hw-shell 抵消
         exam-root 的整页布局（100vh 最小高度是给独立作答页的）。 -->
    <div v-if="boardReady" class="exam-root qz is-playful hw-shell">
      <HomeworkBoard
        embedded
        :entry="entry"
        :history-loader="(params) => fetchLessonHomeworkHistory(lessonId, block.id, params)"
        @start="onStart"
        @review="onReview"
      />
    </div>

    <p v-else-if="!loadFailed && !entry" class="muted hw-loading">正在加载作业…</p>

    <!-- 回退：原来的入口卡片 -->
    <section v-else-if="!boardReady" class="homework-bridge" aria-labelledby="homework-title">
      <div class="homework-bridge-icon"><LessonIcon name="homework" :size="22" /></div>
      <div class="homework-bridge-copy">
        <h3 id="homework-title">{{ done ? "本节作业已完成" : "本节作业" }}</h3>
        <p>
          {{
            done
              ? "可以回看上次的成绩与解析；还有次数时也可以再做一次。"
              : "进入后可看到题目列表，逐题开始挑战，全部交卷后本块自动完成。"
          }}
        </p>
        <p class="homework-meta">
          <span class="ltag" :class="{ 'on-accent': done }">{{ done ? "已完成" : "未提交" }}</span>
          <span v-if="block.question_count" class="ltag">共 {{ block.question_count }} 题</span>
          <span class="ltag">{{ attemptText }}</span>
          <span class="ltag" :class="{ 'on-warn': block.due_at }">{{ dueText }}</span>
        </p>
        <div class="homework-actions">
          <button class="lbtn lbtn-chunky lbtn-accent" type="button" @click="enter()">
            {{ done ? "再做一次" : "去做作业" }}
          </button>
          <button
            v-if="done"
            class="lbtn lbtn-chunky"
            type="button"
            @click="enter({ review: 'last' })"
          >
            查看上次成绩
          </button>
        </div>
      </div>
    </section>

    <div class="block-foot">
      <slot name="prev" />
      <slot name="next" />
      <span class="hint">{{ done ? "本块已完成" : "作业交卷后本块自动标记完成" }}</span>
    </div>
  </div>
</template>

<style scoped>
.hw-shell {
  /* exam-root 的页面级布局在嵌入场景全部卸掉，只留令牌与组件皮肤。 */
  min-height: 0;
  background: transparent;
  border-radius: var(--radius);
}
.hw-loading {
  padding: 1rem 0;
}
.homework-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 0;
}
.homework-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
</style>
