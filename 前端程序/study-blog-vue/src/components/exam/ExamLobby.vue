<script setup>
// 候考页：卷面摘要、时间安排、次数、历史成绩、开始按钮。
// 这一页故意不含任何题目内容——服务端也不会发。
import { computed, ref } from "vue";
import { QUESTION_TYPE_TEXT, fetchAttemptHistory } from "../../services/exam";
import MarkdownBody from "./MarkdownBody.vue";

const props = defineProps({
  entry: { type: Object, required: true },
  // 课时作业没有 token（它的入口是 lessonId + blockId），所以不能是 required——
  // 那会让每次进作业页都刷一条 prop 校验警告。历史记录走 historyLoader，
  // 下面那条 fetchAttemptHistory(props.token) 只是考试链接的兜底。
  token: { type: String, default: "" },
  historyLoader: { type: Function, default: null },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["start", "review"]);

const PHASE_TEXT = {
  waiting: "尚未开放",
  entry_open: "候考中",
  open: "进行中",
  closed: "已结束",
};

function fmt(iso) {
  if (!iso) return "不限";
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

const breakdown = computed(() =>
  Object.entries(props.entry.paper.type_breakdown || {})
    .filter(([, count]) => count)
    .map(([type, count]) => `${QUESTION_TYPE_TEXT[type] || type} ${count} 道`)
    .join(" · "),
);

const attemptsText = computed(() => {
  const { used, limit } = props.entry.attempts;
  return limit === 0 ? `已作答 ${used} 次（不限次数）` : `已作答 ${used} / ${limit} 次`;
});

// ---------- 历史作答 ----------
// 一百次记录不能平铺。三层：摘要（最好/最近/次数）→ 最近 5 条 + 算数的那次 → 按需分页。
// 服务端只发前两层，第三层点开才拉，见 services/exam.js 的 fetchAttemptHistory。

const POLICY_TEXT = {
  best: "最好成绩",
  last: "最后一次",
  first: "第一次",
};

const summary = computed(() => props.entry.attempts.summary || {});
const policyText = computed(() => POLICY_TEXT[summary.value.score_policy] || "最好成绩");

function scoreText(item) {
  if (!item) return "—";
  return "total_score" in item ? `${item.total_score} 分` : "已完成";
}

function statusText(item) {
  if (item.status === "ongoing") return "进行中";
  return item.status === "submitted" ? "已交卷" : "已结束";
}

function durationText(seconds) {
  if (seconds == null) return "";
  const minutes = Math.floor(seconds / 60);
  return minutes ? `用时 ${minutes} 分` : `用时 ${seconds} 秒`;
}

function whenText(item) {
  const iso = item.submitted_at || item.started_at;
  if (!iso) return "";
  return new Date(iso).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

// 展开全部：分页拉取，不是前端 slice——列表可能有几百条
const expanded = ref(false);
const pageData = ref(null);
const pageNo = ref(1);
const pageSize = 20;
const loadingPage = ref(false);
const pageError = ref("");

const pageCount = computed(() =>
  pageData.value ? Math.max(1, Math.ceil(pageData.value.total / pageSize)) : 1,
);

async function loadPage(page) {
  loadingPage.value = true;
  pageError.value = "";
  try {
    const loadHistory =
      props.historyLoader || ((params) => fetchAttemptHistory(props.token, params));
    pageData.value = await loadHistory({ page, size: pageSize });
    pageNo.value = page;
  } catch (error) {
    pageError.value = error.message || "记录加载失败。";
  } finally {
    loadingPage.value = false;
  }
}

async function toggleAll() {
  expanded.value = !expanded.value;
  if (expanded.value && !pageData.value) await loadPage(1);
}
</script>

<template>
  <div class="exam-narrow">
    <div class="sticker" style="padding: 2rem">
      <span class="pill">{{ PHASE_TEXT[entry.phase] || entry.phase }}</span>
      <h1 style="margin: 1rem 0 0.5rem">{{ entry.paper.title }}</h1>
      <p class="muted" style="margin: 0">{{ entry.link.name }} · {{ entry.paper.paper_type }}</p>
      <MarkdownBody v-if="entry.paper.description" :source="entry.paper.description" />

      <div class="stat-row">
        <div class="stat">
          <b>{{ entry.paper.question_count }}</b
          ><span class="muted">题目</span>
        </div>
        <div class="stat">
          <b>{{ entry.paper.total_score }}</b
          ><span class="muted">总分</span>
        </div>
        <div class="stat">
          <b>{{
            entry.link.duration_minutes ? entry.link.duration_minutes + " 分钟" : "不限时"
          }}</b>
          <span class="muted">时长</span>
        </div>
      </div>
      <p class="muted">{{ breakdown }}</p>

      <dl
        style="display: grid; grid-template-columns: auto 1fr; gap: 0.4rem 1rem; margin: 1.25rem 0"
      >
        <dt><strong>开放时间</strong></dt>
        <dd style="margin: 0">{{ fmt(entry.link.open_at) }}</dd>
        <dt><strong>关闭时间</strong></dt>
        <dd style="margin: 0">{{ fmt(entry.link.close_at) }}</dd>
        <dt><strong>作答次数</strong></dt>
        <dd style="margin: 0">{{ attemptsText }}</dd>
      </dl>

      <div v-if="entry.blocked_reason" class="notice-box">{{ entry.blocked_reason }}</div>

      <div style="display: flex; gap: 1rem; margin-top: 1.5rem; flex-wrap: wrap">
        <button
          class="btn-chunky btn-primary"
          type="button"
          :disabled="!entry.can_start || busy"
          @click="emit('start')"
        >
          {{ entry.attempts.ongoing_attempt_id ? "继续作答" : "开始作答" }}
        </button>
      </div>
    </div>

    <div
      v-if="entry.attempts.history.length"
      class="sticker-flat"
      style="padding: 1.25rem; margin-top: 1.5rem"
    >
      <h2 style="margin-top: 0; font-size: 1.05rem">历史作答</h2>

      <!-- 摘要先行：一百行记录里真正有决策价值的就这三个数 + 一句"哪次算数" -->
      <div class="history-summary">
        <div v-if="summary.best" class="stat">
          <b>{{ scoreText(summary.best) }}</b
          ><span class="muted">最好成绩</span>
        </div>
        <div v-if="summary.last" class="stat">
          <b>{{ scoreText(summary.last) }}</b
          ><span class="muted">最近一次</span>
        </div>
        <div class="stat">
          <b>{{ summary.count }} 次</b><span class="muted">已作答</span>
        </div>
      </div>
      <p class="muted history-policy">
        本场按<strong>{{ policyText }}</strong
        >计入成绩<span v-if="summary.counted_attempt_id">，下方带「计分」的那次即是</span>
      </p>

      <div
        v-for="item in entry.attempts.history"
        :key="item.attempt_id"
        class="history-row"
        :class="{ 'is-counted': item.counted, 'is-ongoing': item.status === 'ongoing' }"
      >
        <span class="history-no">第 {{ item.attempt_no }} 次</span>
        <span v-if="item.counted" class="history-flag">计分</span>
        <span class="muted history-when">{{ whenText(item) }}</span>
        <span class="muted history-duration">{{ durationText(item.duration_seconds) }}</span>
        <span class="history-score">
          <template v-if="item.status === 'ongoing'">{{ statusText(item) }}</template>
          <template v-else>{{ scoreText(item) }}</template>
        </span>
        <button
          v-if="item.status === 'submitted'"
          class="btn-chunky btn-sm"
          type="button"
          @click="emit('review', item.attempt_id)"
        >
          查看
        </button>
      </div>

      <!-- 展开全部：点开才拉，分页取，不把几百条挂在候考页的必经接口上 -->
      <button
        v-if="summary.has_more || expanded"
        class="btn-text history-more"
        type="button"
        @click="toggleAll"
      >
        {{ expanded ? "收起" : `查看全部 ${summary.count} 次记录` }}
      </button>

      <div v-if="expanded" class="history-all">
        <p v-if="loadingPage" class="muted">正在加载…</p>
        <p v-else-if="pageError" class="error-box">{{ pageError }}</p>
        <template v-else-if="pageData">
          <div
            v-for="item in pageData.items"
            :key="item.attempt_id"
            class="history-row"
            :class="{ 'is-counted': item.counted }"
          >
            <span class="history-no">第 {{ item.attempt_no }} 次</span>
            <span v-if="item.counted" class="history-flag">计分</span>
            <span class="muted history-when">{{ whenText(item) }}</span>
            <span class="muted history-duration">{{ durationText(item.duration_seconds) }}</span>
            <span class="history-score">
              <template v-if="item.status === 'ongoing'">{{ statusText(item) }}</template>
              <template v-else>{{ scoreText(item) }}</template>
            </span>
            <button
              v-if="item.status === 'submitted'"
              class="btn-chunky btn-sm"
              type="button"
              @click="emit('review', item.attempt_id)"
            >
              查看
            </button>
          </div>
          <div v-if="pageCount > 1" class="history-pager">
            <button
              class="btn-chunky btn-sm"
              type="button"
              :disabled="pageNo <= 1 || loadingPage"
              @click="loadPage(pageNo - 1)"
            >
              上一页
            </button>
            <span class="muted">{{ pageNo }} / {{ pageCount }}</span>
            <button
              class="btn-chunky btn-sm"
              type="button"
              :disabled="pageNo >= pageCount || loadingPage"
              @click="loadPage(pageNo + 1)"
            >
              下一页
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
