<script setup>
// 作答页外壳：顶栏（倒计时 / 保存状态）+ 题卡侧栏 + 单题主区。
//
// 时间与分数都不在这里判定：倒计时只是显示，归零后调 submit 让服务端决定
// submit_kind；任何接口返回 409 都意味着服务端已经封卷，直接跳结果页。
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { createAutosave } from "../../composables/useAutosave";
import { createExamClock, formatDuration } from "../../composables/useExamClock";
import {
  QUESTION_TYPE_TEXT,
  fetchAttempt,
  fetchSubmissions,
  runCodeAndWait,
  saveAnswer,
  submitAttempt,
} from "../../services/exam";
import { isCompileOnly, metricText, verdictOf } from "../../services/verdict";
import ConfirmDialog from "./ConfirmDialog.vue";
import ExamModal from "./ExamModal.vue";
import ExamSidebar from "./ExamSidebar.vue";
import MarkdownBody from "./MarkdownBody.vue";
import QuestionChoice from "./QuestionChoice.vue";
import QuestionFill from "./QuestionFill.vue";
import SubmissionDetail from "./SubmissionDetail.vue";

// CodeMirror 有 300 多 KB，而多数试卷根本没有编程题——切到编程题时才拉。
const QuestionCoding = defineAsyncComponent(() => import("./QuestionCoding.vue"));

const props = defineProps({
  attemptId: { type: Number, required: true },
  playful: { type: Boolean, default: true },
  // 看板「开始挑战」锚定的题目（problem_id_no）。题目可能被乱序，锚点按编号找，
  // 不按看板上的序号找——看板顺序是卷面顺序，作答顺序是这次 attempt 的乱序结果。
  initialProblem: { type: String, default: "" },
});
const emit = defineEmits(["submitted", "expired", "error", "current-change"]);

const loading = ref(true);
const data = ref(null);
const answers = ref({}); // problem_id_no -> answer 对象
const currentIndex = ref(0);
const remaining = ref(null);
const toasts = ref([]);
const judging = ref(false);
const submitting = ref(false);
const confirmOpen = ref(false);
// 交卷失败必须**就地**看得见。以前失败只往上 emit("error")，而 ExamView 把它塞进一个
// 只在候考页渲染的 errorText —— 作答页什么都不显示：确认框一关，界面纹丝不动，
// 学生只会以为自己没点中，然后一遍遍地点。
const submitError = ref("");
// 超时自动收卷失败后的重试。倒计时的 onExpire 有 expired 闩、只触发一次
// （useExamClock.js:61），不自己排重试的话，一次失败就把人永远卡在 00:00 的页面上。
const AUTO_RETRY_MS = 5000;
const AUTO_RETRY_MAX = 3;
let autoRetries = 0;
let autoRetryTimer = null;
// 标记题只活在这一次作答的内存里：服务端没有这个字段，而"回头再看哪几题"是
// 临时的注意力管理，不是要留档的作答数据。刷新丢掉可以接受，编一个存储位不行。
const marked = ref(new Set());

// 编程题的提交记录。按题缓存，切回同一题不必重拉；每次提交判题后自增一条。
const submissions = ref({}); // problem_id_no -> 提交列表
const submissionMeta = ref({}); // problem_id_no -> { total, page, size }
const historyOpen = ref(false);
const detail = ref(null); // 正在看详情的那次提交

// 在途的「提交判题」。交卷前要拿它拦一下：判题跑完时若已封卷，成绩就不再计入
// （服务端有意为之——改一份已封存的成绩比丢一次提交更糟），所以得先告诉学员。
const pendingJudges = ref(new Set());
// 这个 controller 跟着 ExamRunner 的寿命走，而不是跟着编程题工作区。
// 工作区一切题就销毁，但计分的提交不能因为"学员翻到别的题"就断了跟踪。
const runnerAbort = new AbortController();

function trackJudge(current) {
  const next = new Set(pendingJudges.value);
  if (current.done) next.delete(current.id);
  else next.add(current.id);
  pendingJudges.value = next;
}

let clock = null;
let timer = null;

