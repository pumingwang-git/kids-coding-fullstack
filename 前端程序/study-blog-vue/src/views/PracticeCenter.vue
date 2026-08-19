<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { fetchPracticeTasks } from "../services/studentTasks";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const items = ref([]);
const loading = ref(true);
const error = ref("");
const heroImage = "/assets/otter-thinking-720.webp";

async function load() {
  loading.value = true;
  error.value = "";
  try {
    items.value = (await fetchPracticeTasks()).items || [];
  } catch (reason) {
    error.value = reason.message || "暂时无法读取练习任务。";
  } finally {
    loading.value = false;
  }
}

function taskPath(item) {
  return `/learn/${item.entry.lesson_id}`;
}

onMounted(load);
</script>

<template>
  <main class="kids-page student-task-page">
    <header class="student-task-heading">
      <div><h1>练一练</h1><p>从已经解锁的课程内容中继续练习。</p></div>
      <img :src="heroImage" alt="正在思考的水獭" />
    </header>
    <p v-if="loading" class="student-task-message" aria-live="polite">正在加载练习...</p>
    <section v-else-if="error" class="student-task-message student-task-error" role="alert">
      <p>{{ error }}</p><button class="button button-primary" type="button" @click="load">重新加载</button>
    </section>
    <section v-else-if="!items.length" class="honest-empty student-task-empty">
      <AppIcon name="check" :size="30" /><div><h2>暂时没有练习</h2><p>继续学习课程后，这里会展示可以进入的练习。</p></div>
    </section>
    <section v-else class="student-task-list" aria-label="练习任务">
      <RouterLink v-for="item in items" :key="`${item.source_type}:${item.source_id}`" :to="taskPath(item)">
        <div><span class="task-phase">{{ item.phase_label }}</span><h2>{{ item.scope.title }}</h2><p>{{ item.origin.course_title }} · {{ item.origin.lesson_title }}</p></div>
        <span class="task-tries">已作答 {{ item.tries }} 次</span><AppIcon name="arrow-right" :size="20" />
      </RouterLink>
    </section>
  </main>
</template>
