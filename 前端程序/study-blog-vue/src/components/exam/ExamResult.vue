<script setup>
// 结果页。能看到什么完全由服务端决定：show_score / show_analysis / feedback_mode
// 已经在服务端把字段裁掉了，这里只判断"键在不在"，绝不自己再实现一套隐藏逻辑——
// 前端隐藏等于没隐藏，F12 一开就全暴露。
//
// 布局：顶部成绩卡 → 「答题详情 / 成绩排名」两个页签。内容全部平铺曾被评为散乱，
// 页签化之后首屏只聚焦一件事。打印走浏览器打印（另存为 PDF）：屏上内容与成绩单
// 是两套 DOM（.screen-only / .print-only），@media print 切换，成绩单不携带
// 参考答案与解析——它是成绩凭证，不是答案纸。
import { computed, defineAsyncComponent, nextTick, onMounted, ref } from "vue";
import { QUESTION_TYPE_TEXT, fetchLeaderboard, fetchResult } from "../../services/exam";
import { isCompileOnly } from "../../services/verdict";
import { session } from "../../stores/session";
import MarkdownBody from "./MarkdownBody.vue";
import SubmissionDetail from "./SubmissionDetail.vue";
// 解析视频拖着 video.js（600KB+），异步加载：只有题目配了解析视频且开放时才拉。
const VideoPlayer = defineAsyncComponent(() => import("../VideoPlayer.vue"));

const props = defineProps({
  attemptId: { type: Number, required: true },
  playful: { type: Boolean, default: true },
  // 主行动按钮的文案由调用方定：从课时作业进来的人要回课时，从考试链接进来的人
  // 回考试首页。组件自己去读路由就等于把两个壳焊死在一起。
  returnLabel: { type: String, default: "返回考试首页" },
  // 排名是否可见由服务端来源策略决定。
});
const emit = defineEmits(["back", "error"]);

const loading = ref(true);
const data = ref(null);
// 成绩拉不回来时的兜底。以前这里只 emit("error") 就完了，而模板是
// v-if="loading" / v-else-if="data" —— 两个都假的时候**整页什么都不渲染**：
// 学生交完卷看到一片空白，连个返回按钮都没有。
const loadError = ref("");
// 排行榜独立于成绩加载：它挂了（或成绩未公开被 403）不该拖垮成绩页本身。
const board = ref(null);
const tab = ref("detail"); // detail = 答题详情 / board = 成绩排名

const toast = ref("");
let toastTimer = null;
function showToast(message) {
  toast.value = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.value = ""), 2000);
}

const scored = computed(
  () => data.value?.show_score && "total_score" in (data.value.attempt || {}),
);
const passed = computed(() => data.value?.attempt?.passed);
const hasBoard = computed(() => Boolean(board.value?.entries?.length));
const reviewFilter = ref("all");
const questions = computed(() => data.value?.questions || []);

function isUnanswered(item) {
  if (item.type === "fill") return !myBlanks(item).some((blank) => blank.text);
  if (item.type === "programming") return !item.last_submission;
  const picked = item.answer?.picked;
  return Array.isArray(picked) ? !picked.length : !picked;
}

function needsReview(item) {
  return item.is_correct === false || item.judge_status === "failed";
}

const wrongQuestions = computed(() => questions.value.filter(needsReview));
const unansweredQuestions = computed(() => questions.value.filter(isUnanswered));
const pendingQuestions = computed(() =>
  questions.value.filter((item) => item.judge_status === "failed" || item.score == null),
);
const filteredQuestions = computed(() => {
  if (reviewFilter.value === "wrong") return wrongQuestions.value;
  if (reviewFilter.value === "unanswered") return unansweredQuestions.value;
  if (reviewFilter.value === "pending") return pendingQuestions.value;
  return questions.value;
});
const reviewActionLabel = computed(() =>
  wrongQuestions.value.length ? "复习错题" : props.returnLabel,
);

