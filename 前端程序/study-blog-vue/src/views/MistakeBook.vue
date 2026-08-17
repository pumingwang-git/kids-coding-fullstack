<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { request } from "../services/auth";

const route = useRoute();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const items = ref([]);
const summary = ref({ total: 0, due: 0, mastered: 0, recent_review_accuracy: null });
const total = ref(0);
const page = ref(1);
const size = ref(20);
const loading = ref(true);
const loadingMore = ref(false);
const error = ref("");
const status = ref("");
const sourceType = ref("");
const fromDate = ref("");
const toDate = ref("");

const statusLabels = { pending_review: "待复习", mastered: "已掌握" };
const masteryLabels = {
  unmastered: "未掌握",
  basic: "初步掌握",
  strengthening: "巩固中",
  mastered: "已掌握",
};

function formatDate(value) {
  return value
    ? new Date(value).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })
    : "-";
}

async function load({ append = false } = {}) {
  if (append) loadingMore.value = true;
  else loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({ page: String(page.value), size: String(size.value) });
    if (status.value) params.set("status", status.value);
    if (sourceType.value) params.set("source_type", sourceType.value);
    if (fromDate.value) params.set("from", fromDate.value);
    if (toDate.value) params.set("to", toDate.value);
    const listPromise = request(`/api/student/mistakes?${params.toString()}`);
    const [list, overview] = await Promise.all([listPromise, append ? Promise.resolve(null) : request("/api/student/mistakes/summary")]);
    items.value = append ? [...items.value, ...(list.items || [])] : list.items || [];
    total.value = list.total || 0;
    page.value = list.page || page.value;
    size.value = list.size || size.value;
    if (overview) summary.value = overview;
  } catch (reason) {
    error.value = reason.message || "错题本暂时无法打开，请稍后重试。";
  } finally {
    if (append) loadingMore.value = false;
    else loading.value = false;
  }
}

function resetList() {
  page.value = 1;
  load();
}

function loadMore() {
  if (loading.value || loadingMore.value || items.value.length >= total.value) return;
  page.value += 1;
  load({ append: true });
}

watch([status, sourceType, fromDate, toDate], resetList);
onMounted(load);
</script>

