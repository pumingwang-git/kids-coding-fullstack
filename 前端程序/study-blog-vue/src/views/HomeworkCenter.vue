<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { fetchHomeworkTasks } from "../services/studentTasks";
import { taskEntryPath } from "../services/taskEntry";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const items = ref([]);
const counts = ref({});
const historyExpanded = ref(false);
const loading = ref(true);
const error = ref("");
const heroImage = "/assets/otter-writing.png";

const segments = computed(() => [
  { key: "due_48h", title: "48 小时内", items: items.value.filter(item => item.segment === "due_48h") },
  { key: "this_week", title: "本周", items: items.value.filter(item => item.segment === "this_week") },
  { key: "later", title: "更晚或没有截止", items: items.value.filter(item => item.segment === "later") },
]);
const historyItems = computed(() => items.value.filter(
  item => ["overdue", "submitted", "graded"].includes(item.segment),
));
const mainlineTotal = computed(() => (
  (counts.value.due_48h || 0) + (counts.value.this_week || 0) + (counts.value.later || 0)
));
const historyTotal = computed(() => (
  (counts.value.overdue || 0) + (counts.value.submitted || 0) + (counts.value.graded || 0)
));

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const result = await fetchHomeworkTasks();
    items.value = result.items || [];
    counts.value = result.counts || {};
  } catch (reason) {
    error.value = reason.message || "暂时无法读取作业任务。";
  } finally {
    loading.value = false;
  }
}

function taskPath(item) {
  return taskEntryPath(item, { areaKey: areaKey.value });
}

function dueText(item) {
  if (!item.due_at) return "未设置截止时间";
  const text = new Date(item.due_at).toLocaleString("zh-CN", {
    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
  return `截止 ${text}`;
}

function attemptsText(item) {
  if (item.entry.kind === "lesson_scratch") return "不限提交次数";
  return item.attempts_left == null ? "不限作答次数" : `还可作答 ${item.attempts_left} 次`;
}

onMounted(load);
</script>

<template>
  <main class="kids-page student-task-page task-timeline">
    <header class="student-task-heading homework-heading">
      <div>
        <h1>我的作业</h1>
        <p>查看课程作业、提交反馈与截止信息。</p>
      </div>
      <img :src="heroImage" alt="正在记录作业的水獭" />
    </header>

    <p v-if="loading" class="student-task-message" aria-live="polite">正在加载作业...</p>
    <section v-else-if="error" class="student-task-message student-task-error" role="alert">
      <p>{{ error }}</p>
      <button class="button button-primary" type="button" @click="load">重新加载</button>
    </section>
    <template v-else>
      <div v-if="counts.overdue" class="task-alert">
        有 {{ counts.overdue }} 份作业过了截止时间，不能再交了
      </div>
      <div v-if="counts.graded" class="task-alert">
        {{ counts.graded }} 份作业老师批完了
      </div>

      <section v-if="mainlineTotal" class="task-timeline-main" aria-label="待处理作业">
        <section v-for="segment in segments" :key="segment.key" class="task-timeline-segment">
          <h2>{{ segment.title }}（{{ counts[segment.key] || 0 }}）</h2>
          <div v-if="segment.items.length" class="student-task-list">
            <RouterLink
              v-for="item in segment.items"
              :key="`${item.source_type}:${item.source_id}`"
              :to="taskPath(item)"
            >
              <div>
                <span class="task-phase">{{ item.phase_label }}</span>
                <h3>{{ item.scope.title }}</h3>
                <p>
                  {{ item.origin.course_title }} · {{ item.origin.section_title }} ·
                  {{ item.origin.lesson_title }}
                </p>
              </div>
              <div class="task-timeline-meta">
                <span>{{ dueText(item) }}</span>
                <span>{{ attemptsText(item) }}</span>
                <AppIcon name="arrow-right" :size="20" />
              </div>
            </RouterLink>
          </div>
        </section>
      </section>
      <section v-else-if="!historyTotal" class="honest-empty student-task-empty">
        <AppIcon name="book" :size="30" />
        <div>
          <h2>暂时没有作业</h2>
          <p>老师布置的课程作业会在这里集中展示。</p>
        </div>
      </section>

      <button
        v-if="historyTotal"
        class="button task-completed-toggle"
        type="button"
        @click="historyExpanded = !historyExpanded"
      >
        历史作业（{{ historyTotal }}）
      </button>
      <div v-if="historyExpanded" class="student-task-list">
        <RouterLink
          v-for="item in historyItems"
          :key="`${item.source_type}:${item.source_id}`"
          :to="taskPath(item)"
        >
          <div>
            <span class="task-phase">{{ item.phase_label }}</span>
            <h3>{{ item.scope.title }}</h3>
          </div>
          <AppIcon name="arrow-right" :size="20" />
        </RouterLink>
      </div>
    </template>
  </main>
</template>
