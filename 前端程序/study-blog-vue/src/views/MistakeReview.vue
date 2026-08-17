<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { request } from "../services/auth";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const items = ref([]);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const body = await request("/api/student/mistakes/review-tasks?limit=50");
    items.value = body.items || [];
  } catch (reason) {
    error.value = reason.message || "复习任务暂时无法加载。";
  } finally {
    loading.value = false;
  }
}

function dateLabel(value) {
  return value ? new Date(value).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" }) : "今天";
}

onMounted(load);
</script>

<template>
  <main class="kids-page review-page">
    <RouterLink class="back-link" :to="`/areas/${areaKey}/tasks/mistakes`"><AppIcon name="arrow-left" :size="18" /> 返回我的错题</RouterLink>
    <header class="review-hero">
      <div>
        <h1>今日复习任务</h1>
        <p>按系统建议的复习时间排序。完成一题后，掌握度和下一次复习时间会自动更新。</p>
      </div>
      <span class="task-count">{{ items.length }} 题</span>
    </header>
    <p v-if="loading" class="review-message">正在准备今天的任务...</p>
    <section v-else-if="error" class="review-message review-error" role="alert">
      <p>{{ error }}</p><button class="button button-primary" type="button" @click="load">重新加载</button>
    </section>
    <section v-else-if="!items.length" class="review-message review-empty">
      <AppIcon name="check" :size="32" /><h2>今天没有到期任务</h2><p>继续完成练习，新的错题会在建议时间进入复习任务。</p>
      <RouterLink class="secondary-action" :to="`/areas/${areaKey}/tasks/mistakes`">查看错题本</RouterLink>
    </section>
    <section v-else class="task-list" aria-label="今日复习任务">
      <RouterLink v-for="(item, index) in items" :key="item.id" class="task-row" :to="`/areas/${areaKey}/tasks/mistakes/${item.id}`">
        <span class="task-index">{{ String(index + 1).padStart(2, "0") }}</span>
        <span class="task-copy"><strong>{{ item.title }}</strong><small>{{ item.source_label }} · 答错 {{ item.wrong_count }} 次 · {{ dateLabel(item.next_review_at) }}到期</small></span>
        <AppIcon name="arrow-right" :size="18" />
      </RouterLink>
    </section>
  </main>
</template>

<style scoped>
.review-page { max-width: 920px; }
.back-link { display: inline-flex; align-items: center; gap: 5px; margin-bottom: 20px; color: var(--accent); font-weight: 800; }
.review-hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 30px 34px; border-radius: 24px 8px 24px 8px; background: var(--area-surface); color: #203c5b; }
.review-hero h1 { margin: 0; font: 800 34px/1.2 var(--font-display); }
.review-hero p { max-width: 620px; margin: 10px 0 0; color: #54708d; line-height: 1.7; }
.task-count { flex: 0 0 auto; padding: 12px 16px; border-radius: 999px; background: var(--kids-panel); color: var(--accent); font-weight: 900; }
.task-list { display: grid; gap: 10px; margin-top: 20px; }
.task-row { display: grid; grid-template-columns: 42px minmax(0, 1fr) 20px; align-items: center; gap: 14px; padding: 17px 18px; border: 1px solid var(--line); border-radius: 8px; background: var(--kids-panel); color: inherit; }
.task-row:hover { border-color: var(--accent); box-shadow: var(--card-shadow); }
.task-index { color: var(--kids-coral); font: 800 14px/1 var(--font-mono); }
.task-copy { display: grid; gap: 6px; min-width: 0; }
.task-copy strong { overflow-wrap: anywhere; font-size: 16px; }
.task-copy small { color: var(--muted); font-size: 12px; }
.review-message { display: grid; justify-items: center; gap: 10px; margin-top: 20px; padding: 34px; border: 1px solid var(--line); border-radius: 8px; background: var(--kids-panel); color: var(--muted); text-align: center; }
.review-message p { margin: 0; line-height: 1.6; }
.review-message h2 { margin: 0; color: var(--ink); font-size: 21px; }
.review-error { color: var(--danger); }
.review-empty .app-icon { color: var(--accent); }
.secondary-action { display: inline-flex; align-items: center; min-height: 42px; padding: 8px 15px; border: 1px solid var(--line); border-radius: 4px; color: var(--ink); font-weight: 800; }
@media (max-width: 600px) { .review-hero { align-items: flex-start; flex-direction: column; padding: 26px 22px; } .review-hero h1 { font-size: 30px; } .task-row { grid-template-columns: 30px minmax(0, 1fr) 18px; padding: 15px; } }
</style>
