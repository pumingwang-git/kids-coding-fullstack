<script setup>
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { fetchExamTasks } from "../services/studentTasks";

const items = ref([]);
const loading = ref(true);
const error = ref("");
const heroImage = "/assets/otter-reading.png";
async function load() {
  loading.value = true;
  error.value = "";
  try { items.value = (await fetchExamTasks()).items || []; }
  catch (reason) { error.value = reason.message || "暂时无法读取考试安排。"; }
  finally { loading.value = false; }
}
function taskPath(item) { return `/exam/${encodeURIComponent(item.entry.token)}`; }
onMounted(load);
</script>

<template>
  <main class="kids-page student-task-page">
    <header class="student-task-heading exam-heading"><div><h1>我的考试</h1><p>已分配的考试会按当前安排展示在这里。</p></div><img :src="heroImage" alt="正在阅读考试说明的水獭" /></header>
    <p v-if="loading" class="student-task-message" aria-live="polite">正在加载考试...</p>
    <section v-else-if="error" class="student-task-message student-task-error" role="alert"><p>{{ error }}</p><button class="button button-primary" type="button" @click="load">重新加载</button></section>
    <section v-else-if="!items.length" class="honest-empty student-task-empty"><AppIcon name="exam" :size="30" /><div><h2>暂时没有考试安排</h2><p>考试被分配给你后，会显示在这里。</p></div></section>
    <section v-else class="student-task-list" aria-label="考试安排">
      <RouterLink v-for="item in items" :key="`${item.source_type}:${item.source_id}`" :to="taskPath(item)">
        <div><span class="task-phase">{{ item.phase_label }}</span><h2>{{ item.scope.title }}</h2><p>{{ item.open_at ? `开始 ${new Date(item.open_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : "随时可进入" }}</p></div>
        <span class="task-due">{{ item.duration_minutes ? `${item.duration_minutes} 分钟` : "不限时" }}</span><AppIcon name="arrow-right" :size="20" />
      </RouterLink>
    </section>
  </main>
</template>
