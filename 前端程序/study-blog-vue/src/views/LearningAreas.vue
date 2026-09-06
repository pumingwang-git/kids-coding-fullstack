<script setup>
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { request } from "../services/auth";

const areas = ref([]);
const loading = ref(true);
const error = ref("");
onMounted(async () => {
  try {
    areas.value = (await request("/api/learning-areas")).items || [];
  } catch (err) {
    error.value = err?.message || "专区目录加载失败。";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <main class="portal-page portal-section">
    <header class="page-intro">
      <p>学习专区</p>
      <h1>不同方向，使用适合它的学习方式</h1>
      <p>
        专区决定学习场景，课程类型决定组织方式，学科标签只负责筛选内容。三者不会混在同一个分类里。
      </p>
    </header>
    <section class="area-directory">
      <p v-if="loading" class="portal-state">正在加载专区目录…</p>
      <div v-else-if="error" class="honest-empty">
        <p>{{ error }}</p>
      </div>
      <article
        v-for="area in areas"
        :key="area.key"
        :class="{ 'directory-live': area.status === 'active' }"
      >
        <div>
          <span :class="area.status === 'active' ? 'status-live' : 'status-planning'">{{
            area.status === "active" ? "已开放" : "规划中"
          }}</span>
          <h2>{{ area.name }}</h2>
          <p>{{ area.description }}</p>
          <RouterLink
            v-if="area.status === 'active'"
            class="primary-action"
            :to="`/learning/${area.key}`"
            >查看专区 <AppIcon name="arrow-right"
          /></RouterLink>
          <p v-else class="area-planning-note">专区内容正在准备中。</p>
        </div>
        <img
          v-if="area.status === 'active'"
          :src="
            area.theme_key === 'kids'
              ? '/assets/otter-coding-720.webp'
              : '/assets/otter-thinking-720.webp'
          "
          :alt="`${area.name}学习场景`"
          loading="lazy"
          decoding="async"
        />
      </article>
      <article class="directory-resource">
        <span class="status-planning">规划中</span>
        <h2>资源中心</h2>
        <p>用于查阅资料、速查表和参考内容，不计入课程进度，也不伪装为单课时。</p>
      </article>
    </section>
  </main>
</template>
