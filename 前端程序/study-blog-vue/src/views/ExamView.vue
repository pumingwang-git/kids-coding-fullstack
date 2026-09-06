<script setup>
// /exam/:token 的四态编排：候考 → 须知 → 作答 → 结果。
//
// 状态不存 localStorage：答案在服务器上，刷新后重新拉 entry 就能恢复现场
// （有 ongoing_attempt_id 就直接回作答页）。本地缓存进度只会带来"两边不一致"。
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  fetchEntry,
  fetchAttemptHistory,
  fetchLessonHomeworkEntry,
  fetchLessonHomeworkHistory,
  startAttempt,
  startLessonHomework,
} from "../services/exam";
import ExamLobby from "../components/exam/ExamLobby.vue";
import HomeworkBoard from "../components/exam/HomeworkBoard.vue";
import ExamNotice from "../components/exam/ExamNotice.vue";
import ExamResult from "../components/exam/ExamResult.vue";
import ExamRunner from "../components/exam/ExamRunner.vue";
import ImageLightbox from "../components/exam/ImageLightbox.vue";
import "../styles/exam.css";
import { paperAttemptHelpContext, resetHelpState, setActiveHelpContext, setHelpEnabled } from "../stores/helpContext";

const route = useRoute();
const router = useRouter();
// 入口描述对象是前端对 AttemptSource 的对应抽象：不同入口只在这里说明“如何加载、
// 如何开考、如何看历史、回到哪里、用什么文案”。接入班级测验时新增一个描述对象即可。
const source = computed(() => {
  const lessonId = Number(route.params.lessonId || 0);
  const blockId = Number(route.params.blockId || 0);
  if (lessonId && blockId) {
    const lessonRoute = {
      path: `/learn/${lessonId}`,
      // 回到刚完成的块，并绕过课时详情的短期预取缓存，立刻看到解锁后的进度。
      query: { block: String(blockId), refresh: "1" },
    };
    return {
      showReturnBar: true,
      token: "",
      loadEntry: () => fetchLessonHomeworkEntry(lessonId, blockId),
      start: () => startLessonHomework(lessonId, blockId),
      loadHistory: (params) => fetchLessonHomeworkHistory(lessonId, blockId, params),
      returnLabel: "返回课时，继续学习",
      returnTo: lessonRoute,
      copy: { loading: "正在进入作业…", unavailable: "无法进入作业", returnToCourse: "返回课时" },
    };
  }
  const token = route.params.token || "";
  return {
    showReturnBar: false,
    token,
    loadEntry: () => fetchEntry(token),
    start: () => startAttempt(token),
    loadHistory: (params) => fetchAttemptHistory(token, params),
    returnLabel: "返回考试首页",
    returnTo: "/courses",
    copy: { loading: "正在进入考试…", unavailable: "无法进入考试", returnToCourse: "返回课程" },
  };
});
const historyLoader = (params) => source.value.loadHistory(params);

// 401（会话真死）已收归 App.vue 全局接管（文档17 P2）：auth.js 发 session:expired，
// App.vue 清 session + 跳 /auth?next=...。下面 catch 里 401 直接 return 不显示 dead。

const stage = ref("loading"); // loading / lobby / notice / running / result / dead
const entry = ref(null);
const attemptId = ref(null);
const errorText = ref("");
const busy = ref(false);
// 「开始挑战」锚定的那道题（problem_id_no）。null 表示整卷从头开始。
const anchorProblem = ref(null);
// 课时作业 + 服务端下了题目大纲 → 用题目列表看板代替传统候考页。
const useBoard = computed(
  () => source.value.showReturnBar && (entry.value?.paper?.questions || []).length > 0,
);

// 练习卷 / 作业卷保留闯关式的鼓励与动效；测试、模拟、竞赛卷收敛成考场观感。
const playful = computed(() => ["练习卷", "作业卷"].includes(entry.value?.paper?.paper_type));
const rootClass = computed(() => (playful.value ? "is-playful" : "is-formal"));

