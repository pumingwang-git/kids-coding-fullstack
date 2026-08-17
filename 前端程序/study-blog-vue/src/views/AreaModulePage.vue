<script setup>
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { areaByKey, modulePath } from "../stores/learningCatalog";
import { areaNavigationModules } from "../stores/studentNavigation";

const route = useRoute();
const area = computed(() => areaByKey(String(route.params.areaKey)));
const module = computed(() =>
  area.value?.modules.find((item) => item.module_key === route.params.moduleKey),
);
const isMore = computed(() => route.params.moduleKey === "more");
const moreModules = computed(() => areaNavigationModules(area.value).slice(3));
</script>
<template>
  <main v-if="area && isMore" class="kids-page hub-page">
    <header class="kids-page-heading">
      <div>
        <p>{{ area.name }}</p>
        <h1>更多功能</h1>
        <span>手机底栏优先保留前三项，其余入口集中在这里。</span>
      </div>
    </header>
    <section class="hub-list">
      <RouterLink
        v-for="item in moreModules"
        :key="item.module_key"
        :to="modulePath(area.key, item.module_key)"
        ><AppIcon name="spark" />
        <div>
          <span>{{ item.status === "available" ? "已开放" : "规划中" }}</span>
          <h2>{{ item.label }}</h2>
          <p>进入{{ area.name }}的“{{ item.label }}”模块。</p>
        </div>
        <AppIcon name="arrow-right"
      /></RouterLink>
    </section>
  </main>
  <main v-else-if="area && module" class="kids-page planning-page">
    <div class="planning-copy">
      <span :class="module.status === 'available' ? 'status-live' : 'status-planning'">{{
        module.status === "available" ? "已开放" : "正在规划"
      }}</span>
      <h1>{{ module.label }}</h1>
      <p>这是{{ area.name }}工作台中的“{{ module.label }}”模块。</p>
      <p class="planning-note">
        功能会在具备真实列表、详情、权限和异常状态后开放。在此之前，这里不会生成假数据。
      </p>
      <RouterLink class="primary-action" :to="modulePath(area.key, 'overview')"
        ><AppIcon name="arrow-left" /> 返回{{ area.name }}</RouterLink
      >
    </div>
    <img src="/assets/otter-thinking-720.webp" alt="水獭正在规划功能" />
  </main>
  <main v-else class="kids-page planning-page">
    <div class="planning-copy">
      <h1>这个入口尚未配置</h1>
      <p>请返回专区首页，或联系管理员检查工作台能力配置。</p>
      <RouterLink class="primary-action" :to="`/areas/${route.params.areaKey}`"
        ><AppIcon name="arrow-left" /> 返回专区</RouterLink
      >
    </div>
  </main>
</template>
