<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { fetchTaskOverview } from "../services/studentTasks";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const overview = ref(null);
const loading = ref(true);
const error = ref("");
const heroImage = "/assets/otter-writing.png";
const groups = computed(() => {
  if (!overview.value) return [];
  return [
    { key: "in_progress", title: "正在进行", icon: "play", items: overview.value.in_progress?.items || [] },
    { key: "due_soon", title: "即将截止", icon: "timer", items: overview.value.due_soon?.items || [] },
    { key: "to_review", title: "待查看结果", icon: "exam", items: overview.value.to_review?.items || [] },
    { key: "unfinished", title: "最近未完成", icon: "refresh", items: overview.value.unfinished?.items || [] },
    { key: "next_up", title: "推荐下一步", icon: "spark", items: overview.value.next_up?.items || [] },
  ].filter((group) => group.items.length);
});
async function load() {
  loading.value = true;
  error.value = "";
  try { overview.value = await fetchTaskOverview(); }
  catch (reason) { error.value = reason.message || "暂时无法整理学习任务。"; }
  finally { loading.value = false; }
}
function taskPath(item) {
  if (item.kind === "mistakes_review") return `/areas/${areaKey.value}/tasks/mistakes/review`;
  if (item.entry?.kind === "exam_link") return `/exam/${encodeURIComponent(item.entry.token)}`;
  if (item.entry?.kind === "lesson_homework") return `/learn/${item.entry.lesson_id}/homework/${item.entry.block_id}`;
  if (item.entry?.lesson_id) return `/learn/${item.entry.lesson_id}`;
  if (item.continue_lesson_id) return `/learn/${item.continue_lesson_id}`;
  return `/areas/${areaKey.value}/courses`;
}
function itemTitle(item) {
  if (item.kind === "mistakes_review") return `重练 ${item.total} 道错题`;
  return item.scope?.title || item.continue_lesson_title || item.lesson_title || item.course_title;
}
function itemDetail(item) {
  if (item.kind === "mistakes_review") return "回到错题本继续复习";
  return item.phase_label || item.course_title || "继续学习";
}
onMounted(load);
</script>

<template>
  <main class="kids-page tasks-dashboard-page">
    <header class="tasks-dashboard-heading"><div><h1>学习任务</h1><p>把眼前要做的事集中在这里，选一项继续就好。</p></div><img :src="heroImage" alt="正在整理学习任务的水獭" /></header>
    <p v-if="loading" class="student-task-message" aria-live="polite">正在加载任务...</p>
    <section v-else-if="error" class="student-task-message student-task-error" role="alert"><p>{{ error }}</p><button class="button button-primary" type="button" @click="load">重新加载</button></section>
    <section v-else-if="!groups.length" class="honest-empty tasks-dashboard-empty"><AppIcon name="spark" :size="32" /><div><h2>今天的任务已整理完</h2><p>继续浏览课程，新的练习、作业和考试安排会自动出现在这里。</p><RouterLink class="primary-action" :to="`/areas/${areaKey}/courses`">查看课程</RouterLink></div></section>
    <section v-else class="tasks-dashboard-groups" aria-label="学习任务分组">
      <section v-for="group in groups" :key="group.key" class="task-group">
        <header><span><AppIcon :name="group.icon" :size="18" />{{ group.title }}</span><RouterLink v-if="group.key === 'unfinished'" :to="`/areas/${areaKey}/tasks/practice`">查看全部</RouterLink></header>
        <RouterLink v-for="item in group.items" :key="item.scope?.key || item.kind || item.lesson_id" class="task-group-item" :to="taskPath(item)"><div><h2>{{ itemTitle(item) }}</h2><p>{{ itemDetail(item) }}</p></div><AppIcon name="arrow-right" :size="18" /></RouterLink>
      </section>
    </section>
  </main>
</template>
