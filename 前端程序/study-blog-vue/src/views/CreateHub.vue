<script setup>
// 创作入口页：图形化编程 / 代码编程 双入口 + 我的作品快捷展示
// 参考共创世界创作中心布局，顶部 Tab 切换，主体展示作品列表
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { request } from "../services/auth";
import AppIcon from "../components/AppIcon.vue";

const route = useRoute();
const router = useRouter();
const areaKey = computed(() => String(route.params.areaKey || "kids"));

// 当前选中的创作类型: 'scratch' | 'code'
const activeTab = ref("scratch");

const items = ref([]);
const loading = ref(true);
const creating = ref(false);
const createError = ref("");

const studioEdit = (id) =>
  window.open(`/scratch-studio/?mode=free&work_id=${id}`, "_blank");
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
  try {
    const data = await request("/api/scratch/works");
    items.value = data.items || [];
  } catch {
    items.value = [];
  } finally {
    loading.value = false;
  }
}

async function createWork() {
  if (activeTab.value === "code") {
    // 代码编程模式：跳转或提示（当前仅占位）
    alert("代码编程工作台正在开发中，请先用图形化编程创作！");
    return;
  }
  creating.value = true;
  createError.value = "";
  try {
    // 首次保存前不创建后端记录，避免未开始创作的空作品进入列表。
    window.open("/scratch-studio/?mode=free&draft=1", "_blank");
  } catch (e) {
    createError.value = e.message || "创建失败，请检查网络后重试。";
  } finally {
    creating.value = false;
  }
}

function goToProjects() {
  router.push(`/areas/${areaKey.value}/explore/projects`);
}

function goToExplore() {
  router.push(`/areas/${areaKey.value}/explore`);
}

onMounted(load);
</script>

<template>
  <main class="kids-page create-hub-page">
    <!-- 顶部创作导航栏 -->
    <header class="create-hub-header">
      <div class="create-hub-tabs" role="tablist">
        <button
          :class="{ active: activeTab === 'scratch' }"
          role="tab"
          @click="activeTab = 'scratch'"
        >
          <AppIcon name="spark" /> 图形化编程
        </button>
        <button
          :class="{ active: activeTab === 'code' }"
          role="tab"
          @click="activeTab = 'code'"
        >
          <AppIcon name="code" /> 代码编程
        </button>
      </div>
      <div class="create-hub-actions">
        <button class="primary-action" :disabled="creating" @click="createWork">
          <AppIcon name="plus" /> 新建项目
        </button>
        <p v-if="createError" class="create-error">{{ createError }}</p>
      </div>
    </header>

    <!-- 图形化编程内容区 -->
    <section v-if="activeTab === 'scratch'" class="create-hub-body">
      <div class="create-hub-toolbar">
        <h2>我的作品</h2>
        <div class="create-hub-links">
          <button class="text-button" @click="goToExplore">去作品广场 <AppIcon name="arrow-right" /></button>
          <button class="text-button" @click="goToProjects">管理全部作品 <AppIcon name="arrow-right" /></button>
        </div>
      </div>

      <section v-if="loading" class="honest-empty compact-empty">
        <div><h3>正在加载作品…</h3></div>
      </section>

      <section v-else-if="items.length === 0" class="honest-empty compact-empty">
        <AppIcon name="spark" />
        <div>
          <h3>还没有作品</h3>
          <p>点击「新建项目」开始你的第一个 Scratch 创作吧！</p>
          <button class="primary-action" @click="createWork">立即创作</button>
        </div>
      </section>

      <section v-else class="works-grid">
        <article
          v-for="work in items.slice(0, 6)"
          :key="work.id"
          class="work-card gallery-card"
          @click="studioPreview(work.id)"
        >
          <div class="work-cover">
            <img
              v-if="work.thumbnail_url"
              :src="work.thumbnail_url"
              :alt="work.title"
              loading="lazy"
            />
            <div v-else class="work-cover-placeholder">
              <svg viewBox="0 0 240 180" xmlns="http://www.w3.org/2000/svg">
                <rect width="240" height="180" fill="#f0f4f8" />
                <rect x="20" y="60" width="200" height="100" rx="4" fill="#e1e8ed" />
                <circle cx="60" cy="100" r="22" fill="#4d82c2" opacity="0.85" />
                <rect x="100" y="85" width="100" height="8" rx="2" fill="#b0c4de" />
                <rect x="100" y="100" width="80" height="8" rx="2" fill="#b0c4de" />
                <rect x="100" y="115" width="60" height="8" rx="2" fill="#b0c4de" />
                <rect x="20" y="20" width="50" height="14" rx="2" fill="#dcecff" />
                <rect x="170" y="20" width="50" height="14" rx="2" fill="#dcecff" />
              </svg>
            </div>
            <span class="work-cover-badge" :class="work.is_public ? 'badge-public' : 'badge-private'">
              {{ work.is_public ? "公开" : "私密" }}
            </span>
          </div>
          <div class="work-card-body">
            <h3>{{ work.title }}</h3>
            <div class="work-card-meta">
              <span>{{ work.source === "challenge" ? "来自闯关" : "自由创作" }}</span>
              <span>角色 {{ work.sprite_count }}</span>
              <span>{{ formatTime(work.updated_at) }}</span>
            </div>
            <div class="work-card-foot">
              <button
                class="work-action primary-action"
                @click.stop="studioEdit(work.id)"
              >
                去迭代
              </button>
            </div>
          </div>
        </article>
      </section>

      <div v-if="items.length > 6" class="create-hub-more">
        <button class="ghost-action" @click="goToProjects">查看全部 {{ items.length }} 个作品</button>
      </div>
    </section>

    <!-- 代码编程占位区 -->
    <section v-else class="create-hub-body create-hub-placeholder">
      <div class="honest-empty">
        <AppIcon name="code" />
        <div>
          <h3>代码编程工作台</h3>
          <p>Python / JavaScript 代码编程环境正在开发中，敬请期待。</p>
          <p>你可以先切换到「图形化编程」用 Scratch 积木进行创作！</p>
          <button class="primary-action" @click="activeTab = 'scratch'">切换到图形化编程</button>
        </div>
      </div>
    </section>
  </main>
</template>
