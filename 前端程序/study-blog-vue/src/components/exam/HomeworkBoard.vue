<script setup>
// 课时作业的「题目列表」看板：代替传统候考页，对齐闯关式作业的心智——
// 先看到要过哪几道题、已经过了哪几道，再逐题进入作答。
//
// 数据边界：
// - 题目清单来自 entry.paper.questions（服务端只发展示元数据，题干/答案不下发）；
// - 逐题通过状态由服务端在大纲里直接下发（item.passed，「任何一次已交卷作答判对过」
//   的累计口径——分两次各做对一半的题，进度条也照样涨）；成绩不公开时这个键
//   整体缺席——缺席不是"全错"，是"没发"，整列降级为 "—"，不编服务端没说过的状态。
// - 排行榜对课时作业来源是关闭的（attempt_source.py leaderboard_enabled=False），
//   所以第二个标签是「作答记录」，不是排行榜。
import { computed, ref } from "vue";
import { QUESTION_TYPE_TEXT, fetchAttemptHistory } from "../../services/exam";

const props = defineProps({
  entry: { type: Object, required: true },
  // 课时作业没有 token；历史分页走 historyLoader，fetchAttemptHistory 只是兜底。
  token: { type: String, default: "" },
  historyLoader: { type: Function, default: null },
  busy: { type: Boolean, default: false },
  // 嵌在课时页里时为 true：隐藏「返回课时」（已经身在课时页）和页头卡片
  // （块标题 LessonPlayer 已经显示过了，再挂一张是重复）。
  embedded: { type: Boolean, default: false },
});
const emit = defineEmits(["start", "review", "back"]);

// ---------- 题目清单 ----------

const questions = computed(() => props.entry.paper.questions || []);

// 难度色阶沿用洛谷语义（绿→蓝→紫→红），色值从本系统令牌派生，不另起调色盘。
const DIFFICULTY_TONE = [
  [/^入门/, "easy"],
  [/^普及\/?提高-|普及-|普及$/, "mid"],
  [/普及\+|提高/, "hard"],
  [/省选|NOI/, "expert"],
];
function difficultyTone(text) {
  for (const [pattern, tone] of DIFFICULTY_TONE) if (pattern.test(text || "")) return tone;
  return "mid";
}

// ---------- 逐题通过状态 ----------

// passed 键在不在 = 服务端认为成绩可不可见。在的话 true 已通过 / false 未通过。
const scoreVisible = computed(() => questions.value.some((item) => "passed" in item));
const passedCount = computed(() => questions.value.filter((item) => item.passed).length);
const allPassed = computed(
  () => scoreVisible.value && questions.value.length > 0 && passedCount.value === questions.value.length,
);

// ---------- 标签页 ----------

const tab = ref("list"); // list / history

// ---------- 作答记录（沿用候考页的三层：摘要 → 最近 5 条 → 分页） ----------