const questions = computed(() => data.value?.questions || []);
const current = computed(() => questions.value[currentIndex.value] || null);
watch(current, (question) => {
  if (question) emit("current-change", question);
}, { immediate: true });
const answeredKeys = computed(
  () =>
    new Set(
      Object.entries(answers.value)
        .filter(([, value]) => isAnswered(value))
        .map(([key]) => key),
    ),
);
const unanswered = computed(() =>
  questions.value
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => !answeredKeys.value.has(item.problem_id_no))
    .map(({ index }) => index + 1),
);
// 百题卷全列出来会把弹窗撑成一整屏，超过 12 个就折叠。
const unansweredText = computed(() => {
  const list = unanswered.value;
  if (list.length > 12)
    return `还有 ${list.length} 题未作答（第 ${list.slice(0, 12).join("、")}… 题），交卷后将无法修改。`;
  return `第 ${list.join("、")} 题还没有作答，交卷后将无法修改。`;
});
const clockText = computed(() =>
  remaining.value === null ? "不限时" : formatDuration(remaining.value),
);
const urgent = computed(() => remaining.value !== null && remaining.value <= 5 * 60 * 1000);
const isWorkspace = computed(() => current.value?.type === "programming" && !current.value.missing);
const currentMarked = computed(
  () => !!current.value && marked.value.has(current.value.problem_id_no),
);
const currentSubmissions = computed(
  () => (current.value && submissions.value[current.value.problem_id_no]) || [],
);
const currentSubmissionMeta = computed(
  () =>
    (current.value && submissionMeta.value[current.value.problem_id_no]) || {
      total: 0,
      page: 1,
      size: 20,
    },
);
const submissionPageCount = computed(() =>
  Math.max(1, Math.ceil(currentSubmissionMeta.value.total / currentSubmissionMeta.value.size)),
);

async function loadSubmissionPage(question, page = 1) {
  if (!question) return;
  const payload = await fetchSubmissions(props.attemptId, question.problem_id_no, {
    page,
    size: 20,
  });
  submissions.value = { ...submissions.value, [question.problem_id_no]: payload.submissions || [] };
  submissionMeta.value = {
    ...submissionMeta.value,
    [question.problem_id_no]: {
      total: payload.total || 0,
      page: payload.page || page,
      size: payload.size || 20,
    },
  };
}

function toggleMark() {
  if (!current.value) return;
  const next = new Set(marked.value);
  const key = current.value.problem_id_no;
  if (next.has(key)) next.delete(key);
  else next.add(key);
  marked.value = next;
}

async function openHistory() {
  const key = current.value.problem_id_no;
  try {
    await loadSubmissionPage(current.value, 1);
    historyOpen.value = true;
  } catch (error) {
    if (error?.status === 409) handleFatal(error);
    else pushToast(error.message);
  }
}

function openDetail(submission) {
  detail.value = submission;
  historyOpen.value = false;
}

function isAnswered(answer) {
  if (!answer) return false;
  if (answer.type === "multi_choice") return (answer.picked || []).length > 0;
  if (answer.type === "fill")
    return Object.values(answer.blanks || {}).some((item) => String(item).trim());
  if (answer.type === "programming") return Boolean(answer.submission_id);
  return Boolean(answer.picked);
}

const autosave = createAutosave({
  save: (problemIdNo, answer) => saveAnswer(props.attemptId, problemIdNo, answer),
});

// 「已保存 23:26:41」比光秃秃的「已保存」更能让人放心继续做题。时间戳留在这里而不是
// 塞进 useAutosave——那个模块被测试钉住了形状，为一行文案改它不划算。
const savedAt = ref("");
watch(autosave.status, (value) => {
  if (value === "saved") savedAt.value = new Date().toTimeString().slice(0, 8);
});
const saveText = computed(() => {
  if (autosave.status.value === "saving") return "保存中…";
  if (autosave.status.value === "error") return "保存失败，请检查网络";
  if (autosave.status.value === "saved") return `已保存 ${savedAt.value}`;
  return "尚未修改";
});

function pushToast(text) {
  const id = Date.now() + Math.random();
  toasts.value = [...toasts.value, { id, text }];
  setTimeout(() => {
    toasts.value = toasts.value.filter((item) => item.id !== id);
  }, 6000);
}

