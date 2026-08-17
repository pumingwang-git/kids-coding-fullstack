<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { request } from "../services/auth";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const days = ref(30);
const data = ref(null);
const loading = ref(true);
const error = ref("");
const maxMastery = computed(() => Math.max(1, ...(data.value?.mastery_breakdown || []).map((item) => item.count)));
const maxSource = computed(() => Math.max(1, ...(data.value?.source_breakdown || []).map((item) => item.count)));

async function load() {
  loading.value = true;
  error.value = "";
  try { data.value = await request(`/api/student/mistakes/stats?days=${days.value}`); }
  catch (reason) { error.value = reason.message || "统计暂时无法加载。"; }
  finally { loading.value = false; }
}
watch(days, load);
onMounted(load);
</script>

<template>
  <main class="kids-page stats-page">
    <RouterLink class="back-link" :to="`/areas/${areaKey}/tasks/mistakes`"><AppIcon name="arrow-left" :size="18" /> 返回我的错题</RouterLink>
    <header class="stats-heading"><div><h1>复习统计</h1><p>从真实错题档案和重做记录中汇总，帮助你找到下一步要加强的地方。</p></div><label><span>统计范围</span><select v-model.number="days"><option :value="7">近 7 天</option><option :value="30">近 30 天</option><option :value="90">近 90 天</option></select></label></header>
    <p v-if="loading" class="stats-message">正在汇总复习记录...</p>
    <section v-else-if="error" class="stats-message stats-error" role="alert"><p>{{ error }}</p><button class="button button-primary" type="button" @click="load">重新加载</button></section>
    <template v-else-if="data">
      <section class="stats-kpis" aria-label="复习概览"><div><strong>{{ data.summary.total }}</strong><span>累计错题</span></div><div><strong>{{ data.summary.due }}</strong><span>当前待复习</span></div><div><strong>{{ data.review_count }}</strong><span>近 {{ data.days }} 天重做</span></div><div><strong>{{ data.review_accuracy == null ? "-" : `${data.review_accuracy}%` }}</strong><span>重做正确率</span></div></section>
      <div class="stats-grid">
        <section class="stats-panel"><h2>掌握度分布</h2><div class="bars"> <div v-for="item in data.mastery_breakdown" :key="item.key" class="bar-row"><span>{{ item.label }}</span><div class="bar-track"><i :style="{ width: `${(item.count / maxMastery) * 100}%` }"></i></div><b>{{ item.count }}</b></div></div></section>
        <section class="stats-panel"><h2>错题来源</h2><div v-if="data.source_breakdown.length" class="bars"><div v-for="item in data.source_breakdown" :key="item.label" class="bar-row"><span>{{ item.label }}</span><div class="bar-track source"><i :style="{ width: `${(item.count / maxSource) * 100}%` }"></i></div><b>{{ item.count }}</b></div></div><p v-else class="panel-empty">还没有错题来源数据。</p></section>
      </div>
      <section class="stats-panel activity-panel"><h2>每日复习次数</h2><div v-if="data.daily_reviews.length" class="activity-list"><div v-for="item in data.daily_reviews" :key="item.date" class="activity-day"><span>{{ item.date.slice(5) }}</span><i :style="{ height: `${Math.max(8, item.count * 18)}px` }"></i><b>{{ item.count }}</b></div></div><p v-else class="panel-empty">这个时间段还没有重做记录，完成一次错题重做后会显示在这里。</p></section>
    </template>
  </main>
</template>

<style scoped>
.stats-page { max-width: 1060px; }
.back-link { display: inline-flex; align-items: center; gap: 5px; margin-bottom: 20px; color: var(--accent); font-weight: 800; }
.stats-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; padding: 30px 34px; border-radius: 24px 8px 24px 8px; background: var(--area-surface); color: #203c5b; }
.stats-heading h1 { margin: 0; font: 800 34px/1.2 var(--font-display); }
.stats-heading p { max-width: 620px; margin: 10px 0 0; color: #54708d; line-height: 1.7; }
.stats-heading label { display: grid; gap: 6px; flex: 0 0 auto; color: #54708d; font-size: 12px; font-weight: 800; }
select { min-height: 42px; min-width: 118px; padding: 8px 28px 8px 10px; border: 1px solid var(--line); border-radius: 4px; background: var(--kids-panel); color: var(--ink); }
.stats-kpis { display: grid; grid-template-columns: repeat(4, 1fr); margin-top: 20px; border: 1px solid var(--line); border-radius: 8px; background: var(--kids-panel); overflow: hidden; }
.stats-kpis div { padding: 19px 21px; border-right: 1px solid var(--line); }.stats-kpis div:last-child { border-right: 0; }.stats-kpis strong { display: block; color: var(--accent); font: 800 28px/1.1 var(--font-body); }.stats-kpis span { display: block; margin-top: 7px; color: var(--muted); font-size: 13px; }
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 20px; }.stats-panel { padding: 24px; border: 1px solid var(--line); border-radius: 8px; background: var(--kids-panel); }.stats-panel h2 { margin: 0 0 22px; font: 800 21px/1.25 var(--font-display); }.bars { display: grid; gap: 17px; }.bar-row { display: grid; grid-template-columns: 74px minmax(0, 1fr) 22px; align-items: center; gap: 10px; font-size: 13px; }.bar-row span { color: var(--muted); }.bar-row b { text-align: right; }.bar-track { height: 10px; overflow: hidden; border-radius: 999px; background: var(--mint); }.bar-track i { display: block; height: 100%; border-radius: inherit; background: var(--accent); }.bar-track.source i { background: var(--kids-coral); }.activity-panel { margin-top: 14px; }.activity-list { display: flex; align-items: end; gap: 14px; min-height: 132px; overflow-x: auto; padding-top: 12px; }.activity-day { display: grid; justify-items: center; gap: 6px; min-width: 34px; color: var(--muted); font-size: 11px; }.activity-day i { width: 20px; min-height: 8px; border-radius: 4px 4px 2px 2px; background: var(--kids-blue); }.activity-day b { color: var(--ink); font-size: 12px; }.panel-empty,.stats-message { color: var(--muted); line-height: 1.6; }.stats-message { display: grid; justify-items: center; gap: 10px; margin-top: 20px; padding: 34px; border: 1px solid var(--line); border-radius: 8px; background: var(--kids-panel); text-align: center; }.stats-message p { margin: 0; }.stats-error { color: var(--danger); }
@media (max-width: 760px) { .stats-heading { align-items: flex-start; flex-direction: column; padding: 26px 22px; }.stats-heading h1 { font-size: 30px; }.stats-kpis { grid-template-columns: repeat(2, 1fr); }.stats-kpis div:nth-child(2) { border-right: 0; }.stats-kpis div:nth-child(-n + 2) { border-bottom: 1px solid var(--line); }.stats-grid { grid-template-columns: 1fr; } }
@media (max-width: 420px) { .stats-kpis div { padding: 16px; }.stats-kpis strong { font-size: 24px; }.stats-panel { padding: 20px 16px; } }
</style>
