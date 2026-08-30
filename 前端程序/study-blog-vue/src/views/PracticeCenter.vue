<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { fetchPracticeQueue, fetchPracticeTasks } from "../services/studentTasks";
import { taskEntryPath } from "../services/taskEntry";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const queue = ref({ current: null, upcoming: [], counts: {} });
const completedItems = ref([]);
const completedExpanded = ref(false);
const completedLoaded = ref(false);
const loading = ref(true);
const error = ref("");

function taskPath(item) {
  return taskEntryPath(item, { areaKey: areaKey.value });
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    queue.value = await fetchPracticeQueue({ preview: 3 });
  } catch (reason) {
    error.value = reason.message || "暂时无法读取练习任务。";
  } finally {
    loading.value = false;
  }
}

async function toggleCompleted() {
  completedExpanded.value = !completedExpanded.value;
  if (!completedExpanded.value || completedLoaded.value) return;
  const result = await fetchPracticeTasks({ status: "done", page: 1 });
  completedItems.value = result.items || [];
  completedLoaded.value = true;
}

function swapCurrent() {
  if (!queue.value.upcoming.length) return;
  const next = queue.value.upcoming.shift();
  queue.value.upcoming.push(queue.value.current);
  queue.value.current = next;
}

onMounted(load);
</script>

<template>
  <main class="kids-page student-task-page task-queue">
    <header class="student-task-heading">
      <h1>练一练</h1>
    </header>

    <p v-if="loading" class="student-task-message" aria-live="polite">正在加载练习...</p>
    <section v-else-if="error" class="student-task-message student-task-error" role="alert">
      <p>{{ error }}</p>
      <button class="button button-primary" type="button" @click="load">重新加载</button>
    </section>
    <section v-else-if="!queue.current" class="honest-empty student-task-empty">
      <h2>暂时没有练习</h2>
      <p>继续学习课程后，这里会展示可以进入的练习。</p>
    </section>
    <template v-else>
      <section class="task-queue-current">
        <span class="task-phase">{{ queue.current.reason_label }}</span>
        <h2>{{ queue.current.scope.title }}</h2>
        <p>
          {{ queue.current.origin.course_title }} · {{ queue.current.origin.section_title }} ·
          {{ queue.current.origin.lesson_title }}
        </p>
        <div class="task-queue-actions">
          <RouterLink class="button button-primary" :to="taskPath(queue.current)">继续做</RouterLink>
          <button class="button" type="button" @click="swapCurrent">换一题</button>
        </div>
      </section>

      <section class="task-queue-upcoming" aria-labelledby="practice-upcoming-title">
        <h2 id="practice-upcoming-title">接下来</h2>
        <div class="student-task-list">
          <RouterLink
            v-for="item in queue.upcoming"
            :key="`${item.source_type}:${item.source_id}`"
            :to="taskPath(item)"
          >
            <span>{{ item.scope.title }}</span>
            <small>{{ item.reason_label }}</small>
          </RouterLink>
        </div>
      </section>

      <button class="button task-completed-toggle" type="button" @click="toggleCompleted">
        练过的题（{{ queue.counts.done || 0 }}）
      </button>
      <div v-if="completedExpanded" class="student-task-list">
        <RouterLink
          v-for="item in completedItems"
          :key="`${item.source_type}:${item.source_id}`"
          :to="taskPath(item)"
        >
          {{ item.scope.title }}
        </RouterLink>
      </div>
    </template>
  </main>
</template>