function handleFatal(error) {
  // 409 = 服务端已封卷（超时或已交卷），不是错误，是"该去结果页了"。
  if (error?.status === 409) emit("expired");
  else emit("error", error);
}

async function load() {
  loading.value = true;
  try {
    const payload = await fetchAttempt(props.attemptId);
    data.value = payload;
    answers.value = Object.fromEntries(
      payload.questions
        .filter((item) => item.answer)
        .map((item) => [item.problem_id_no, item.answer]),
    );
    if (props.initialProblem) {
      const anchor = payload.questions.findIndex(
        (item) => item.problem_id_no === props.initialProblem,
      );
      if (anchor >= 0) currentIndex.value = anchor;
    }
    clock = createExamClock({
      deadlineAt: payload.attempt.deadline_at,
      serverNow: payload.server_now,
      remindMinutes: payload.link.remind_minutes,
      onRemind: (minute) => pushToast(`还剩 ${minute} 分钟，注意时间。`),
      onExpire: () => finish(true),
    });
    remaining.value = clock.remainingMs();
    timer = setInterval(() => {
      remaining.value = clock.tick();
    }, 1000);
  } catch (error) {
    handleFatal(error);
  } finally {
    loading.value = false;
  }
}

function onAnswerChange(answer) {
  const key = current.value.problem_id_no;
  answers.value = { ...answers.value, [key]: answer };
  // 选项类立刻存，输入类交给防抖——狂敲键盘时不该每个字符发一次请求。
  const immediate = answer.type !== "fill";
  autosave.schedule(key, answer, { immediate }).catch(handleFatal);
}

function onProgrammingDraft({ language, code }) {
  const key = current.value?.problem_id_no;
  if (!key) return;
  const previous = answers.value[key] || {};
  const answer = {
    type: "programming",
    language: language || previous.language || null,
    ...(previous.submission_id ? { submission_id: previous.submission_id } : {}),
    draft_code: code,
  };
  answers.value = { ...answers.value, [key]: answer };
  autosave.schedule(key, answer).catch(handleFatal);
}

async function goTo(index) {
  // 切题前把上一题冲出去：学员的心智是"我离开这题时它已经存好了"。
  await autosave.flushAll().catch(handleFatal);
  currentIndex.value = index;
}

// 进到一道编程题就把提交记录数拉回来。操作条上的「提交记录 (n)」如果一直显示 0，
// 刷新过页面的人会以为之前的提交都没了。失败就静默留 0——这是个计数，不值得打断作答。
watch(
  current,
  async (question) => {
    if (question?.type !== "programming" || question.missing) return;
    const key = question.problem_id_no;
    if (submissions.value[key]) return;
    try {
      await loadSubmissionPage(question, 1);
    } catch {
      // 忽略：计数拉不到不影响作答，真交不上时 runCode 会报错
    }
  },
  { immediate: true },
);

