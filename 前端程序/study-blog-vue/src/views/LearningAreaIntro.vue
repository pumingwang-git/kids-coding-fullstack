<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { request } from "../services/auth";
import { session } from "../stores/session";

const route = useRoute();
const area = ref(null);
const taxonomy = ref([]);
const loading = ref(true);
const error = ref("");
const areaKey = computed(() => String(route.params.areaKey || ""));
const entry = computed(() => session.user ? `/areas/${areaKey.value}` : `/auth?next=${encodeURIComponent(`/areas/${areaKey.value}`)}`);

async function load() {
  loading.value = true; error.value = "";
  try {
    const [areaData, tree] = await Promise.all([
      request(`/api/learning-areas/${areaKey.value}`),
      request(`/api/course-taxonomy?area_key=${encodeURIComponent(areaKey.value)}`),
    ]);
    area.value = areaData; taxonomy.value = tree.items || [];
  } catch (err) { error.value = err?.message || "专区介绍加载失败。"; }
  finally { loading.value = false; }
}
onMounted(load);
watch(areaKey, load);
</script>

<template>
  <main class="portal-page area-intro-page" :data-area-theme="area?.theme_key || 'default'">
    <p v-if="loading" class="portal-state">正在加载学习专区…</p>
    <section v-else-if="error" class="honest-empty"><div><h1>暂时无法打开专区</h1><p>{{ error }}</p><RouterLink to="/learning">返回学习专区</RouterLink></div></section>
    <template v-else-if="area">
      <header class="area-intro-hero">
        <div>
          <span :class="area.status === 'active' ? 'status-live' : 'status-planning'">{{ area.status === "active" ? "已开放" : "规划中" }}</span>
          <p>学习专区</p><h1>{{ area.name }}</h1><p>{{ area.description }}</p>
          <dl><div><dt>适合谁</dt><dd>{{ area.audience || "正在完善" }}</dd></div><div><dt>学习方式</dt><dd>{{ area.modules.map((item) => item.label).join("、") }}</dd></div></dl>
          <RouterLink class="primary-action" :to="entry">{{ area.status === "active" ? "进入学习空间" : "查看规划工作台" }} <AppIcon name="arrow-right" /></RouterLink>
        </div>
        <img :src="area.theme_key === 'programmer' ? '/assets/otter-thinking-720.webp' : '/assets/otter-coding-720.webp'" :alt="`${area.name}学习场景`" width="720" height="720" />
      </header>
      <section class="area-direction-section">
        <header><p>方向与主题</p><h2>先看方向，再选择想深入的主题</h2><span>这些分类来自后台目录，可以继续调整和扩展。</span></header>
        <div class="direction-grid">
          <article v-for="(direction, index) in taxonomy" :key="direction.id">
            <span>{{ String(index + 1).padStart(2, "0") }}</span><h3>{{ direction.name }}</h3>
            <p v-if="direction.description">{{ direction.description }}</p>
            <ul><li v-for="topic in direction.children" :key="topic.id">{{ topic.name }}</li></ul>
          </article>
        </div>
      </section>
    </template>
  </main>
</template>
