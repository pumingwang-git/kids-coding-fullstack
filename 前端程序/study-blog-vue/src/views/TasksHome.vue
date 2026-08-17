<script setup>
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));

const taskTypes = computed(() => [
  {
    key: "practice",
    to: `/areas/${areaKey.value}/tasks/practice`,
    icon: "check",
    title: "练一练",
    description: "把刚学会的知识马上用起来，做完就能看到反馈。",
    state: "从课时进入",
    stateTone: "ready",
    action: "查看练习入口",
  },
  {
    key: "homework",
    to: `/areas/${areaKey.value}/tasks/homework`,
    icon: "book",
    title: "我的作业",
    description: "集中查看老师布置的作业、截止时间和提交结果。",
    state: "列表接入中",
    stateTone: "soon",
    action: "查看作业说明",
  },
  {
    key: "exams",
    to: `/areas/${areaKey.value}/tasks/exams`,
    icon: "exam",
    title: "我的考试",
    description: "查看可参加的考试；已有考试链接时可以直接开始作答。",
    state: "链接作答已开放",
    stateTone: "ready",
    action: "查看考试说明",
  },
]);
</script>

<template>
  <main class="kids-page tasks-overview-page">
    <header class="tasks-overview-hero">
      <div class="tasks-overview-copy">
        <h1>把今天的学习收一收</h1>
        <p>练习、作业和考试各有自己的节奏，从这里找到下一步。</p>
        <div class="tasks-overview-actions">
          <RouterLink class="primary-action" :to="`/areas/${areaKey}/courses`">
            <AppIcon name="book" :size="18" /> 回到我的课程
          </RouterLink>
          <RouterLink class="secondary-action" :to="`/areas/${areaKey}/tasks/mistakes`">
            <AppIcon name="exam" :size="18" /> 查看错题本
          </RouterLink>
        </div>
      </div>
      <img src="/assets/otter-writing.png" alt="水獭正在整理学习任务" />
    </header>

    <section class="tasks-overview-note" aria-label="任务状态说明">
      <AppIcon name="info" :size="20" />
      <p>练习和作业通常从课程课时进入；考试列表正在接入统一的任务分发，现有考试链接仍可正常作答。</p>
    </section>

    <section class="task-type-list" aria-label="学习任务类型">
      <RouterLink v-for="task in taskTypes" :key="task.key" class="task-type-row" :to="task.to">
        <span class="task-type-icon" :class="`tone-${task.key}`"><AppIcon :name="task.icon" :size="22" /></span>
        <span class="task-type-content">
          <span class="task-type-title-line">
            <strong>{{ task.title }}</strong>
            <span class="task-status" :class="`status-${task.stateTone}`">{{ task.state }}</span>
          </span>
          <span class="task-type-description">{{ task.description }}</span>
          <span class="task-type-action">{{ task.action }} <AppIcon name="arrow-right" :size="16" /></span>
        </span>
        <AppIcon class="task-type-arrow" name="arrow-right" :size="20" />
      </RouterLink>
    </section>
  </main>
</template>

<style scoped>
.tasks-overview-page { max-width: 1120px; }
.tasks-overview-hero {
  position: relative;
  min-height: 286px;
  overflow: hidden;
  display: flex;
  align-items: center;
  padding: 38px 46px;
  border-radius: 30px 9px 30px 9px;
  background: var(--kids-sky);
  color: #203c5b;
}
.tasks-overview-copy { position: relative; z-index: 1; max-width: 680px; }
.tasks-overview-copy h1 {
  margin: 0;
  font: 900 clamp(32px, 4.3vw, 52px) / 1.18 var(--font-display);
  letter-spacing: -0.035em;
}
.tasks-overview-copy p { max-width: 46ch; margin: 16px 0 0; color: #54708d; font-size: 16px; line-height: 1.75; }
.tasks-overview-hero img { position: absolute; right: 5%; bottom: -38px; width: 250px; height: 260px; object-fit: contain; }
.tasks-overview-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
.tasks-overview-actions :deep(.primary-action),
.tasks-overview-actions :deep(.secondary-action) { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; }
.tasks-overview-actions :deep(.primary-action) { background: var(--kids-blue); border-color: var(--kids-blue); }
.tasks-overview-actions :deep(.secondary-action) { border-color: rgba(32, 60, 91, 0.2); color: #365879; }
.tasks-overview-note { display: flex; align-items: flex-start; gap: 10px; margin: 20px 0 16px; padding: 14px 16px; border: 1px solid rgba(77, 130, 194, 0.2); border-radius: 8px; background: color-mix(in srgb, var(--kids-sky) 42%, var(--kids-panel)); color: #54708d; }
.tasks-overview-note .app-icon { flex: 0 0 auto; margin-top: 2px; color: var(--kids-blue); }
.tasks-overview-note p { margin: 0; font-size: 13px; line-height: 1.7; }
.task-type-list { display: grid; gap: 12px; }
.task-type-row { display: grid; grid-template-columns: 52px minmax(0, 1fr) 20px; align-items: center; gap: 18px; min-height: 118px; padding: 20px 24px; border: 1px solid rgba(55, 87, 123, 0.13); border-radius: 18px 7px 18px 7px; background: var(--kids-panel); color: inherit; transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease; }
.task-type-row:hover { border-color: rgba(77, 130, 194, 0.42); box-shadow: 0 10px 24px rgba(55, 87, 123, 0.08); transform: translateX(3px); }
.task-type-row:focus-visible { outline: 3px solid color-mix(in srgb, var(--accent) 70%, white); outline-offset: 3px; }
.task-type-icon { display: grid; width: 52px; height: 52px; place-items: center; border-radius: 15px; }
.tone-practice { background: rgba(47, 128, 110, 0.12); color: var(--accent); }
.tone-homework { background: rgba(239, 107, 74, 0.12); color: var(--kids-coral); }
.tone-exams { background: rgba(77, 130, 194, 0.12); color: var(--kids-blue); }
.task-type-content { min-width: 0; display: grid; gap: 5px; }
.task-type-title-line { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; }
.task-type-title-line strong { font-size: 20px; line-height: 1.35; }
.task-status { display: inline-flex; align-items: center; min-height: 24px; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 900; }
.status-ready { background: var(--mint); color: var(--accent); }
.status-soon { background: color-mix(in srgb, var(--kids-sun) 25%, transparent); color: #8c671e; }
.task-type-description { color: #687b8e; font-size: 13px; line-height: 1.65; }
.task-type-action { display: inline-flex; align-items: center; gap: 4px; margin-top: 4px; color: var(--kids-blue); font-size: 12px; font-weight: 900; }
.task-type-arrow { color: #8292a3; }
@media (max-width: 800px) {
  .tasks-overview-hero { min-height: 286px; align-items: flex-start; padding: 28px 24px; }
  .tasks-overview-hero img { right: -28px; bottom: -30px; width: 190px; height: 200px; opacity: 0.34; }
  .tasks-overview-copy p { max-width: 34ch; font-size: 15px; }
  .task-type-row { grid-template-columns: 44px minmax(0, 1fr) 18px; gap: 13px; padding: 18px 16px; }
  .task-type-icon { width: 44px; height: 44px; border-radius: 13px; }
  .task-type-title-line strong { font-size: 18px; }
}
@media (max-width: 480px) {
  .tasks-overview-actions { display: grid; }
  .tasks-overview-actions :deep(.primary-action), .tasks-overview-actions :deep(.secondary-action) { justify-content: center; }
  .task-type-description { font-size: 12px; }
  .task-type-action { display: none; }
}
@media (prefers-reduced-motion: reduce) { .task-type-row { transition: none; } }
</style>