async function onRun({ kind, language, code, customInput, onProgress, signal, resolve, reject }) {
  // 自测跑得频繁，不该让「试跑 / 提交判题」两个按钮跟着一起变灰；只有正式两种才占 busy。
  const selfTest = customInput !== undefined;
  if (!selfTest) judging.value = true;
  const key = current.value.problem_id_no;
  try {
    // 判题是异步的：这一步先拿到 queued，再轮询到终态。onProgress 把中间态
    // （排队位次）透给工作区显示，signal 让切题/卸载能掐断轮询。
    const payload = await runCodeAndWait(
      props.attemptId,
      {
        problem_id_no: key,
        language,
        code,
        kind,
        // 只在自测时带这个键：submit 携带它虽然后端会忽略，但请求体里出现没用的字段
        // 迟早有人照着它猜出错误的语义。
        ...(selfTest ? { custom_input: customInput } : {}),
      },
      {
        onProgress: (current) => {
          onProgress?.(current);
          // 只跟踪计分的提交：不计分的运行学员翻页走了就不用管了。
          if (kind === "submit") trackJudge(current);
        },
        // 同理，计分的提交用 ExamRunner 自己的 signal——切题不该让它失联。
        signal: kind === "submit" ? runnerAbort.signal : signal,
      },
    );
    if (kind === "submit") {
      answers.value = {
        ...answers.value,
        [key]: { type: "programming", language, submission_id: payload.id, draft_code: code },
      };
      autosave.schedule(key, answers.value[key], { immediate: true }).catch(handleFatal);
      // 提交判题的主反馈就是这个弹窗（与历史详情同款）。列表本地追加一条即可，
      // 不必再拉一次接口——payload 与接口返回的形状一致，只差学员自己的代码。
      submissions.value = {
        ...submissions.value,
        [key]: [...(submissions.value[key] || []), { ...payload, code }],
      };
      // 判题没跑成就别弹详情——那个弹窗是给"有判定结果"用的，判题异常时
      // 里面只剩一排 -- 和一个 ?，看着像系统在装傻。工作区会出中性告警横幅。
      if (payload.status !== "judge_failed") detail.value = { ...payload, code };
    }
    resolve(payload);
  } catch (error) {
    // 409 = 服务端已封卷，直接跳结果页；主动取消（切题/卸载）不该弹提示；
    // 其余错误必须当场看得见——之前这里只 reject 不提示，而工作区把 submit 的
    // 错误吞了，结果就是"点了提交判题，界面纹丝不动"。
    if (error?.status === 409) handleFatal(error);
    else if (error?.message !== "已取消。") pushToast(error.message);
    reject(error);
  } finally {
    if (!selfTest) judging.value = false;
  }
}

// 交卷不可逆，一律先确认。link.warn_unanswered 管的是"要不要额外警告还有题没做"，
// 不是"要不要确认"——把它当成确认开关，会让全做完的人一按就封卷，误触无法挽回。
const warnUnanswered = computed(
  () => !!data.value?.link.warn_unanswered && unanswered.value.length > 0,
);

function askSubmit() {
  confirmOpen.value = true;
}

async function finish(auto) {
  if (submitting.value) return;
  submitting.value = true;
  confirmOpen.value = false;
  submitError.value = "";
  clearTimeout(autoRetryTimer);
  try {
    await autosave.flushAll();
  } catch {
    // 保存失败也要让交卷继续：服务端以库里已存的答案判分，卡住交卷更糟。
  }
  try {
    await submitAttempt(props.attemptId);
    autoRetries = 0;
    emit("submitted", props.attemptId);
  } catch (error) {
    // judge_pending：还有计分判题没跑完，服务端不许封卷。留在原地提示等几秒，
    // 绝不能走 expired——那是"已封卷"的信号，会把人送去一个还不存在的结果页。
    if (error?.status === 409 && !error?.code) {
      emit("expired");
      return;
    }
    submitError.value = error?.message || "交卷失败，请重试。";
    // 自动收卷（倒计时归零）没有人在旁边点重试，这里自己排几次。
    // 判题在途通常几秒就好，5 秒一次、最多 3 次足以覆盖，之后交给手动按钮。
    if (auto && autoRetries < AUTO_RETRY_MAX) {
      autoRetries += 1;
      submitError.value = `${submitError.value}（${AUTO_RETRY_MS / 1000} 秒后自动重试，第 ${autoRetries}/${AUTO_RETRY_MAX} 次）`;
      autoRetryTimer = setTimeout(() => finish(true), AUTO_RETRY_MS);
    } else if (!auto) {
      emit("error", error);
    }
  } finally {
    submitting.value = false;
  }
}

onMounted(load);
onBeforeUnmount(() => {
  clearInterval(timer);
  clearTimeout(autoRetryTimer);
  // 点击「返回课时」可能发生在 1.5 秒防抖尚未到期时；销毁前必须把草稿发出，
  // 不能直接 cancelAll()，否则学生最容易在主动离开时丢掉刚写的代码。
  autosave.flushAll().catch(() => {});
  runnerAbort.abort(); // 离开作答页，在途提交的轮询也该停
});
</script>

