<script setup>
// 探索创作 → 作品广场：浏览所有学生公开的 Scratch 作品。
// - 搜索（标题包含）、排序（最新 / 最热）、分页
// - 卡片点击 → 打开 Studio 只读预览（?mode=preview&work_id=N）
// - 「去创作」直接新建作品并打开工作台；「我的作品」进入管理页
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { request } from "../services/auth";
import AppIcon from "../components/AppIcon.vue";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));

const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = 12;
const sort = ref("latest");
const keyword = ref("");
const loading = ref(true);
const errorMsg = ref("");
const creating = ref(false);
const createError = ref("");

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

const studioPreview = (id) =>
  window.open(`/scratch-studio/?mode=preview&work_id=${id}`, "_blank");

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 60 * 1000) return "刚刚";
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)} 分钟前`;
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / 3600000)} 小时前`;
  if (diff < 7 * 24 * 60 * 60 * 1000) return `${Math.floor(diff / 86400000)} 天前`;
  return d.toLocaleDateString("zh-CN");
}

async function load() {
  loading.value = true;
  errorMsg.value = "";
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      size: String(pageSize),
      sort: sort.value,
    });
    if (keyword.value.trim()) params.set("keyword", keyword.value.trim());
    const data = await request(`/api/scratch/gallery?${params.toString()}`);
    items.value = data.items || [];
    total.value = data.total || 0;
  } catch (e) {
    errorMsg.value = e.message || "加载失败，请稍后再试。";
  } finally {
    loading.value = false;
  }
}

function changeSort(next) {
  if (sort.value === next) return;
  sort.value = next;
  page.value = 1;
  load();
}

function search() {
  page.value = 1;
  load();
}

function goPage(next) {
  if (next < 1 || next > totalPages.value) return;
  page.value = next;
  load();
}

async function createWork() {
  creating.value = true;
  createError.value = "";
  try {
    // 先进入编辑器，第一次保存时才创建服务端作品，避免空作品污染作品列表。
    window.open("/scratch-studio/?mode=free&draft=1", "_blank");
  } catch (e) {
    createError.value = e.message || "创建失败，请检查网络后重试。";
  } finally {
    creating.value = false;
  }
}

onMounted(load);
</script>

<template>
  <main class="kids-page hub-page explore-page">
    <header class="kids-page-heading">
      <div>
        <p>探索创作</p>
        <h1>把学到的知识，变成自己的作品</h1>
        <span>这里展出同学们公开的 Scratch 作品。点开任何一张卡片，都可以运行看看效果。</span>
      </div>
      <img src="/assets/otter-coding-720.webp" alt="水獭正在创作" />
    </header>

    <div class="works-toolbar">
      <div class="works-toolbar-left">
        <button class="primary-action" :disabled="creating" @click="createWork">
          <AppIcon name="spark" /> 去创作
        </button>
        <p v-if="createError" class="create-error">{{ createError }}</p>
      </div>
      <RouterLink class="ghost-action" :to="`/areas/${areaKey}/explore/projects`">
        我的作品
      </RouterLink>
      <form class="works-search" @submit.prevent="search">
        <input
          v-model="keyword"
          type="search"
          placeholder="搜索作品标题…"
          maxlength="60"
        />
        <button type="submit">搜索</button>
      </form>
      <div class="works-sort" role="tablist">
        <button
          :class="{ active: sort === 'latest' }"
          role="tab"
          @click="changeSort('latest')"
        >最新</button>
        <button
          :class="{ active: sort === 'popular' }"
          role="tab"
          @click="changeSort('popular')"
        >最热</button>
      </div>
    </div>

    <section v-if="loading" class="honest-empty compact-empty">
      <div><h3>正在加载作品…</h3></div>
    </section>

    <section v-else-if="errorMsg" class="honest-empty compact-empty">
      <div><h3>加载失败</h3><p>{{ errorMsg }}</p></div>
    </section>

    <section v-else-if="items.length === 0" class="honest-empty compact-empty">
      <AppIcon name="spark" />
      <div>
        <h3>{{ keyword ? "没有找到相关作品" : "还没有公开作品" }}</h3>
        <p>{{ keyword ? "换个关键词试试，或者清空搜索浏览全部作品。" : "快去创作你的第一个作品，让它出现在这里吧！" }}</p>
      </div>
    </section>

    <section v-else class="works-grid">
      <article
        v-for="work in items"
        :key="work.id"
        class="work-card gallery-card"
        @click="studioPreview(work.id)"
      >
        <!-- 作品封面。`thumbnail_url` 服务端保证不为空：有舞台截图发截图，
             没有（老作品 / 分享快照 / 截图失败）发生成占位图，前端不判空 -->
        <div class="work-cover">
          <img
            :src="work.thumbnail_url"
            :alt="work.title"
            loading="lazy"
          />
          <span v-if="work.is_public === false" class="work-cover-badge">私密</span>
        </div>
        <div class="work-card-body">
          <h3>{{ work.title }}</h3>
          <div class="work-card-meta">
            <span class="work-source">{{ work.author?.username || "同学" }}</span>
            <span>角色 {{ work.sprite_count }}</span>
            <span>{{ work.views }} 次浏览</span>
          </div>
          <div class="work-card-foot">
            <span>{{ formatTime(work.created_at) }}</span>
            <span class="work-preview-hint">点击预览 <AppIcon name="arrow-right" /></span>
          </div>
        </div>
      </article>
    </section>

    <nav v-if="totalPages > 1" class="works-pager">
      <button class="work-action" :disabled="page <= 1" @click="goPage(page - 1)">
        上一页
      </button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button class="work-action" :disabled="page >= totalPages" @click="goPage(page + 1)">
        下一页
      </button>
    </nav>
  </main>
</template>
