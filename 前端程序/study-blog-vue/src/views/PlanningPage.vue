<script setup>
import { RouterLink } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
defineProps({
  title: { type: String, required: true },
  description: { type: String, required: true },
  parent: { type: String, required: true },
  areaKey: { type: String, default: "kids" },
});
</script>
<template>
  <main class="kids-page planning-page">
    <div class="planning-copy">
      <span class="status-planning">正在规划</span>
      <h1>{{ title }}</h1>
      <p>{{ description }}</p>
      <p class="planning-note">
        功能会在具备真实列表、详情、权限和异常状态后开放。在此之前，这里不会生成假数据。
      </p>
      <RouterLink class="primary-action" :to="`/areas/${areaKey}/${parent}`"
        ><AppIcon name="arrow-left" /> 返回{{
          parent === "tasks" ? "学习任务" : "探索创作"
        }}</RouterLink
      >
    </div>
    <img src="/assets/otter-thinking-720.webp" alt="水獭正在规划功能" />
  </main>
</template>