<template>
  <main class="kids-page mistakes-page">
    <header class="mistakes-heading">
      <div>
        <h1>我的错题</h1>
        <p>系统会把每次正式判错的题目归纳在这里。重做后，复习记录和掌握度会自动更新。</p>
        <RouterLink
          v-if="summary.due && items.find((item) => item.status === 'pending_review')"
          class="primary-action"
          :to="`/areas/${areaKey}/tasks/mistakes/review`"
        >
          <AppIcon name="check" :size="18" /> 开始复习 {{ summary.due }} 题
        </RouterLink>
      </div>
      <img src="/assets/otter-thinking-720.webp" alt="正在思考题目的水獭" />
    </header>

    <nav class="mistake-nav" aria-label="错题本视图">
      <RouterLink class="mistake-nav-link active" :to="`/areas/${areaKey}/tasks/mistakes`"><AppIcon name="book" :size="17" /> 错题列表</RouterLink>
      <RouterLink class="mistake-nav-link" :to="`/areas/${areaKey}/tasks/mistakes/review`"><AppIcon name="check" :size="17" /> 复习任务</RouterLink>
      <RouterLink class="mistake-nav-link" :to="`/areas/${areaKey}/tasks/mistakes/stats`"><AppIcon name="spark" :size="17" /> 复习统计</RouterLink>
    </nav>

    <section class="mistake-summary" aria-label="错题复习摘要">
      <div>
        <strong>{{ summary.total }}</strong
        ><span>累计错题</span>
      </div>
      <div>
        <strong>{{ summary.due }}</strong
        ><span>待复习</span>
      </div>
      <div>
        <strong>{{ summary.mastered }}</strong
        ><span>已掌握</span>
      </div>
      <div>
        <strong>{{
          summary.recent_review_accuracy == null ? "-" : `${summary.recent_review_accuracy}%`
        }}</strong
        ><span>近 7 次正确率</span>
      </div>
    </section>

    <section class="mistake-filters" aria-label="更多筛选">
      <label><span>来源</span><select v-model="sourceType">
        <option value="">全部来源</option>
        <option value="lesson_practice">课程练习</option>
        <option value="lesson_homework">课后作业</option>
        <option value="exam_link">考试</option>
      </select></label>
      <label><span>从</span><input v-model="fromDate" type="date" /></label>
      <label><span>到</span><input v-model="toDate" type="date" /></label>
    </section>

    <section class="mistake-toolbar" aria-label="错题筛选">
      <div>
        <h2>错题列表</h2>
        <p>按状态、来源和时间查看自己的错题记录。已显示 {{ items.length }} / {{ total }} 题。</p>
      </div>
      <label
        ><span class="sr-only">复习状态</span
        ><select v-model="status">
          <option value="">全部状态</option>
          <option value="pending_review">待复习</option>
          <option value="mastered">已掌握</option>
        </select></label
      >
    </section>

    <p v-if="loading" class="mistake-message" aria-live="polite">正在整理你的错题...</p>
    <section v-else-if="error" class="mistake-message mistake-error" role="alert">
      <p>{{ error }}</p>
      <button class="button button-primary" type="button" @click="load">重新加载</button>
    </section>
    <section v-else-if="!items.length" class="mistake-message mistake-empty">
      <AppIcon name="check" :size="30" />
      <h2>这里还没有错题</h2>
      <p>完成课程练习、作业或考试后，系统会自动归纳需要复习的题目。</p>
      <RouterLink class="secondary-action" :to="`/areas/${areaKey}/tasks/practice`"
        >去练一练</RouterLink
      >
    </section>
    <section v-else class="mistake-list" aria-label="我的错题列表">
      <RouterLink
        v-for="item in items"
        :key="item.id"
        :to="`/areas/${areaKey}/tasks/mistakes/${item.id}`"
      >
        <div class="mistake-list-main">
          <div class="mistake-tags">
            <span class="tag" :class="item.status === 'mastered' ? 'tag-good' : 'tag-warn'">{{
              statusLabels[item.status] || item.status
            }}</span
            ><span class="mistake-source">{{ item.source_label }}</span>
          </div>
          <h2>{{ item.title }}</h2>
          <p>{{ item.stem.replace(/[#*_`]/g, " ").slice(0, 110) || "查看题目并重新作答。" }}</p>
        </div>
        <dl>
          <div>
            <dt>掌握度</dt>
            <dd>{{ masteryLabels[item.mastery_level] || item.mastery_level }}</dd>
          </div>
          <div>
            <dt>答错</dt>
            <dd>{{ item.wrong_count }} 次</dd>
          </div>
          <div>
            <dt>下次复习</dt>
            <dd>{{ formatDate(item.next_review_at) }}</dd>
          </div>
        </dl>
        <AppIcon name="arrow-right" />
      </RouterLink>
      <button
        v-if="items.length < total"
        class="mistake-load-more"
        type="button"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? "正在加载..." : `加载更多（还剩 ${total - items.length} 题）` }}
      </button>
    </section>
  </main>
</template>

<style scoped>
.mistakes-page {
  max-width: 1060px;
}
.mistakes-heading {
  position: relative;
  min-height: 230px;
  overflow: hidden;
  display: flex;
  align-items: center;
  padding: 40px clamp(28px, 5vw, 56px);
  border-radius: 24px 8px 24px 8px;
  background: var(--area-surface);
  color: #203c5b;
}
.mistakes-heading > div {
  position: relative;
  z-index: 1;
  max-width: 660px;
}
.mistakes-heading h1 {
  margin: 0;
  font: 900 44px/1.2 var(--font-display);
  letter-spacing: 0;
}
.mistakes-heading p {
  margin: 12px 0 22px;
  color: #54708d;
  line-height: 1.7;
}
.mistakes-heading img {
  position: absolute;
  right: 4%;
  bottom: -32px;
  width: 230px;
  height: 245px;
  object-fit: contain;
}
.primary-action {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.mistake-nav {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  border-bottom: 1px solid var(--line);
}
.mistake-nav-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 42px;
  padding: 0 12px;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
}
.mistake-nav-link:hover,
.mistake-nav-link.active {
  border-color: var(--accent);
  color: var(--accent);
}
.mistake-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 10px;
  margin-top: 16px;
}
.mistake-filters label {
  display: grid;
  gap: 5px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
}
.mistake-filters select,
.mistake-filters input {
  min-height: 40px;
  min-width: 126px;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--kids-panel);
  color: var(--ink);
}
.mistake-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin-top: 20px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 8px;
  background: var(--kids-panel);
  overflow: hidden;
}
.mistake-summary > div {
  min-width: 0;
  padding: 20px 22px;
  border-right: 1px solid rgba(55, 87, 123, 0.12);
}
.mistake-summary > div:last-child {
  border-right: 0;
}
.mistake-summary strong {
  display: block;
  font: 800 28px/1.1 var(--font-body);
  color: var(--accent);
}
.mistake-summary span,
.mistake-toolbar p,
.mistake-list dt {
  color: var(--muted);
  font-size: 13px;
}
.mistake-summary span {
  display: block;
  margin-top: 7px;
}
.mistake-toolbar {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 20px;
  margin-top: 38px;
}
.mistake-toolbar h2 {
  margin: 0;
  font: 800 26px/1.25 var(--font-display);
  letter-spacing: 0;
}
.mistake-toolbar p {
  margin: 6px 0 0;
}
select {
  min-height: 42px;
  min-width: 126px;
  padding: 8px 30px 8px 11px;
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--ink);
  background: var(--kids-panel);
}
.mistake-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}
.mistake-list > a {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 24px;
  align-items: center;
  gap: 24px;
  padding: 19px 20px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 8px;
  background: var(--kids-panel);
  color: inherit;
}
.mistake-list > a:hover {
  border-color: var(--kids-blue);
  box-shadow: 0 8px 18px rgba(34, 43, 40, 0.08);
}
.mistake-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.mistake-list-main,
.mistake-source,
.mistake-list h2,
.mistake-list p,
dd {
  min-width: 0;
  overflow-wrap: anywhere;
}
.tag {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}
.tag-warn {
  color: #8a5b13;
  background: rgba(244, 189, 91, 0.24);
}
.tag-good {
  color: #226551;
  background: var(--mint);
}
.mistake-source {
  color: var(--muted);
  font-size: 12px;
}
.mistake-list h2 {
  margin: 9px 0 5px;
  font-size: 17px;
}
.mistake-list p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.55;
}
.mistake-load-more {
  justify-self: center;
  min-height: 42px;
  padding: 8px 16px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--kids-panel);
  color: var(--accent);
  font-weight: 800;
  cursor: pointer;
}
.mistake-load-more:hover:not(:disabled) {
  border-color: var(--accent);
  background: var(--mint);
}
.mistake-load-more:disabled {
  cursor: wait;
  opacity: 0.65;
}
dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(74px, 1fr));
  gap: 12px;
  margin: 0;
}
dt,
dd {
  margin: 0;
}
dd {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 800;
}
.mistake-message {
  margin-top: 18px;
  padding: 32px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--kids-panel);
  color: var(--muted);
  text-align: center;
}
.mistake-message h2 {
  margin: 10px 0 6px;
  color: var(--ink);
  font-size: 21px;
}
.mistake-message p {
  margin: 0 0 16px;
  line-height: 1.6;
}
.mistake-error {
  color: var(--danger);
}
.mistake-empty {
  display: grid;
  justify-items: center;
}
.mistake-empty .app-icon {
  color: var(--accent);
}
.secondary-action {
  display: inline-flex;
  align-items: center;
  min-height: 42px;
  padding: 8px 15px;
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--ink);
  font-weight: 800;
}
@media (max-width: 800px) {
  .mistake-nav {
    overflow-x: auto;
  }
  .mistake-filters {
    align-items: stretch;
  }
  .mistake-filters label {
    flex: 1 1 140px;
  }
  .mistake-filters select,
  .mistake-filters input {
    width: 100%;
  }
  .mistakes-heading {
    min-height: 220px;
    padding: 30px 24px;
  }
  .mistakes-heading h1 {
    font-size: 34px;
  }
  .mistakes-heading img {
    width: 175px;
    opacity: 0.25;
    right: -28px;
  }
  .mistake-summary {
    grid-template-columns: repeat(2, 1fr);
  }
  .mistake-summary > div:nth-child(2) {
    border-right: 0;
  }
  .mistake-summary > div:nth-child(-n + 2) {
    border-bottom: 1px solid rgba(55, 87, 123, 0.12);
  }
  .mistake-toolbar {
    align-items: start;
    flex-direction: column;
  }
  .mistake-list > a {
    grid-template-columns: minmax(0, 1fr) 20px;
    gap: 14px;
  }
  .mistake-list dl {
    grid-column: 1/-1;
    grid-row: 2;
  }
  .mistake-list > a > .app-icon {
    grid-column: 2;
    grid-row: 1;
  }
}
@media (max-width: 480px) {
  .mistake-summary > div {
    padding: 16px;
  }
  .mistake-summary strong {
    font-size: 24px;
  }
  dl {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  dl > div:last-child {
    grid-column: 1 / -1;
  }
  dd {
    font-size: 12px;
  }
}
</style>
