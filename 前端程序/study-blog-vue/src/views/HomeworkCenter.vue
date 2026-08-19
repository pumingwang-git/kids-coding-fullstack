<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { fetchHomeworkTasks } from "../services/studentTasks";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const items = ref([]);
const loading = ref(true);
const error = ref("");
const heroImage = "/assets/otter-writing.png";

async function load() {
  loading.value = true;
  error.value = "";
  try { items.value = (await fetchHomeworkTasks()).items || []; }
  catch (reason) { error.value = reason.message || "暂时无法读取作业任务。"; }
  finally { loading.value = false; }
}

function taskPath(item) {
  return `/learn/${item.entry.lesson_id}/homework/${item.entry.block_id}`;
}

function dueText(item) {
  return item.due_at ? `截止 ${new Date(item.due_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : "未设置截止时间";
}

onMounted(load);
</script>

<template>
  <main class="kids-page student-task-page">
    <header class="student-task-heading homework-heading">
      <div><h1>我的作业</h1><p>查看课程作业、提交反馈与截止信息。</p></div>
      <img :src="heroImage" alt="正在记录作业的水獭" />
    </header>
    <p v-if="loading" class="student-task-message" aria-live="polite">正在加载作业...</p>
    <section v-else-if="error" class="student-task-message student-task-error" role="alert"><p>{{ error }}</p><button class="button button-primary" type="button" @click="load">重新加载</button></section>
    <section v-else-if="!items.length" class="honest-empty student-task-empty"><AppIcon name="book" :size="30" /><div><h2>暂时没有作业</h2><p>老师布置的课程作业会在这里集中展示。</p></div></section>
    <section v-else class="student-task-list" aria-label="作业任务">
      <RouterLink v-for="item in items" :key="`${item.source_type}:${item.source_id}`" :to="taskPath(item)">
        <div><span class="task-phase">{{ item.phase_label }}</span><h2>{{ item.scope.title }}</h2><p>{{ item.origin.course_title }} · {{ item.origin.lesson_title }}</p></div>
        <span class="task-due">{{ dueText(item) }}</span><AppIcon name="arrow-right" :size="20" />
      </RouterLink>
    </section>
  </main>
</template>
