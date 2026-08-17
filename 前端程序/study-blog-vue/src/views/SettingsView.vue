<script setup>
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";

const route = useRoute();
const securityTarget = computed(() => ({
  path: "/security",
  query: { area: String(route.query.area || route.meta.areaKey || "kids") },
}));
</script>

<template>
  <main class="kids-page settings-page">
    <header class="settings-heading">
      <div>
        <h1>设置</h1>
        <p>管理你的账号与安全选项。</p>
      </div>
      <AppIcon name="settings" :size="64" class="settings-hero" />
    </header>

    <section class="settings-list" aria-label="设置项">
      <RouterLink class="settings-item" :to="securityTarget">
        <span class="settings-item-icon"><AppIcon name="shield" :size="20" /></span>
        <span class="settings-item-main">
          <strong>账号与安全</strong>
          <small>修改密码、启用两步验证</small>
        </span>
        <AppIcon name="arrow-right" :size="20" class="settings-item-arrow" />
      </RouterLink>
    </section>

    <p class="settings-hint">更多学生端设置项会在有明确需求后逐步加入。</p>
  </main>
</template>

<style scoped>
.settings-page {
  max-width: 1060px;
}
.settings-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 32px clamp(28px, 5vw, 56px);
  border-radius: 24px 8px 24px 8px;
  background: var(--area-surface);
  color: #203c5b;
}
.settings-heading h1 {
  margin: 0;
  font: 900 36px/1.2 var(--font-display);
  letter-spacing: 0;
}
.settings-heading p {
  margin: 10px 0 0;
  color: #54708d;
  line-height: 1.7;
}
.settings-hero {
  color: color-mix(in srgb, var(--accent) 35%, transparent);
}
.settings-list {
  display: grid;
  gap: 10px;
  margin-top: 20px;
}
.settings-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 8px;
  background: var(--kids-panel);
  color: inherit;
}
.settings-item:hover {
  border-color: var(--kids-blue);
  box-shadow: 0 8px 18px rgba(34, 43, 40, 0.08);
}
.settings-item-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.settings-item-main {
  min-width: 0;
  flex: 1;
}
.settings-item-main strong {
  display: block;
  font-size: 16px;
}
.settings-item-main small {
  display: block;
  margin-top: 3px;
  color: var(--muted);
  font-size: 13px;
}
.settings-item-arrow {
  color: var(--muted);
}
.settings-hint {
  margin: 18px 2px 0;
  color: var(--muted);
  font-size: 13px;
}
</style>