/** 候考页历史里"最近一次已交卷"的 attempt id。?review=last 用它直达成绩页。 */
function lastSubmittedAttempt(payload) {
  const summary = payload?.attempts?.summary || {};
  if (summary.counted_attempt_id) return summary.counted_attempt_id;
  const done = (payload?.attempts?.history || []).filter((item) => item.status === "submitted");
  return done.length ? done[done.length - 1].attempt_id : null;
}

async function loadEntry({ resume = true, review = false, reviewId = null } = {}) {
  try {
    const payload = await source.value.loadEntry();
    entry.value = payload;
    setHelpEnabled(payload.help_enabled !== false);
    // 「查看成绩」两种直达：reviewId 指定某一次；review=true 取最近一次已交卷。
    // 都不让学生先过一遍候考页再自己找回看入口。
    const target = reviewId ?? (review ? lastSubmittedAttempt(payload) : null);
    if (target) {
      attemptId.value = target;
      stage.value = "result";
      return;
    }
    if (resume && payload.attempts.ongoing_attempt_id) {
      attemptId.value = payload.attempts.ongoing_attempt_id;
      // 续做也尊重锚点：点了某题的「继续挑战」，续上卷子就该落在那题。
      if (typeof route.query.anchor === "string") anchorProblem.value = route.query.anchor;
      stage.value = "running";
    } else {
      stage.value = "lobby";
      // 课时页内嵌看板的「开始挑战」：autostart=1 直接开考，不再过一遍本页看板。
      if (autostartPending && payload.can_start) {
        autostartPending = false;
        onStart(typeof route.query.anchor === "string" ? route.query.anchor : null);
      }
    }
  } catch (error) {
    if (error?.status === 401) return; // 全局 session:expired 已接管
    errorText.value = error.message;
    stage.value = "dead";
  }
}

// autostart 只消费一次：开考失败回到候考页时不能再自动点第二次。
let autostartPending = false;

function onStart(problemIdNo = null) {
  anchorProblem.value = problemIdNo;
  // 有须知就先过须知页；没有就直奔开考。
  if (entry.value.link.notice?.trim() && !entry.value.attempts.ongoing_attempt_id) {
    stage.value = "notice";
    return;
  }
  begin();
}

async function begin() {
  busy.value = true;
  errorText.value = "";
  try {
    const payload = await source.value.start();
    attemptId.value = payload.attempt_id;
    stage.value = "running";
  } catch (error) {
    if (error?.status === 401) return; // 全局 session:expired 已接管
    errorText.value = error.message;
    // 开考被拒（时间没到 / 次数用完）不是致命错误，回候考页把原因显示出来。
    await loadEntry({ resume: false });
    stage.value = entry.value ? "lobby" : "dead";
  } finally {
    busy.value = false;
  }
}

function onSubmitted(id) {
  attemptId.value = id;
  errorText.value = "";
  stage.value = "result";
}

function onExpired() {
  stage.value = "result";
}

function onRunnerError(error) {
  if (error?.status === 401) return; // 全局 session:expired 已接管
  errorText.value = error?.message || "作答过程中发生错误。";
}

function onCurrentQuestion(question) {
  if (!source.value.showReturnBar || !question?.problem_id_no || !attemptId.value) return;
  setActiveHelpContext(paperAttemptHelpContext(attemptId.value, question.problem_id_no));
}

/** 成绩页的主行动。课时作业回课时，独立考试链接回自己的候考页——两种入口，两个终点。 */
async function onBack() {
  errorText.value = "";
  if (source.value.showReturnBar) {
    await router.push(source.value.returnTo);
    return;
  }
  await loadEntry({ resume: false });
}

onMounted(() => {
  // review=last → 最近一次已交卷；review=<数字> → 内嵌看板「作答记录」点「查看」直达那次。
  const reviewQuery = route.query.review;
  const reviewId = /^\d+$/.test(String(reviewQuery)) ? Number(reviewQuery) : null;
  autostartPending = route.query.autostart === "1";
  loadEntry({ review: reviewQuery === "last", reviewId });
});