function statusText(item) {
  if (item.judge_status === "failed") return "待复核";
  if (item.is_correct === false) return "需复习";
  if (item.is_correct === true) return "正确";
  if (item.score == null) return "待评阅";
  return "已提交";
}

function focusQuestion(item) {
  reviewFilter.value = "all";
  nextTick(() => document.getElementById(`result-question-${item.problem_id_no}`)?.focus());
}

function onTabKey(event) {
  const next = event.key === "ArrowRight" || event.key === "End" ? "board" : "detail";
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  tab.value = next;
  nextTick(() => document.getElementById(`result-tab-${next}`)?.focus());
}

function durationText(seconds) {
  if (seconds == null) return "—";
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes} 分 ${seconds % 60} 秒` : `${seconds} 秒`;
}

function submittedText(iso) {
  return iso ? new Date(iso).toLocaleString("zh-CN", { hour12: false }) : "—";
}

// ---------- 「我的答案」----------
// 服务端一直在下发 item.answer（学员自己存的那份），只是从来没渲染过。
// 结果页不重排选项，而 label 与选项正文的配对在洗牌前就定死了，所以这里按 label
// 取正文，学员当时点的 B 就是这里的 B。

/** label → "B. print()"。选项缺失（题被改过）时退回只显示 label。 */
function optionText(item, label) {
  const option = (item.options || []).find((entry) => entry.label === label);
  return option ? `${label}. ${option.content}` : label;
}

/** 客观题「我的答案」的文本；未作答返回 null，由模板显示成灰字。 */
function myChoiceText(item) {
  const picked = item.answer?.picked;
  const labels = Array.isArray(picked) ? picked : picked ? [picked] : [];
  if (!labels.length) return null;
  return labels.map((label) => optionText(item, label)).join("、");
}

/** 填空「我的答案」：[{ key, 序号, 我填的, 对不对 }]，顺序按题面空位顺序。 */
function myBlanks(item) {
  const keys = item.blank_keys || (item.correct?.blanks || []).map((blank) => blank.blank_key);
  const mine = item.answer?.blanks || {};
  // detail.blanks 是判分明细，成绩不公开时整个 detail 都不下发——那时不标对错。
  const marks = new Map(
    (item.detail?.blanks || []).map((blank) => [blank.blank_key, blank.correct]),
  );
  return keys.map((key, index) => ({
    key,
    index: index + 1,
    text: (mine[key] ?? "").trim(),
    correct: marks.has(key) ? marks.get(key) : null,
  }));
}

/** 参考答案：填空按空位逐条给，不再把多个空糊成 "a / b"。 */
function correctBlankText(item, key) {
  return (item.correct?.blanks || []).find((blank) => blank.blank_key === key)?.answer ?? "";
}

// 导出期间纸张走「出血」模式：白边由 .transcript 自己的 padding 给，不再留给浏览器。
const exporting = ref(false);
const transcriptMode = ref("summary");
const transcriptPageEstimate = computed(() =>
  Math.max(1, Math.ceil(questions.value.length / 18) + 1),
);

/** 导出成绩单：交给浏览器打印对话框，目标选「另存为 PDF」即可。
 *
 * 浏览器的页眉页脚（日期 / 网页标题 / URL / 页码）画在纸张的页边距里，成绩单顶上
 * 因此会多出两行与凭证无关的字——学生得自己去打印对话框里取消勾选「页眉和页脚」。
 * 把 @page 的边距归零就没它们的位置了，白边改由成绩单自己的 padding 给。
 *
 * @page 只能全局生效（CSS 里没有按选择器限定它的写法），而 exam.css 是全局样式，
 * 离开 /exam 也还挂在文档上，写死在样式表里会连带把博客页的打印边距一起清掉。
 * 所以这条规则临时注入、打印结束就撤。 */
async function exportTranscript(mode = "summary") {
  const page = document.createElement("style");
  page.textContent = "@page { size: A4; margin: 0 }";
  document.head.append(page);
  transcriptMode.value = mode;
  exporting.value = true;
  const restore = () => {
    page.remove();
    exporting.value = false;
    window.removeEventListener("afterprint", restore);
  };
  window.addEventListener("afterprint", restore);
  // 类名要先落到 DOM 上再唤起打印，否则第一页排的还是没加白边的版式。
  await nextTick();
  window.print();
}

async function loadResult() {
  loading.value = true;
  loadError.value = "";
  try {
    data.value = await fetchResult(props.attemptId);
    reviewFilter.value = wrongQuestions.value.length ? "wrong" : "all";
  } catch (error) {
    loadError.value = error?.message || "成绩加载失败。";
    emit("error", error);
  } finally {
    loading.value = false;
  }
  // 成绩不公开的考试没有排行榜（服务端 403），请求前就按 show_score 拦一道。
  if (data.value?.leaderboard_enabled && data.value?.show_score) {
    try {
      board.value = await fetchLeaderboard(props.attemptId);
    } catch {
      board.value = null;
    }
  }
}

onMounted(loadResult);
</script>

<template>
  <div class="exam-narrow">
    <div class="screen-only">
      <p v-if="loading" class="muted">正在加载成绩…</p>

      <!-- 加载失败必须有话说、有出口。卷已经交上去了，成绩在服务端好好的，
           这里只是没取回来——所以文案要写明"不影响成绩"，别让人以为白考了。 -->
      <div v-else-if="!data" class="sticker" style="padding: 2rem">
        <h1 style="margin-top: 0">成绩暂时没能取回来</h1>
        <p>{{ loadError || "请稍后重试。" }}</p>
        <p class="muted">你的答卷已经提交，成绩不受影响。</p>
        <div style="display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1rem">
          <button class="btn-chunky btn-primary" type="button" @click="loadResult">重试</button>
          <button class="btn-chunky" type="button" @click="emit('back')">{{ returnLabel }}</button>
        </div>
      </div>

      <template v-else>
        <div class="sticker" style="padding: 2rem; text-align: center">
          <h1 style="margin-top: 0">
            {{ playful ? "交卷完成，辛苦啦！" : "已交卷" }}
          </h1>
          <p class="muted" style="margin-top: 0">
            {{ data.paper.title }} ·
            {{ data.attempt.submit_kind === "manual" ? "手动交卷" : "系统收卷" }}
          </p>

          <div v-if="scored" style="margin: 1.5rem 0">
            <div style="font-size: 3rem; font-weight: 800; line-height: 1">
              {{ data.attempt.total_score }}
              <span class="muted" style="font-size: 1rem">/ {{ data.paper.total_score }}</span>
            </div>
            <p v-if="passed !== undefined" style="font-weight: 700; margin: 0.5rem 0 0">
              {{ passed ? "已达到及格线 🎉" : "未达到及格线，再接再厉" }}
            </p>
          </div>
          <div v-else class="notice-box result-release-note" style="margin: 1.5rem 0" role="status">
            <strong>答卷已保存，成绩暂未公布。</strong>
            <p>老师批改或到达公布条件后会显示成绩；当前可查看的答案与解析以本页内容为准。</p>
          </div>

          <p class="muted">用时 {{ durationText(data.attempt.duration_seconds) }}</p>
          <!-- 交完卷的下一步是"回去继续学"，不是"回到这张卷的候考页"。
               去向由调用方给（课时作业 → 课时并停在刚做完的那一块）。 -->
          <button
            class="btn-chunky btn-primary"
            type="button"
            style="margin-top: 1rem"
            @click="wrongQuestions.length ? (reviewFilter = 'wrong') : emit('back')"
          >
            {{ reviewActionLabel }}
          </button>
        </div>

        <section
          v-if="questions.length"
          class="result-review-summary"
          aria-labelledby="result-review-title"
        >
          <div>
            <h2 id="result-review-title">学习回顾</h2>
            <p class="muted">
              共 {{ questions.length }} 题
              <template v-if="wrongQuestions.length">
                · {{ wrongQuestions.length }} 题需复习</template
              >
              <template v-if="unansweredQuestions.length">
                · {{ unansweredQuestions.length }} 题未作答</template
              >
              <template v-if="pendingQuestions.length">
                · {{ pendingQuestions.length }} 题待评阅或复核</template
              >
            </p>
          </div>
          <div class="result-filter-group" aria-label="筛选答题详情">
            <button
              type="button"
              :class="{ 'is-active': reviewFilter === 'all' }"
              :aria-pressed="reviewFilter === 'all'"
              @click="reviewFilter = 'all'"
            >
              全部 {{ questions.length }}
            </button>
            <button
              v-if="wrongQuestions.length"
              type="button"
              :class="{ 'is-active': reviewFilter === 'wrong' }"
              :aria-pressed="reviewFilter === 'wrong'"
              @click="reviewFilter = 'wrong'"
            >
              需复习 {{ wrongQuestions.length }}
            </button>
            <button
              v-if="unansweredQuestions.length"
              type="button"
              :class="{ 'is-active': reviewFilter === 'unanswered' }"
              :aria-pressed="reviewFilter === 'unanswered'"
              @click="reviewFilter = 'unanswered'"
            >
              未作答 {{ unansweredQuestions.length }}
            </button>
            <button
              v-if="pendingQuestions.length"
              type="button"
              :class="{ 'is-active': reviewFilter === 'pending' }"
              :aria-pressed="reviewFilter === 'pending'"
              @click="reviewFilter = 'pending'"
            >
              待处理 {{ pendingQuestions.length }}
            </button>
          </div>
          <div class="result-question-nav" aria-label="题号导航">
            <button
              v-for="(item, index) in questions"
              :key="item.problem_id_no"
              type="button"
              :class="{
                'is-review': needsReview(item),
                'is-pending': item.judge_status === 'failed' || item.score == null,
              }"
              :aria-label="`第 ${index + 1} 题，${statusText(item)}`"
              @click="focusQuestion(item)"
            >
              {{ index + 1 }}
            </button>
          </div>
        </section>

        <!-- 页签：答题详情常开；成绩排名只在榜单真的存在时出现。 -->
        <div v-if="hasBoard" class="result-tabs" role="tablist">
          <button
            id="result-tab-detail"
            type="button"
            role="tab"
            aria-controls="result-panel-detail"
            :aria-selected="tab === 'detail'"
            :class="{ 'is-active': tab === 'detail' }"
            @click="tab = 'detail'"
            @keydown="onTabKey"
          >
            答题详情
          </button>
          <button
            id="result-tab-board"
            type="button"
            role="tab"
            aria-controls="result-panel-board"
            :aria-selected="tab === 'board'"
            :class="{ 'is-active': tab === 'board' }"
            @click="tab = 'board'"
            @keydown="onTabKey"
          >
            成绩排名
          </button>
        </div>

        <div
          id="result-panel-detail"
          role="tabpanel"
          aria-labelledby="result-tab-detail"
          tabindex="0"
          v-show="tab === 'detail'"
        >
          <div v-if="scored" class="detail-toolbar">
            <div class="transcript-actions">
              <div>
                <strong>导出成绩单</strong>
                <p v-if="questions.length > 18" class="muted">
                  完整明细约 {{ transcriptPageEstimate }} 页；摘要仅保留成绩凭证。
                </p>
              </div>
              <div>
                <button
                  class="btn-chunky btn-sm"
                  type="button"
                  @click="exportTranscript('summary')"
                >
                  导出摘要 PDF
                </button>
                <button class="btn-chunky btn-sm" type="button" @click="exportTranscript('detail')">
                  导出完整明细 PDF
                </button>
              </div>
            </div>
          </div>

          <div
            v-for="item in filteredQuestions"
            :key="item.problem_id_no"
            :id="`result-question-${item.problem_id_no}`"
            class="sticker-flat result-question-card"
            tabindex="-1"
            style="padding: 1.25rem; margin-top: 1.25rem"
          >
            <div class="question-meta">
              <span class="q-badge" :class="{ 'is-wrong': item.is_correct === false }">
                {{ questions.indexOf(item) + 1 }}
              </span>
              <span class="q-type">{{ QUESTION_TYPE_TEXT[item.type] || "题目" }}</span>
              <span class="result-question-status" :class="{ 'is-review': needsReview(item) }">{{
                statusText(item)
              }}</span>
              <span v-if="'score' in item" class="q-score">
                {{ item.score == null ? "待定" : item.score }} / {{ item.full_score }} 分
              </span>
            </div>

            <div v-if="item.judge_status === 'failed'" class="error-box">
              这道题判题异常，成绩未计入总分，请联系老师复核。
            </div>

            <MarkdownBody v-if="item.stem" :source="item.stem" />

            <!-- 我的答案。编程题不进这里——它的"我的答案"是代码，由下面的
                 SubmissionDetail 连带逐测试点一起给。 -->
            <div v-if="item.type === 'fill'" class="answer-box">
              <div class="answer-line">
                <span class="answer-tag">我的答案</span>
                <div class="blank-answers">
                  <span
                    v-for="blank in myBlanks(item)"
                    :key="blank.key"
                    class="blank-chip"
                    :class="{
                      'is-wrong': blank.correct === false,
                      'is-right': blank.correct === true,
                    }"
                  >
                    <i>空 {{ blank.index }}</i>
                    <template v-if="blank.text">{{ blank.text }}</template>
                    <em v-else>未作答</em>
                  </span>
                </div>
              </div>
              <div v-if="item.correct" class="answer-line">
                <span class="answer-tag is-key">参考答案</span>
                <div class="blank-answers">
                  <span v-for="blank in myBlanks(item)" :key="blank.key" class="blank-chip">
                    <i>空 {{ blank.index }}</i
                    >{{ correctBlankText(item, blank.key) }}
                  </span>
                </div>
              </div>
            </div>

            <div v-else-if="item.type && item.type !== 'programming'" class="answer-box">
              <div class="answer-line">
                <span class="answer-tag">我的答案</span>
                <span :class="{ 'answer-wrong': item.is_correct === false }">
                  {{ myChoiceText(item) || "未作答" }}
                </span>
              </div>
              <div v-if="item.correct?.labels" class="answer-line">
                <span class="answer-tag is-key">参考答案</span>
                <span>{{
                  item.correct.labels.map((label) => optionText(item, label)).join("、")
                }}</span>
              </div>
            </div>

            <!-- 题被删掉这类情况下 type 都没有，参考答案仍要能露出来 -->
            <div v-else-if="item.correct" class="notice-box" style="margin-top: 1rem">
              <strong>参考答案：</strong>
              <span v-if="item.correct.labels">{{ item.correct.labels.join("、") }}</span>
            </div>

            <div v-if="item.analysis" style="margin-top: 1rem">
              <strong>解析</strong>
              <MarkdownBody :source="item.analysis" />
            </div>

            <!-- 解析视频：服务端在 show_analysis 可见时下发 analysis_video（available/
                 processing），播放地址走独立门控端点（本人 + 已交卷 + 解析可见）。 -->
            <div v-if="item.analysis_video" class="result-analysis-video" style="margin-top: 1rem">
              <strong>教师解析视频</strong>
              <VideoPlayer
                v-if="item.analysis_video.available"
                :lesson-id="0"
                :play-path="item.analysis_video.play_path"
              />
              <p v-else-if="item.analysis_video.processing" class="muted">
                解析视频仍在处理中，请稍后再看。
              </p>
            </div>

            <!-- 编程题：交卷后回看自己提交的代码与逐测试点详情，和作答页提交记录
                 用同一个组件——两处各写一套，迟早出现口径对不上的错觉。 -->
            <div v-if="item.last_submission" style="margin-top: 1rem">
              <SubmissionDetail
                :submission="item.last_submission"
                :compile-only="isCompileOnly(item)"
                @copied="showToast"
              />
            </div>
          </div>
        </div>

        <div
          id="result-panel-board"
          role="tabpanel"
          aria-labelledby="result-tab-board"
          tabindex="0"
          v-show="tab === 'board'"
          v-if="hasBoard"
          class="sticker-flat"
          style="padding: 1.25rem; margin-top: 1.25rem"
        >
          <h2 style="margin-top: 0; font-size: 1.05rem">
            成绩排名
            <span class="muted" style="font-weight: 400"
              >{{ board.participant_count }} 人已交卷</span
            >
          </h2>
          <div
            v-for="entry in board.entries"
            :key="entry.username"
            class="board-row"
            :class="{ 'is-me': board.me && entry.username === board.me.username }"
          >
            <span class="board-rank" :data-rank="entry.rank">{{ entry.rank }}</span>
            <span class="board-name">{{ entry.username }}</span>
            <span class="board-score"
              ><strong>{{ entry.total_score }}</strong> 分</span
            >
            <span class="board-duration muted">{{ durationText(entry.duration_seconds) }}</span>
          </div>
          <p v-if="board.me" class="muted" style="margin: 0.75rem 0 0">
            你的排名：第 {{ board.me.rank }} / {{ board.participant_count }} 名
          </p>
        </div>

        <div v-if="tab === 'detail'" class="result-completion">
          <p>已完成本次作业回顾。</p>
          <button class="btn-chunky btn-primary" type="button" @click="emit('back')">
            {{ returnLabel }}
          </button>
        </div>
      </template>
    </div>

    <!-- 打印专用成绩单：屏上永不显示，window.print() 时与 .screen-only 互换。
         只放成绩凭证信息；参考答案、解析、代码一个都不进——它是给学生留档的
         成绩单，不是答案纸。 -->
    <div v-if="data && scored" class="print-only transcript" :class="{ 'is-bleed': exporting }">
      <h1>考试成绩单</h1>
      <table class="transcript-meta">
        <tbody>
          <tr>
            <th>试卷</th>
            <td>{{ data.paper.title }}</td>
            <th>考生</th>
            <td>{{ session.user?.username || "—" }}</td>
          </tr>
          <tr>
            <th>成绩</th>
            <td>{{ data.attempt.total_score }} / {{ data.paper.total_score }} 分</td>
            <th>用时</th>
            <td>{{ durationText(data.attempt.duration_seconds) }}</td>
          </tr>
          <tr>
            <th>交卷时间</th>
            <td>{{ submittedText(data.attempt.submitted_at) }}</td>
            <th>排名</th>
            <td>
              {{ board?.me ? `第 ${board.me.rank} / ${board.participant_count} 名` : "—" }}
            </td>
          </tr>
        </tbody>
      </table>

      <table v-if="transcriptMode === 'detail'" class="transcript-detail">
        <thead>
          <tr>
            <th>题号</th>
            <th>题型</th>
            <th>得分</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in data.questions" :key="item.problem_id_no">
            <td>{{ index + 1 }}</td>
            <td>{{ QUESTION_TYPE_TEXT[item.type] || "题目" }}</td>
            <td>
              <template v-if="item.judge_status === 'failed'">判题异常，待复核</template>
              <template v-else-if="'score' in item">
                {{ item.score == null ? "待定" : `${item.score} / ${item.full_score} 分` }}
              </template>
              <template v-else>—</template>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="transcript-foot">本成绩单由系统生成，仅供留档参考。</p>
    </div>

    <div v-if="toast" class="result-toast">{{ toast }}</div>
  </div>
</template>