<template>
  <div v-if="loading" class="exam-narrow"><p class="muted">正在加载题目…</p></div>

  <div v-else-if="data" class="exam-runner">
    <!-- 沉浸顶栏：考试中不渲染全站导航，卷面之外只留保存状态、时间和交卷。 -->
    <header class="exam-topbar">
      <div class="brand"><span class="logo">&lt;/&gt;</span>学习系统</div>
      <div class="paper-meta">
        <h1 class="paper-title">{{ data.paper.title }}</h1>
        <span class="paper-tag">{{ data.paper.paper_type }}</span>
      </div>
      <div class="spacer" />
      <div
        class="save-state"
        :class="{
          'is-saving': autosave.status.value === 'saving',
          'is-error': autosave.status.value === 'error',
        }"
      >
        <span class="dot" />{{ saveText }}
      </div>
      <div class="countdown" :class="{ 'is-urgent': urgent }">
        <span class="label">剩余</span>{{ clockText }}
      </div>
      <div class="progress-pill">
        <b>{{ answeredKeys.size }}</b
        >/{{ questions.length }} 题
      </div>
      <button class="btn btn-primary" type="button" :disabled="submitting" @click="askSubmit">
        交卷
      </button>
    </header>

    <!-- 交卷失败：横幅钉在顶栏正下方，带一个重试按钮。这条必须在作答页里，
         不能只往上抛——交卷是这一页最不能"点了没反应"的动作。 -->
    <div v-if="submitError" class="submit-error" role="alert" data-testid="submit-error">
      <span class="v-name">⚠ 交卷未完成</span>
      <span>{{ submitError }}</span>
      <span class="spacer" />
      <button class="btn" type="button" :disabled="submitting" @click="finish(false)">
        {{ submitting ? "重试中…" : "重试交卷" }}
      </button>
    </div>

    <div class="exam-layout">
      <ExamSidebar
        :questions="questions"
        :current-index="currentIndex"
        :answered-keys="answeredKeys"
        :marked-keys="marked"
        :playful="playful"
        @select="goTo"
      />

      <main class="exam-stage">
        <!-- 三段式统一骨架：题头条 / 工作区 / 导航条，五种题型共用同一张卡。 -->
        <article v-if="current" :key="current.problem_id_no" class="qcard">
          <div class="qcard-head">
            <span class="qnum">{{ String(currentIndex + 1).padStart(2, "0") }}</span>
            <span class="qtype">{{ QUESTION_TYPE_TEXT[current.type] || "题目" }}</span>
            <span v-if="isCompileOnly(current)" class="qtype is-compile-only">
              满分条件：编译通过
            </span>
            <button
              class="mark-btn"
              :class="{ 'is-on': currentMarked }"
              type="button"
              :aria-pressed="currentMarked"
              @click="toggleMark"
            >
              ⚑ {{ currentMarked ? "已标记" : "标记" }}
            </button>
            <span class="qscore">{{ current.score }} 分</span>
          </div>

          <div class="qcard-body" :class="isWorkspace ? 'is-workspace' : 'is-objective'">
            <div v-if="current.missing" class="error-box">
              这道题已被出题人移除，本题不计分，请继续作答其余题目。
            </div>

            <QuestionCoding
              v-else-if="isWorkspace"
              :question="current"
              :busy="judging"
              :submission-count="currentSubmissions.length"
              @run="onRun"
              @history="openHistory"
              @toast="pushToast"
              @draft-change="onProgrammingDraft"
            />

            <div v-else class="obj-inner">
              <MarkdownBody :source="current.stem" />

              <QuestionChoice
                v-if="['choice', 'multi_choice', 'judge'].includes(current.type)"
                :question="current"
                :answer="answers[current.problem_id_no]"
                @change="onAnswerChange"
              />
              <QuestionFill
                v-else-if="current.type === 'fill'"
                :question="current"
                :answer="answers[current.problem_id_no]"
                @change="onAnswerChange"
              />
            </div>
          </div>

          <div class="qcard-foot">
            <button
              class="btn"
              type="button"
              :disabled="currentIndex === 0"
              @click="goTo(currentIndex - 1)"
            >
              ← 上一题
            </button>
            <button
              class="btn"
              type="button"
              :disabled="currentIndex >= questions.length - 1"
              @click="goTo(currentIndex + 1)"
            >
              下一题 →
            </button>
            <span class="pos">{{ currentIndex + 1 }} / {{ questions.length }}</span>
          </div>
        </article>
      </main>
    </div>

    <div class="toast-stack">
      <div v-for="toast in toasts" :key="toast.id" class="toast">{{ toast.text }}</div>
    </div>

    <ConfirmDialog
      v-model:open="confirmOpen"
      title="确认交卷？"
      confirm-text="仍要交卷"
      cancel-text="回去检查"
      tone="danger"
      :busy="submitting"
      @confirm="finish(false)"
    >
      <div class="dialog-stats">
        <div>
          <b>{{ answeredKeys.size }}</b
          >已答
        </div>
        <div>
          <b>{{ unanswered.length }}</b
          >未答
        </div>
        <div>
          <b>{{ marked.size }}</b
          >标记
        </div>
        <div v-if="pendingJudges.size">
          <b>{{ pendingJudges.size }}</b
          >判题中
        </div>
      </div>
      <!-- 在途判题的警告排在未答警告前面：未答是学员自己的选择，
           这条是"判完之前服务端不收卷"，更紧急。 -->
      <p v-if="pendingJudges.size" class="unanswered-warn" data-testid="pending-judge-warn">
        还有 {{ pendingJudges.size }} 次提交判题没跑完。判题结束前无法交卷——
        通常只要几秒，等判完再交即可。
      </p>
      <p v-if="warnUnanswered" class="unanswered-warn">{{ unansweredText }}</p>
      <p class="mono-dim" style="margin-top: 10px">
        交卷后不可再修改答案。编程题成绩以最后一次「提交判题」为准。
      </p>
    </ConfirmDialog>

    <!-- 提交记录：行点击开同款判定详情 -->
    <ExamModal v-model:open="historyOpen" title="提交记录" wide>
      <table v-if="currentSubmissions.length" class="hist-table">
        <thead>
          <tr>
            <th>状态</th>
            <th>分数</th>
            <th>运行时间</th>
            <th>内存</th>
            <th>提交时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in currentSubmissions" :key="item.id" @click="openDetail(item)">
            <td>
              <span class="case-badge" :class="verdictOf(item.status).badge">
                {{ verdictOf(item.status).text }}
              </span>
            </td>
            <td class="mono-dim">{{ "score" in item ? item.score : "—" }}</td>
            <td class="mono-dim">{{ metricText(item.time_ms, "ms") }}</td>
            <td class="mono-dim">{{ metricText(item.memory_kb, "KB") }}</td>
            <td class="mono-dim">{{ new Date(item.created_at).toLocaleString("zh-CN") }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="mono-dim">这道题还没有提交判题的记录。试跑与自测不计入。</p>
      <p v-if="currentSubmissions.length" class="mono-dim" style="margin-top: 10px">
        点击任意一行查看判定详情与当次代码。
      </p>
      <div v-if="submissionPageCount > 1" class="history-pager">
        <button
          class="btn-chunky btn-sm"
          type="button"
          :disabled="currentSubmissionMeta.page <= 1"
          @click="loadSubmissionPage(current, currentSubmissionMeta.page - 1)"
        >
          上一页
        </button>
        <span
          >第 {{ currentSubmissionMeta.page }} / {{ submissionPageCount }} 页 · 共
          {{ currentSubmissionMeta.total }} 次</span
        >
        <button
          class="btn-chunky btn-sm"
          type="button"
          :disabled="currentSubmissionMeta.page >= submissionPageCount"
          @click="loadSubmissionPage(current, currentSubmissionMeta.page + 1)"
        >
          下一页
        </button>
      </div>
    </ExamModal>

    <!-- 判定详情：提交判题后的主反馈，也是历史记录点开后看到的东西 -->
    <ExamModal
      :open="!!detail"
      :title="detail ? `判定详情 · 提交 #${detail.id}` : ''"
      wide
      @update:open="detail = null"
    >
      <SubmissionDetail
        v-if="detail"
        :submission="detail"
        :compile-only="isCompileOnly(current)"
        @copied="pushToast"
      />
      <template #actions>
        <button class="btn" type="button" @click="detail = null">关闭</button>
      </template>
    </ExamModal>
  </div>
</template>