onBeforeUnmount(() => {
  resetHelpState();
});
</script>

<template>
  <div class="exam-root qz" :class="[rootClass, { 'has-return-bar': source.showReturnBar }]">
    <header v-if="source.showReturnBar" class="lesson-exam-bar">
      <RouterLink class="lesson-return" :to="source.returnTo">返回课时</RouterLink>
    </header>

    <!-- 错误常驻在四态之外。以前 errorText 只在 lobby / dead 两个分支里渲染，
         于是**作答页与成绩页的任何失败都是不可见的**：点了交卷，确认框一关，
         界面纹丝不动，学生只会以为自己没点中，然后再点一次。 -->
    <div v-if="errorText && stage !== 'lobby' && stage !== 'dead'" class="exam-narrow exam-alert">
      <div class="error-box">{{ errorText }}</div>
    </div>

    <p v-if="stage === 'loading'" class="exam-narrow muted">{{ source.copy.loading }}</p>

    <div v-else-if="stage === 'dead'" class="exam-narrow">
      <div class="sticker" style="padding: 2rem">
        <h1 style="margin-top: 0">{{ source.copy.unavailable }}</h1>
        <p>{{ errorText }}</p>
        <RouterLink
          class="btn-chunky"
          :to="source.returnTo"
          style="display: inline-block; text-decoration: none"
        >
          {{ source.copy.returnToCourse }}
        </RouterLink>
      </div>
    </div>

    <template v-else-if="stage === 'lobby'">
      <div v-if="errorText" class="exam-narrow" style="padding-bottom: 0">
        <div class="error-box">{{ errorText }}</div>
      </div>
      <HomeworkBoard
        v-if="useBoard"
        :entry="entry"
        :history-loader="historyLoader"
        :busy="busy"
        @start="onStart"
        @review="onSubmitted"
        @back="router.push(source.returnTo)"
      />
      <ExamLobby
        v-else
        :entry="entry"
        :token="source.token"
        :history-loader="historyLoader"
        :busy="busy"
        @start="onStart"
        @review="onSubmitted"
      />
    </template>

    <ExamNotice
      v-else-if="stage === 'notice'"
      :notice="entry.link.notice"
      :ack-required="entry.link.notice_ack_required"
      :busy="busy"
      @accept="begin"
      @back="stage = 'lobby'"
    />

    <ExamRunner
      v-else-if="stage === 'running'"
      :attempt-id="attemptId"
      :playful="playful"
      :initial-problem="anchorProblem"
      @submitted="onSubmitted"
      @expired="onExpired"
      @error="onRunnerError"
      @current-change="onCurrentQuestion"
    />

    <ExamResult
      v-else-if="stage === 'result'"
      :attempt-id="attemptId"
      :playful="playful"
      :return-label="source.returnLabel"
      @back="onBack"
      @error="onRunnerError"
    />

    <!-- 弹窗的专用挂载层。ExamModal 的 Portal 曾经直接指到 .exam-root，传送门的
         节点和上面 v-if 分支切换插拔的节点混在同一个容器里：交卷瞬间「确认框关闭」
         与「作答页 → 结果页」落在同一次渲染冲刷里，Vue 拿着被传送门挪走的锚点
         insertBefore 直接抛 NotFoundError，整页白屏（2026-08-07 实测复现）。
         这层 div 是 ExamView 模板里的静态节点，任何阶段切换都不会动它，
         传送门的挂载/卸载只在它内部发生，与分支切换互不相干。 -->
    <div class="exam-modal-layer"></div>

    <!-- 题干配图的大图查看器。跟上面那层挂载层一样是模板里的静态节点、四个阶段共用一个，
         由 stores/lightbox 的单例状态驱动——每个 MarkdownBody 自带一层遮罩既浪费，
         也会叠出两层遮罩。z-index 200，盖在弹窗（100/101）之上。 -->
    <ImageLightbox />
  </div>
</template>
