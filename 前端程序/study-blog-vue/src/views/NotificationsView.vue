<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  unreadNotificationCount,
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
// null = 计数接口没答上来。此时按钮保持可点，不要因为「未知」把入口锁死。
const unread = ref(null);
const hasMore = computed(() => items.value.length < total.value);
const canMarkAll = computed(() => unread.value !== 0 && !markingAll.value);

const clockFormat = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const fullFormat = new Intl.DateTimeFormat("zh-CN", { dateStyle: "long", timeStyle: "short" });

function dayStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function dayLabel(value) {
  if (!value) return "更早";
  const date = new Date(value);
  const now = new Date();
  const days = Math.round((dayStart(now) - dayStart(date)) / 86400000);
  if (days <= 0) return "今天";
  if (days === 1) return "昨天";
  if (date.getFullYear() === now.getFullYear())
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

// 列表已按天分组，条目里再重复一次日期是噪音：只给「今天多久以前」或当天时刻。
function shortTime(value) {
  if (!value) return "";
  const date = new Date(value);
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  return clockFormat.format(date);
}

function fullTime(value) {
  return value ? fullFormat.format(new Date(value)) : "";
}

// 相邻同一天的条目并成一组；接口已按时间倒序，这里不再排序。
const groups = computed(() => {
  const out = [];
  for (const item of items.value) {
    const label = dayLabel(item.created_at);
    if (!out.length || out[out.length - 1].label !== label) out.push({ label, items: [] });
    out[out.length - 1].items.push(item);
  }
  return out;
});

async function refreshUnread() {
  try {
    const data = await unreadNotificationCount();
    unread.value = Number(data.count || 0);
  } catch {
    unread.value = null;
  }
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

function reload() {
  page.value = 1;
  load();
}

function changeTab(value) {
  if (tab.value === value) return;
  tab.value = value;
  reload();
}

async function openNotice(item) {
  if (item.revoked_at) return;
  if (!item.read_at) {
    try {
      await markNotificationRead(item.id);
      item.read_at = new Date().toISOString();
      if (typeof unread.value === "number") unread.value = Math.max(0, unread.value - 1);
    } catch {
      // Opening a server-approved destination remains useful even if the
      // best-effort read receipt is temporarily unavailable.
    }
  }
  // 答疑通知在同一应用壳里打开浮窗。replace 保留通知页之前的真实来源，浏览器返回可回到学习页面。
  if (item.link_url?.startsWith("/") && !item.link_url.startsWith("//")) router.replace(item.link_url);
}

async function markAll() {
  markingAll.value = true;
  try {
    await markAllNotificationsRead();
    items.value.forEach((item) => {
      item.read_at ||= new Date().toISOString();
    });
    unread.value = 0;
    // 「未读」页签下这批条目已经不该留在列表里，重新取一次免得剩一屏幽灵。
    if (tab.value === "unread") reload();
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

onMounted(() => {
  load();
  refreshUnread();
});
</script>

<template>
  <main class="kids-page notifications-page">
    <header class="notifications-heading">
      <div>
        <h1>
          通知
          <span v-if="unread" class="unread-pill">{{ unread > 99 ? "99+" : unread }} 条未读</span>
        </h1>
        <p>查看作业、成绩和教师协作的最新动态。</p>
      </div>
      <button class="button" type="button" :disabled="!canMarkAll" @click="markAll">
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
        <b v-if="unread" class="tab-count">{{ unread > 99 ? "99+" : unread }}</b>
      </button>
    </nav>

    <!-- 骨架尺寸照抄真实卡片（chip 18 + 标题 17 + 正文两行 12），差太多就等于
         「加载完跳一下」，还不如不做。颜色只用 --mint，不新增灰度色。 -->
    <div v-if="loading" class="notifications-skeleton" role="status" aria-label="正在加载通知">
      <div v-for="n in 3" :key="n" class="skeleton-card">
        <span class="sk sk-chip"></span>
        <span class="sk sk-title"></span>
        <span class="sk sk-body"></span>
        <span class="sk sk-body sk-short"></span>
      </div>
    </div>
    <section v-else-if="error" class="notifications-state notifications-error" role="alert">
      <AppIcon name="info" :size="26" />
      <p class="state-title">{{ error }}</p>
      <button class="button button-primary" type="button" @click="reload">
        <AppIcon name="refresh" :size="17" /> 重新加载
      </button>
    </section>
    <section v-else-if="!items.length" class="notifications-state notifications-empty">
      <span class="state-medallion" aria-hidden="true"><AppIcon name="bell" :size="26" /></span>
      <h2 class="state-title">{{ tab === "unread" ? "未读通知已清空" : "暂时没有通知" }}</h2>
      <p>
        {{
          tab === "unread"
            ? "最新动态都看过了，历史通知还在「全部」里。"
            : "新的作业、成绩和教师回复会在这里出现。"
        }}
      </p>
      <button
        v-if="tab === 'unread'"
        class="notifications-more"
        type="button"
        @click="changeTab('all')"
      >
        查看全部通知
      </button>
    </section>
    <section v-else class="notifications-list" aria-label="通知列表" :aria-busy="loadingMore">
      <div v-for="group in groups" :key="group.label" class="notification-group">
        <h2 class="group-label">{{ group.label }}</h2>
        <button
          v-for="item in group.items"
          :key="item.id"
          type="button"
          class="notification-item"
          :class="{ unread: !item.read_at, revoked: item.revoked_at }"
          @click="openNotice(item)"
        >
          <span class="notification-copy">
            <span class="notification-meta">
              <span v-if="item.kind_label" class="notification-kind">{{ item.kind_label }}</span>
              <time
                class="notification-time"
                :datetime="item.created_at"
                :title="fullTime(item.created_at)"
                >{{ shortTime(item.created_at) }}</time
              >
            </span>
            <span class="notification-title">{{ item.title }}</span>
            <span class="notification-body">{{
              item.revoked_at ? "这条通知已撤回。" : item.body
            }}</span>
          </span>
          <AppIcon
            v-if="item.link_url && !item.revoked_at"
            class="notification-caret"
            name="arrow-right"
            :size="18"
          />
        </button>
      </div>
      <button
        v-if="hasMore"
        class="notifications-more"
        type="button"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? "正在加载..." : "加载更多" }}
      </button>
      <p v-else-if="items.length > 4" class="notifications-end">已经到底了</p>
    </section>
  </main>
</template>

<style scoped>
.notifications-page {
  /* 深色下 --accent（深绿）落在深色卡片上就糊了。这一页统一走 --n-accent，
     深色主题只换这一处，不用给每个元素各补一条 :root.dark 覆盖。 */
  --n-accent: var(--accent);
  max-width: 900px;
}
:root.dark .notifications-page {
  --n-accent: #7ec8b1;
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
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font: 800 22px/1.35 var(--font-display);
  letter-spacing: -0.01em;
}
/* 不带修饰类的 .button 只有排版没有配色，会落到浏览器默认灰上，
   在这一页糊成一块「没做完」的方块。这里补齐它的皮肤。 */
.notifications-heading .button {
  gap: 7px;
  min-height: 36px;
  padding: 8px 15px;
  border: 1px solid color-mix(in srgb, var(--n-accent) 32%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--n-accent) 12%, transparent);
  color: var(--n-accent);
  font-size: 13px;
}
.notifications-heading .button:hover:not(:disabled) {
  border-color: var(--n-accent);
}
.unread-pill,
.tab-count,
.notifications-tabs button.active {
  background: var(--n-accent);
  color: var(--paper);
}
.unread-pill {
  padding: 2px 10px;
  border-radius: 999px;
  font: 700 12px/1.6 var(--font-body);
  letter-spacing: 0;
}
.notifications-heading p,
.notification-body,
.notification-time,
.group-label,
.notifications-end {
  color: var(--muted);
}
.notifications-heading p {
  margin: 6px 0 0;
  font-size: 13px;
}
.notifications-tabs {
  gap: 8px;
  margin: 16px 0 14px;
}
.notifications-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 5px 14px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--kids-panel);
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
}
.notifications-tabs button:hover {
  border-color: var(--n-accent);
  color: var(--n-accent);
}
.notifications-tabs button.active {
  border-color: transparent;
}
.tab-count {
  min-width: 18px;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 11px;
  text-align: center;
}
.notifications-tabs button.active .tab-count {
  background: color-mix(in srgb, var(--paper) 28%, transparent);
  color: var(--paper);
}
.notifications-list,
.notification-group {
  display: grid;
  gap: 8px;
}
.notification-group + .notification-group {
  margin-top: 14px;
}
.group-label {
  margin: 0;
  padding-left: 2px;
  font: 700 12px/1.6 var(--font-body);
  letter-spacing: 0.04em;
}
.notification-item {
  position: relative;
  overflow: hidden;
  width: 100%;
  gap: 14px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--kids-panel);
  color: var(--ink);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}
