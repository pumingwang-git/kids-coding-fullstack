<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../services/notifications";

const router = useRouter();
const items = ref([]);
const page = ref(1);
const total = ref(0);
const tab = ref("all");
const loading = ref(true);
const loadingMore = ref(false);
const error = ref("");
const markingAll = ref(false);
const hasMore = computed(() => items.value.length < total.value);

function formatTime(value) {
  return value
    ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
        new Date(value),
      )
    : "";
}

async function load({ append = false } = {}) {
  if (append) loadingMore.value = true;
  else loading.value = true;
  error.value = "";
  try {
    const data = await listNotifications({ tab: tab.value, page: page.value });
    items.value = append ? [...items.value, ...(data.items || [])] : data.items || [];
    total.value = data.total || 0;
  } catch (reason) {
    error.value = reason.message || "通知暂时无法打开，请稍后重试。";
  } finally {
    if (append) loadingMore.value = false;
    else loading.value = false;
  }
}

function changeTab(value) {
  tab.value = value;
  page.value = 1;
  load();
}

async function openNotice(item) {
  if (item.revoked_at) return;
  if (!item.read_at) {
    try {
      await markNotificationRead(item.id);
      item.read_at = new Date().toISOString();
    } catch {
      // Opening a server-approved destination remains useful even if the
      // best-effort read receipt is temporarily unavailable.
    }
  }
  if (item.link_url?.startsWith("/") && !item.link_url.startsWith("//")) router.push(item.link_url);
}

async function markAll() {
  markingAll.value = true;
  try {
    await markAllNotificationsRead();
    items.value.forEach((item) => {
      item.read_at ||= new Date().toISOString();
    });
  } catch (reason) {
    error.value = reason.message || "暂时无法更新已读状态。";
  } finally {
    markingAll.value = false;
  }
}

function loadMore() {
  if (!hasMore.value || loadingMore.value) return;
  page.value += 1;
  load({ append: true });
}

onMounted(load);
</script>

<template>
  <main class="kids-page notifications-page">
    <header class="notifications-heading">
      <div>
        <h1>通知</h1>
        <p>查看作业、成绩和教师协作的最新动态。</p>
      </div>
      <button class="button" type="button" :disabled="markingAll" @click="markAll">
        <AppIcon name="check" :size="17" /> {{ markingAll ? "正在更新..." : "全部标为已读" }}
      </button>
    </header>

    <nav class="notifications-tabs" aria-label="通知筛选">
      <button
        type="button"
        :class="{ active: tab === 'all' }"
        :aria-pressed="tab === 'all'"
        @click="changeTab('all')"
      >
        全部
      </button>
      <button
        type="button"
        :class="{ active: tab === 'unread' }"
        :aria-pressed="tab === 'unread'"
        @click="changeTab('unread')"
      >
        未读
      </button>
    </nav>

    <p v-if="loading" class="notifications-state" aria-live="polite">正在加载通知...</p>
    <section v-else-if="error" class="notifications-state notifications-error" role="alert">
      <p>{{ error }}</p>
      <button class="button button-primary" type="button" @click="load">重新加载</button>
    </section>
    <section v-else-if="!items.length" class="notifications-state notifications-empty">
      <AppIcon name="check" :size="30" />
      <h2>暂时没有通知</h2>
      <p>新的作业、成绩和教师回复会在这里出现。</p>
    </section>
    <section v-else class="notifications-list" aria-label="通知列表">
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        class="notification-item"
        :class="{ unread: !item.read_at, revoked: item.revoked_at }"
        @click="openNotice(item)"
      >
        <span class="notification-dot" aria-hidden="true"></span>
        <span class="notification-copy"
          ><span class="notification-title">{{ item.title }}</span
          ><span class="notification-body">{{
            item.revoked_at ? "这条通知已撤回。" : item.body
          }}</span
          ><span class="notification-time">{{ formatTime(item.created_at) }}</span></span
        >
        <AppIcon v-if="item.link_url && !item.revoked_at" name="arrow-right" :size="18" />
      </button>
      <button
        v-if="hasMore"
        class="notifications-more"
        type="button"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? "正在加载..." : "加载更多" }}
      </button>
    </section>
  </main>
</template>

<style scoped>
.notifications-page {
  max-width: 920px;
}
.notifications-heading,
.notifications-tabs,
.notification-item {
  display: flex;
  align-items: center;
}
.notifications-heading {
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line);
}
.notifications-heading h1 {
  margin: 0;
  font: 800 30px/1.2 var(--font-display);
}
.notifications-heading p,
.notification-body,
.notification-time {
  color: var(--muted);
}
.notifications-heading p {
  margin: 7px 0 0;
}
.notifications-tabs {
  gap: 8px;
  margin: 16px 0;
}
.notifications-tabs button {
  min-height: 38px;
  padding: 7px 14px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--kids-panel);
  color: var(--muted);
  font-weight: 800;
}
.notifications-tabs button.active {
  border-color: var(--accent);
  background: var(--mint);
  color: var(--accent);
}
.notifications-list {
  display: grid;
  gap: 8px;
}
.notification-item {
  width: 100%;
  gap: 13px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--kids-panel);
  color: var(--ink);
  text-align: left;
}
.notification-item:hover {
  border-color: var(--accent);
}
.notifications-page button:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--accent) 70%, white);
  outline-offset: 3px;
}
.notification-copy {
  display: grid;
  flex: 1;
  min-width: 0;
  gap: 5px;
}
.notification-title,
.notification-body {
  overflow-wrap: anywhere;
}
.notification-item.unread .notification-title {
  font-weight: 900;
}
.notification-body {
  line-height: 1.55;
}
.notification-time {
  font-size: 12px;
}
.notification-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  border-radius: 50%;
  background: transparent;
}
.notification-item.unread .notification-dot {
  background: var(--accent);
}
.notification-item.revoked {
  opacity: 0.7;
}
.notifications-state {
  display: grid;
  justify-items: center;
  gap: 10px;
  min-height: 220px;
  padding: 28px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--kids-panel);
  color: var(--muted);
  text-align: center;
}
.notifications-state h2,
.notifications-state p {
  margin: 0;
}
.notifications-error {
  color: var(--danger);
}
.notifications-more {
  justify-self: center;
  min-height: 42px;
  padding: 8px 16px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--kids-panel);
  color: var(--accent);
  font-weight: 800;
}
@media (max-width: 540px) {
  .notifications-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .notifications-heading .button {
    width: 100%;
  }
  .notification-item {
    align-items: flex-start;
  }
}
</style>
