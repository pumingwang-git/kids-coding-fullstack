<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { request } from "../services/auth";
import { areaByKey, modulePath } from "../stores/learningCatalog";
import { session } from "../stores/session";

const route = useRoute();
const area = computed(() => areaByKey(String(route.params.areaKey)));
const displayName = computed(() => session.user?.username || "同学");
const available = computed(() => area.value?.status === "active");

// —— 继续学习：后端聚合的最近学习记录（无数据 / 接口失败都退化为空态） ——
const continueItems = ref([]);
const continueLoading = ref(false);

onMounted(async () => {
  if (!available.value) return;
  continueLoading.value = true;
  try {
    const data = await request("/api/courses/continue-learning");
    continueItems.value = (data?.items || []).slice(0, 5);
  } catch {
    continueItems.value = []; // 首页不因聚合接口失败而报错，空态自会引导去选课程
  } finally {
    continueLoading.value = false;
  }
  try {
    const data = await request("/api/scratch/gallery?size=6&sort=latest");
    galleryWorks.value = (data?.items || []).slice(0, 6);
  } catch {
    galleryWorks.value = []; // 作品区加载失败不阻塞首页
  } finally {
    galleryLoaded.value = true;
  }
});

function formatLearnedAt(iso) {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const minutes = Math.floor((Date.now() - at.getTime()) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return at.toLocaleDateString("zh-CN");
}

function formatPosition(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const m = Math.floor(total / 60);
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

// —— 同学的作品：最新公开的 Scratch 作品（画廊接口，最多 6 个，加载失败静默降级） ——
const galleryWorks = ref([]);
const galleryLoaded = ref(false);

const studioPreview = (id) =>
  window.open(`/scratch-studio/?mode=preview&work_id=${id}`, "_blank");

function formatGalleryTime(iso) {
  if (!iso) return "—";
  const at = new Date(iso);
  const minutes = Math.floor((Date.now() - at.getTime()) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return at.toLocaleDateString("zh-CN");
}
</script>
<template>
  <main class="kids-page area-overview" v-if="area">
    <section class="kids-welcome">
      <div>
        <p>{{ displayName }}，欢迎来到{{ area.name }}</p>
        <h1>{{ available ? "今天想从哪里开始？" : "这个专区正在认真准备" }}</h1>
        <span>{{ area.description }}</span>
      </div>
      <img
        :src="available ? '/assets/otter-welcome.png' : '/assets/otter-thinking-720.webp'"
        :alt="`${area.name}欢迎场景`"
      />
    </section>
    <section class="continue-panel">
      <div class="panel-heading">
        <div>
          <h2>{{ available ? "继续学习" : "当前状态" }}</h2>
          <p>{{ available ? "回到最近一次学习的位置" : "规划内容会按真实开发进度开放" }}</p>
        </div>
      </div>

      <div v-if="!available" class="honest-empty compact-empty">
        <AppIcon name="spark" />
        <div>
          <h3>尚未开放真实课程</h3>
          <p>现在可以查看方向和工作台结构，不会展示虚构课程或项目。</p>
          <RouterLink class="primary-action" :to="`/learning/${area.key}`">查看方向介绍</RouterLink>
        </div>
      </div>

      <div v-else-if="continueLoading" class="honest-empty compact-empty">
        <AppIcon name="book" />
        <div>
          <h3>正在加载学习记录…</h3>
          <p>马上就好。</p>
        </div>
      </div>

      <div v-else-if="continueItems.length" class="continue-items">
        <div
          v-for="item in continueItems"
          :key="item.lesson_id"
          class="continue-card"
          :class="{ 'is-done': item.completed }"
        >
          <RouterLink
            v-if="item.completed || item.continue_lesson_id"
            class="cc-link"
            :to="`/learn/${item.completed ? item.lesson_id : item.continue_lesson_id}`"
          >
            <span v-if="item.cover_url" class="cc-cover"
              ><img :src="item.cover_url" :alt="item.course_title" loading="lazy" decoding="async"
            /></span>
            <span class="cc-main">
              <span class="cc-course"
                >{{ item.course_title
                }}<template v-if="item.section_title"> · {{ item.section_title }}</template></span
              >
              <b class="cc-title">{{ item.lesson_title }}</b>
              <span v-if="!item.completed && item.progress.total" class="cc-progress">
                <span class="cc-bar"
                  ><i :style="{ width: (item.progress.percent || 0) + '%' }"></i
                ></span>
                <em>{{ item.progress.percent }}%</em>
              </span>
              <span class="cc-meta">
                <template v-if="!item.completed && item.resume_position_seconds"
                  >上次看到 {{ formatPosition(item.resume_position_seconds) }}</template
                >
                <template v-else-if="!item.completed"
                  >已学习 {{ item.progress.done }}/{{ item.progress.total }} 个内容块</template
                >
                <template v-else-if="item.continue_lesson_id">本课时已完成，点击复习</template>
                <template v-else>整门课程已学完，点击复习</template>
                <em>{{ formatLearnedAt(item.last_learned_at) }}</em>
              </span>
            </span>
            <span v-if="item.completed" class="cc-done"><AppIcon name="check" />已完成</span>
            <span v-else class="cc-action"><AppIcon name="arrow-right" /></span>
          </RouterLink>
        </div>
      </div>

      <div v-else class="honest-empty compact-empty">
        <AppIcon name="book" />
        <div>
          <h3>还没有学习记录</h3>
          <p>选一门课程开始学习后，这里会显示你最近学到哪、方便一键继续。</p>
          <RouterLink class="primary-action" :to="modulePath(area.key, 'courses')"
            >去选课程</RouterLink
          >
        </div>
      </div>
    </section>
    <section class="quick-panel">
      <div class="panel-heading">
        <div>
          <h2>专区功能</h2>
          <p>由后台配置的真实入口</p>
        </div>
      </div>
      <nav class="quick-links">
        <RouterLink
          v-for="module in area.modules.filter((item) => item.module_key !== 'overview')"
          :key="module.module_key"
          :to="modulePath(area.key, module.module_key)"
          ><AppIcon
            :name="
              module.module_key === 'courses'
                ? 'book'
                : module.module_key === 'tasks'
                  ? 'check'
                  : 'spark'
            " /><span
            ><b>{{ module.label }}</b
            ><small>{{ module.status === "available" ? "可以进入" : "规划中" }}</small></span
          ><AppIcon name="arrow-right"
        /></RouterLink>
      </nav>
    </section>
    <section class="works-panel">
      <div class="panel-heading">
        <div>
          <h2>同学的作品</h2>
          <p>最新公开的 Scratch 创作，点开即可运行</p>
        </div>
        <RouterLink class="panel-more" :to="`/areas/${area.key}/explore`"
          >去探索创作 <AppIcon name="arrow-right"
        /></RouterLink>
      </div>
      <div v-if="!galleryLoaded" class="honest-empty compact-empty">
        <AppIcon name="spark" />
        <div><h3>正在加载作品…</h3></div>
      </div>
      <div v-else-if="galleryWorks.length === 0" class="honest-empty compact-empty">
        <AppIcon name="spark" />
        <div>
          <h3>还没有公开作品</h3>
          <p>同学创作并公开作品后，会展示在这里。</p>
          <RouterLink class="primary-action" :to="`/areas/${area.key}/explore/projects`"
            >去创作第一个作品</RouterLink
          >
        </div>
      </div>
      <div v-else class="home-works-grid">
        <button
          v-for="work in galleryWorks"
          :key="work.id"
          class="home-work-card"
          @click="studioPreview(work.id)"
        >
          <b>{{ work.title }}</b>
          <span>{{ work.author?.username || "同学" }} · {{ formatGalleryTime(work.created_at) }}</span>
        </button>
      </div>
    </section>
  </main>
</template>