/* 未读用左侧色条而不是小圆点：扫一眼列表就知道哪几条还没看。 */
.notification-item::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: transparent;
}
.notification-item.unread::before {
  background: var(--n-accent);
}
.notification-item.unread {
  background: color-mix(in srgb, var(--n-accent) 8%, var(--kids-panel));
}
.notification-item:hover:not(.revoked) {
  border-color: color-mix(in srgb, var(--n-accent) 55%, transparent);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--n-accent) 12%, transparent);
  transform: translateY(-1px);
}
.notification-caret {
  color: var(--muted);
  transition: transform 0.16s ease;
}
.notification-item:hover .notification-caret {
  color: var(--n-accent);
  transform: translateX(2px);
}
.notifications-page button:focus-visible {
  outline: 2px solid var(--n-accent);
  outline-offset: 2px;
}
.notification-copy {
  display: grid;
  flex: 1;
  min-width: 0;
  gap: 4px;
}
.notification-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.notification-kind {
  padding: 2px 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--n-accent) 14%, transparent);
  color: var(--n-accent);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.notification-title,
.notification-body {
  overflow-wrap: anywhere;
}
.notification-title {
  font-size: 15px;
  font-weight: 700;
}
.notification-item.unread .notification-title {
  font-weight: 800;
}
.notification-body {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  font-size: 13px;
  line-height: 1.6;
}
.notification-time {
  font-size: 11px;
}
.notification-item :deep(.app-icon) {
  color: var(--muted);
}
.notification-item.revoked {
  opacity: 0.68;
}
.notification-item.revoked .notification-title {
  text-decoration: line-through;
}
.notifications-state {
  display: grid;
  justify-items: center;
  gap: 10px;
  padding: 40px 28px;
  border: 1px dashed var(--line);
  border-radius: 14px;
  background: var(--kids-panel);
  color: var(--muted);
  text-align: center;
}
.state-medallion {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--n-accent) 14%, transparent);
  color: var(--n-accent);
}
.notifications-state h2,
.notifications-state p {
  margin: 0;
}
/* 全局 h2 是 clamp(26px,3vw,40px) 的衬线大标题，空状态套上去会糊满半屏。 */
.state-title {
  color: var(--ink);
  font: 700 16px/1.5 var(--font-body);
  letter-spacing: 0;
}
.notifications-state p {
  font-size: 13px;
}
.notifications-error {
  border-style: solid;
  border-color: color-mix(in srgb, var(--danger) 45%, var(--line));
  color: var(--danger);
}
.notifications-error .state-title {
  color: var(--danger);
}
.notifications-error .button-primary {
  min-height: 36px;
  padding: 8px 16px;
  gap: 7px;
  border-radius: 999px;
  font-size: 13px;
}
.notifications-more {
  justify-self: center;
  min-height: 36px;
  margin-top: 6px;
  padding: 7px 18px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--kids-panel);
  color: var(--n-accent);
  font-size: 13px;
  font-weight: 700;
}
.notifications-more:hover:not(:disabled) {
  border-color: var(--n-accent);
}
.notifications-end {
  margin: 8px 0 0;
  font-size: 12px;
  text-align: center;
}
.notifications-skeleton {
  display: grid;
  gap: 8px;
}
.skeleton-card {
  display: grid;
  gap: 9px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--kids-panel);
}
.sk {
  display: block;
  border-radius: 999px;
  background: color-mix(in srgb, var(--n-accent) 16%, transparent);
  animation: notifications-sk-pulse 1.4s ease-in-out infinite;
}
.sk-chip {
  width: 88px;
  height: 16px;
}
.sk-title {
  width: 58%;
  height: 15px;
}
.sk-body {
  width: 100%;
  height: 12px;
}
.sk-short {
  width: 42%;
}
@keyframes notifications-sk-pulse {
  0%,
  100% {
    opacity: 0.5;
  }
  50% {
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk {
    animation: none;
    opacity: 0.65;
  }
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
    padding: 12px 14px;
  }
  .notifications-state {
    padding: 32px 20px;
  }
}
</style>