const POLICY_TEXT = { best: "最好成绩", last: "最后一次", first: "第一次" };
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
  <div class="exam-narrow hw-board">
    <!-- 页头：这份作业是什么 + 规则胶囊。嵌入课时页时块标题已在外面，省略。 -->
    <div v-if="!embedded" class="sticker hw-head">
      <div class="hw-title-row">
        <h1 class="hw-title">{{ entry.link.name }}</h1>
        <span class="pill">{{ entry.paper.paper_type }}</span>
      </div>
      <p class="muted hw-sub">{{ entry.paper.title }} · 共 {{ entry.paper.question_count }} 题</p>
      <div class="hw-meta">
        <span class="ltag">总分 {{ entry.paper.total_score }}</span>
        <span class="ltag">
          {{ entry.attempts.limit ? `最多作答 ${entry.attempts.limit} 次` : "作答次数不限" }}
        </span>
        <span v-if="entry.link.close_at" class="ltag on-warn">
          截止 {{ new Date(entry.link.close_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) }}
        </span>
      </div>
    </div>

    <!-- 不能开考的原因两种模式都得看见，不放页头里。 -->
    <div v-if="entry.blocked_reason" class="notice-box hw-blocked">{{ entry.blocked_reason }}</div>

    <!-- 标签页 -->
    <div class="hw-tabs" role="tablist">
      <button
        class="hw-tab"
        :class="{ active: tab === 'list' }"
        type="button"
        role="tab"
        @click="tab = 'list'"
      >
        题目列表
      </button>
      <button
        class="hw-tab"
        :class="{ active: tab === 'history' }"
        type="button"
        role="tab"
        @click="tab = 'history'"
      >
        作答记录
      </button>
    </div>

    <!-- 题目列表。整个标签页内容限制在滚动框里：题目多了也只在自己框里滚，
         不把课时页/候考页整体顶长；底部行动条留在框外，永远看得见。 -->
    <template v-if="tab === 'list'">
      <div class="hw-scroll">
        <div class="sticker-flat hw-progress" :class="{ done: allPassed }">
        <template v-if="scoreVisible">
          <span class="hw-progress-label">我通过的题目</span>
          <div class="hw-progress-track">
            <div
              class="hw-progress-bar"
              :style="{ width: (questions.length ? (passedCount / questions.length) * 100 : 0) + '%' }"
            ></div>
          </div>
          <span class="hw-progress-num">{{ passedCount }} / {{ questions.length }}</span>
          <span v-if="allPassed" class="hw-progress-cheer">全部通过 🎉</span>
        </template>
        <template v-else>
          <span class="muted">
            {{
              entry.attempts.used
                ? "本作业不公开逐题对错，交卷后可查看成绩。"
                : "还没有作答记录，从第一题开始吧。"
            }}
          </span>
        </template>
      </div>

      <div class="sticker-flat hw-table-wrap">
        <table class="hw-table">
          <thead>
            <tr>
              <th class="col-status">状态</th>
              <th class="col-no">序号</th>
              <th>题目名称</th>
              <th class="col-type">题型</th>
              <th class="col-diff">难度</th>
              <th class="col-score">分值</th>
              <th class="col-op">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in questions" :key="item.problem_id_no">
              <td class="col-status">
                <span
                  v-if="scoreVisible"
                  class="hw-status"
                  :class="item.passed ? 'passed' : item.answered ? 'failed' : ''"
                >
                  {{ item.passed ? "✓ 已通过" : item.answered ? "✗ 未通过" : "—" }}
                </span>
                <span v-else class="hw-status">—</span>
              </td>
              <td class="col-no mono">{{ index + 1 }}</td>
              <td>
                <div class="hw-qname">{{ item.missing ? "（题目已下架）" : item.title }}</div>
                <div v-if="item.knowledge?.length" class="hw-qtags">
                  <span v-for="name in item.knowledge" :key="name" class="ltag">{{ name }}</span>
                </div>
              </td>
              <td class="col-type muted">{{ QUESTION_TYPE_TEXT[item.type] || item.type || "—" }}</td>
              <td class="col-diff">
                <span class="hw-diff" :class="difficultyTone(item.difficulty)">
                  {{ item.difficulty || "—" }}
                </span>
              </td>
              <td class="col-score mono">{{ item.score }}</td>
              <td class="col-op">
                <button
                  class="btn-text hw-challenge"
                  type="button"
                  :disabled="!entry.can_start || busy || item.missing"
                  @click="emit('start', item.problem_id_no)"
                >
                  {{ entry.attempts.ongoing_attempt_id ? "继续挑战" : "开始挑战" }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      </div>

      <!-- 底部行动条。嵌入课时页时「返回课时」没意义，上下块导航由块自身的 foot 管。 -->
      <div class="hw-foot">
        <button v-if="!embedded" class="btn-chunky" type="button" @click="emit('back')">
          返回课时
        </button>
        <!-- 全部通过后主行动从「开始作答」换成「完成练习」：该收尾了，不该再把人往回拉进卷子。
             嵌入课时页时块自身的 foot 已有「下一块」导航，主按钮保留「再做一次」。 -->
        <button
          v-if="allPassed && !embedded"
          class="btn-chunky btn-primary hw-finish"
          type="button"
          @click="emit('back')"
        >
          完成练习 🎉
        </button>
        <button
          v-else
          class="btn-chunky"
          :class="allPassed ? '' : 'btn-primary'"
          type="button"
          :disabled="!entry.can_start || busy"
          @click="emit('start', null)"
        >
          {{ allPassed ? "再做一次" : entry.attempts.ongoing_attempt_id ? "继续作答" : "开始作答" }}
        </button>
        <span class="hint muted" :class="{ 'hint-done': allPassed }">
          {{ allPassed ? "全部通过，本块已完成 🎉" : "作业交卷后本块自动标记完成" }}
        </span>
      </div>
    </template>

    <!-- 作答记录：表格化。摘要留在外面当决策信息，明细在滚动框里。 -->
    <template v-else>
      <div v-if="!entry.attempts.history.length" class="sticker-flat hw-empty muted">
        还没有作答记录。
      </div>
      <template v-else>
        <div class="sticker-flat hw-history">
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
            本作业按<strong>{{ policyText }}</strong
            >计入成绩<span v-if="summary.counted_attempt_id">，带「计分」的那次即是</span>
          </p>
        </div>

        <div class="hw-scroll">
          <div class="sticker-flat hw-table-wrap">
            <table class="hw-table hw-history-table">
              <thead>
                <tr>
                  <th>次数</th>
                  <th>状态</th>
                  <th>时间</th>
                  <th>用时</th>
                  <th>成绩</th>
                  <th class="col-op">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in entry.attempts.history"
                  :key="item.attempt_id"
                  :class="{ 'is-counted': item.counted }"
                >
                  <td>
                    第 {{ item.attempt_no }} 次
                    <span v-if="item.counted" class="history-flag">计分</span>
                  </td>
                  <td>
                    <span class="hw-status" :class="item.status === 'submitted' ? 'passed' : ''">
                      {{ statusText(item) }}
                    </span>
                  </td>
                  <td class="muted">{{ whenText(item) }}</td>
                  <td class="muted">{{ durationText(item.duration_seconds) || "—" }}</td>
                  <td class="mono">
                    <template v-if="item.status === 'ongoing'">—</template>
                    <template v-else>{{ scoreText(item) }}</template>
                  </td>
                  <td class="col-op">
                    <button
                      v-if="item.status === 'submitted'"
                      class="btn-text hw-challenge"
                      type="button"
                      @click="emit('review', item.attempt_id)"
                    >
                      查看
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>

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
                <table class="hw-table hw-history-table">
                  <tbody>
                    <tr
                      v-for="item in pageData.items"
                      :key="item.attempt_id"
                      :class="{ 'is-counted': item.counted }"
                    >
                      <td>
                        第 {{ item.attempt_no }} 次
                        <span v-if="item.counted" class="history-flag">计分</span>
                      </td>
                      <td>
                        <span
                          class="hw-status"
                          :class="item.status === 'submitted' ? 'passed' : ''"
                        >
                          {{ statusText(item) }}
                        </span>
                      </td>
                      <td class="muted">{{ whenText(item) }}</td>
                      <td class="muted">{{ durationText(item.duration_seconds) || "—" }}</td>
                      <td class="mono">
                        <template v-if="item.status === 'ongoing'">—</template>
                        <template v-else>{{ scoreText(item) }}</template>
                      </td>
                      <td class="col-op">
                        <button
                          v-if="item.status === 'submitted'"
                          class="btn-text hw-challenge"
                          type="button"
                          @click="emit('review', item.attempt_id)"
                        >
                          查看
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
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
    </template>
  </div>
</template>

<style scoped>
/* 看板沿用 exam.css 的令牌（--accent/--mint/--line/...），不另起调色盘。
   .ltag / .btn-text 是 lesson.css 的作用域类，exam-root 下不存在，这里就地补一份。 */

.ltag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.8rem;
  background: var(--mint);
  color: var(--ink);
  white-space: nowrap;
}
.ltag.on-warn {
  background: rgba(185, 133, 47, 0.14);
  color: var(--warn);
}

