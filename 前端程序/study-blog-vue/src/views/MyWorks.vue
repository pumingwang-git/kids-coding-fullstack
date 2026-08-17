<script setup>
// 我的作品：学生自由创作的 Scratch 作品管理页。
// - 自由作品（source=free）与从挑战分享来的作品（source=challenge）统一列表
// - 操作：继续编辑（打开 Studio free 模式）、预览、公开/私密切换、重命名、删除、新建
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { request } from "../services/auth";
import AppIcon from "../components/AppIcon.vue";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));

const items = ref([]);
const loading = ref(true);
const errorMsg = ref("");
// 正在重命名的作品 id → 编辑框里的标题
const renamingId = ref(null);
const renameValue = ref("");
const busy = ref(false);
const notice = ref(""); // 操作结果提示（成功/失败），几秒后消失

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
  errorMsg.value = "";
  try {
    const data = await request("/api/scratch/works");
    items.value = data.items || [];
  } catch (e) {
    errorMsg.value = e.message || "加载失败，请稍后再试。";
  } finally {
    loading.value = false;
  }
}

async function createWork() {
  busy.value = true;
  try {
    const work = await request("/api/scratch/works", {
      method: "POST",
      body: JSON.stringify({ title: "未命名作品" }),
    });
    studioEdit(work.id);
    await load();
  } catch (e) {
    notice.value = e.message || "创建失败，请稍后再试。";
  } finally {
    busy.value = false;
  }
}

async function togglePublic(work) {
  busy.value = true;
  try {
    await request(`/api/scratch/works/${work.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_public: !work.is_public }),
    });
    notice.value = work.is_public
      ? `「${work.title}」已设为私密，不再在广场展出。`
      : `「${work.title}」已公开，同学们可以在广场看到它了！`;
    await load();
  } catch (e) {
    notice.value = e.message || "操作失败，请稍后再试。";
  } finally {
    busy.value = false;
  }
}

function startRename(work) {
  renamingId.value = work.id;
  renameValue.value = work.title;
}

async function confirmRename(work) {
  const title = renameValue.value.trim();
  if (!title) {
    renamingId.value = null;
    return;
  }
  busy.value = true;
  try {
    await request(`/api/scratch/works/${work.id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    notice.value = "已保存新标题。";
    renamingId.value = null;
    await load();
  } catch (e) {
    notice.value = e.message || "重命名失败，请稍后再试。";
  } finally {
    busy.value = false;
  }
}

async function removeWork(work) {
  if (!window.confirm(`确定删除「${work.title}」吗？删除后无法恢复。`)) return;
  busy.value = true;
  try {
    await request(`/api/scratch/works/${work.id}`, { method: "DELETE" });
    notice.value = `「${work.title}」已删除。`;
    await load();
  } catch (e) {
    notice.value = e.message || "删除失败，请稍后再试。";
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <main class="kids-page my-works-page">
    <header class="kids-page-heading">
      <div>
        <p>探索创作</p>
        <h1>我的作品</h1>
        <span>你创作和分享的 Scratch 作品都在这里。公开的作品会出现在广场上，展出给同学们。</span>
      </div>
      <img src="/assets/otter-coding-720.webp" alt="水獭正在创作" />
    </header>

    <div class="works-toolbar">
      <button class="primary-action" :disabled="busy" @click="createWork">
        <AppIcon name="spark" /> 新建作品
      </button>
      <RouterLink class="ghost-action" :to="`/areas/${areaKey}/explore`">
        <AppIcon name="arrow-left" /> 返回探索创作
      </RouterLink>
      <span v-if="notice" class="works-notice">{{ notice }}</span>
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
        <h3>还没有作品</h3>
        <p>点击「新建作品」打开编程工作台，用积木创作你的第一个作品吧。</p>
      </div>
    </section>

    <section v-else class="works-grid">
      <article v-for="work in items" :key="work.id" class="work-card" :class="{ 'work-private': !work.is_public }">
        <!-- 作品封面 -->
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
          <div class="work-card-head">
            <h3>{{ work.title }}</h3>
          </div>
          <div class="work-card-meta">
            <span class="work-source">
              {{ work.source === "challenge" ? "来自闯关作品" : "自由创作" }}
            </span>
            <span>角色 {{ work.sprite_count }}</span>
            <span>{{ formatTime(work.updated_at) }}</span>
          </div>
          <div class="work-card-actions">
            <button class="work-action primary-action" :disabled="busy" @click="studioEdit(work.id)">
              继续编辑
            </button>
            <button
              v-if="work.has_content"
              class="work-action"
              :disabled="busy"
              @click="studioPreview(work.id)"
            >
              预览
            </button>
            <button class="work-action" :disabled="busy" @click="togglePublic(work)">
              {{ work.is_public ? "设为私密" : "设为公开" }}
            </button>
            <template v-if="renamingId === work.id">
              <input
                v-model="renameValue"
                class="rename-input"
                maxlength="120"
                @keyup.enter="confirmRename(work)"
                @keyup.esc="renamingId = null"
              />
              <button class="work-action" :disabled="busy" @click="confirmRename(work)">保存</button>
              <button class="work-action ghost" @click="renamingId = null">取消</button>
            </template>
            <button v-else class="work-action" :disabled="busy" @click="startRename(work)">
              重命名
            </button>
            <button class="work-action danger" :disabled="busy" @click="removeWork(work)">删除</button>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>