.hw-head {
  padding: 1.5rem 2rem;
}
.hw-title-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.hw-title {
  margin: 0;
  font-size: 1.35rem;
}
.hw-sub {
  margin: 0.4rem 0 0;
}
.hw-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 0.9rem;
}

.hw-blocked {
  margin-top: 1rem;
}

/* 内容滚动框：高度封顶，超出在框内滚，不把外层页面顶长。
   表头 sticky 吸顶，滚动时列名不丢。滚动条做窄做淡，不抢视线。 */
.hw-scroll {
  max-height: min(62vh, 640px);
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--line-strong) transparent;
}
.hw-scroll::-webkit-scrollbar {
  width: 6px;
}
.hw-scroll::-webkit-scrollbar-thumb {
  background: var(--line-strong);
  border-radius: 999px;
}
.hw-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.hw-tabs {
  display: flex;
  gap: 1.5rem;
  margin: 1.25rem 0 0.75rem;
  border-bottom: 1px solid var(--line);
}
.hw-tab {
  appearance: none;
  background: none;
  border: none;
  padding: 0.5rem 0.25rem;
  font-size: 1rem;
  color: var(--muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.hw-tab.active {
  color: var(--ink);
  font-weight: 600;
  border-bottom-color: var(--accent);
}

.hw-progress {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.9rem 1.25rem;
  transition: box-shadow 0.3s ease;
}
/* 全部通过：进度条从墨绿换成暖金（--warn 令牌），卡片加一圈淡淡的光，
   给一个"这事成了"的收尾反馈，但不弹窗不撒花——作业页不该比成绩页还闹。 */
.hw-progress.done {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--warn) 35%, transparent);
}
.hw-progress.done .hw-progress-bar {
  background: linear-gradient(90deg, var(--accent), var(--warn));
}
.hw-progress.done .hw-progress-num {
  color: var(--warn);
  font-weight: 700;
}
.hw-progress-cheer {
  color: var(--warn);
  font-weight: 700;
  white-space: nowrap;
}
.hw-progress-label {
  font-weight: 600;
  white-space: nowrap;
}
.hw-progress-track {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: var(--mint);
  overflow: hidden;
}
.hw-progress-bar {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.4s ease;
}
.hw-progress-num {
  font-variant-numeric: tabular-nums;
  color: var(--muted);
  white-space: nowrap;
}

.hw-table-wrap {
  margin-top: 1rem;
  padding: 0.25rem 0;
  overflow-x: auto;
}
.hw-scroll .hw-table-wrap {
  margin-top: 0;
}
.hw-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.95rem;
}
.hw-table th {
  text-align: left;
  padding: 0.6rem 1rem;
  color: var(--muted);
  font-weight: 600;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  /* 吸顶表头：滚动时列名钉在框顶，底色盖住行内容 */
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface);
}
.hw-table td {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
  transition: background 0.15s ease;
}
.hw-table tbody tr:hover td {
  background: color-mix(in srgb, var(--mint) 35%, transparent);
}
.hw-table tbody tr.is-counted td {
  background: color-mix(in srgb, var(--mint) 55%, transparent);
}
.hw-table tbody tr:last-child td {
  border-bottom: none;
}
.hw-qname {
  font-weight: 600;
}
.hw-qtags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.hw-status.passed {
  color: var(--accent);
  font-weight: 600;
}
.hw-status.failed {
  color: var(--danger);
  font-weight: 600;
}
.hw-diff {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 600;
  white-space: nowrap;
}
.hw-diff.easy {
  background: var(--mint);
  color: var(--accent);
}
.hw-diff.mid {
  background: rgba(74, 127, 191, 0.14);
  color: #4a7fbf;
}
.hw-diff.hard {
  background: rgba(138, 109, 191, 0.14);
  color: #8a6dbf;
}
.hw-diff.expert {
  background: rgba(185, 92, 80, 0.14);
  color: var(--danger);
}
.hw-challenge {
  appearance: none;
  background: none;
  border: none;
  padding: 0;
  color: var(--accent);
  font-weight: 600;
  cursor: pointer;
}
.hw-challenge:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.hw-foot {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1.25rem;
  flex-wrap: wrap;
}
.hw-foot .hint {
  font-size: 0.88rem;
}
.hw-foot .hint-done {
  color: var(--warn);
  font-weight: 600;
}
.hw-finish {
  /* 与进度条同一抹暖金，首尾呼应 */
  background: linear-gradient(135deg, var(--accent), var(--warn));
  border-color: transparent;
}

.hw-empty {
  padding: 2rem;
  text-align: center;
}
.hw-history {
  padding: 1.25rem;
}
.hw-history-table td {
  white-space: nowrap;
}
.hw-history-table .history-flag {
  margin-left: 6px;
}
.hw-scroll .history-more {
  display: block;
  margin: 0.75rem auto 0.25rem;
  color: var(--accent);
}
.hw-scroll .history-all {
  margin-top: 0.75rem;
}
.hw-scroll .history-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 0.75rem 0 0.25rem;
}
</style>
