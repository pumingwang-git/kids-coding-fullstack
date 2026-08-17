<script setup>
// 课中练习块（单题）· 形态 A「块内直答」（交接文档 15 第三节）。
//
// **复用考试页的题目渲染件**：QuestionChoice / QuestionFill 只吃 `question` + `answer`，
// 不认 attempt 也不认考试——这正是它们能被课时页复用的根本原因。样式靠外层的 `.qz`
// 类（question.css 从 exam.css 抽出，两个壳共用同一套题目样式）。
//
// **答案与解析永远来自服务端**：取题接口不下发答案，判定与解析只在提交后的响应里。
// 前端一行判分逻辑都不写——写了就是把答案发到客户端。
//
// 本块自己拉题、自己提交（那是它自己的数据），但**完成状态要回传给壳**：
// 提交成功后 emit("answered")，由壳更新抽屉进度，不然进度环不动。
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from "vue";
import { request } from "../../../services/auth";
import { takeProblem } from "../../../services/prefetch";
import MarkdownBody from "../../exam/MarkdownBody.vue";
import QuestionChoice from "../../exam/QuestionChoice.vue";
import QuestionFill from "../../exam/QuestionFill.vue";
import LessonIcon from "../LessonIcon.vue";
// 编程题拖着 CodeMirror（打包 580KB+），异步加载：纯客观题的课时不该为它买单。
const PracticeCoding = defineAsyncComponent(() => import("./PracticeCoding.vue"));
// 解析视频拖着 video.js（600KB+），异步加载：没配解析视频的题不该为主包买单。
const VideoPlayer = defineAsyncComponent(() => import("../../VideoPlayer.vue"));

const props = defineProps({
  block: { type: Object, required: true },
  lessonId: { type: Number, required: true },
});
const emit = defineEmits(["answered", "toast"]);

const TYPE_LABEL = {
  choice: "单选题",
  multi_choice: "多选题",
  judge: "判断题",
  fill: "填空题",
  programming: "编程题",
};

const state = ref(null); // 服务端下发的题面 + 作答态
const loading = ref(true);
const error = ref("");
const submitting = ref(false);
const resetting = ref(false);
// 提交/重做的错误单独走 submitError。以前复用 error，而模板上 v-else-if="error"
// 会把题干和选项整块替换成一行错误文字——点一次提交失败，学生看到的就是
// "空白页面 + 本题作答次数已用完"。题面没错，错的是这一次提交，不该把题面撤掉。
const submitError = ref("");
const confirmReset = ref(false); // 重做是有损操作，点两次才真的清
const draft = ref(null); // 未提交的作答草稿
const codingKey = ref(0); // 重做编程题时换 key 重挂工作区，把编辑器真的清空
let confirmTimer = null;

const question = computed(() => state.value?.question || null);
const verdict = computed(() => state.value?.verdict || null);
const submitted = computed(() => !!state.value?.submitted);
const typeLabel = computed(() => TYPE_LABEL[question.value?.type] || "题目");
const isCoding = computed(() => question.value?.type === "programming");
const attemptText = computed(() => {
  const limit = state.value?.attempt_limit || 0;
  if (!limit) return "次数不限";
  return `限 ${limit} 次（已用 ${state.value.tries}）`;
});
// 「重做本题」的可见条件：交过一次就有（**答对的人也要有**）。
// 复习是学习的一部分，只给答错的人重做，等于告诉学得好的学生"你不需要复习"。
// 次数用尽时按钮仍在，只是文案变成「重做（不计分）」——服务端允许清空作答态，
// 只是提交不上去（后端 reset_practice_answer 的第 3 条口径）。
const canReset = computed(() => submitted.value && !loading.value);
// 次数用尽且当前没有已判定的作答 = 自测态：重做之后 submitted 落回 false，
// 但 can_answer 仍是 false。此时若放行「提交答案」，每点一次就撞一次 409
// （服务端只清作答态、不返还次数，reset_practice_answer 第 3 条口径）——
// 所以提交按钮要直接禁掉，把"不计分"说在前面，而不是让学生拿报错碰出来。
const selfTestOnly = computed(
  () => !submitted.value && state.value?.can_answer === false,
);
// 自测态的解析（服务端在 self_test 分支下发，只有解析文本、没有对错明细）。
// 默认收起、点了才展开：一进来就摊开解析，学生还没作答就看到了答案，
// 自测就变回了"看答案"，这个功能存在的理由也没了。
const selfTestAnalysis = computed(() =>
  selfTestOnly.value && state.value?.self_test ? state.value.analysis || "" : "",
);
// 自测态的解析视频（同一闸门：只给 available/processing，播放走门控端点）
const selfTestAnalysisVideo = computed(() =>
  selfTestOnly.value && state.value?.self_test ? state.value.analysis_video || null : null,
);
const showSelfTestAnalysis = ref(false);
const resetLabel = computed(() => (state.value?.can_answer ? "重做本题" : "重做本题（不计分）"));
const resetHint = computed(() =>
  state.value?.can_answer
    ? "重做不消耗次数，已完成的记录也会保留"
    : "次数已用完，重做仅供自测，成绩不再更新",
);
// 作答是否已填（选择题选了、填空题至少填了一个空）
const hasDraft = computed(() => {
  const a = draft.value;
  if (!a) return false;
  if (Array.isArray(a.picked)) return a.picked.length > 0;
  if (a.picked) return true;
  return Object.values(a.blanks || {}).some((v) => String(v || "").trim());
});

async function load({ silent = false } = {}) {
  // silent：判完之后就地刷新作答态，不要再闪一次骨架屏——内容基本没变，
  // 闪一下反而像是"页面自己重来了一遍"。
  loading.value = !silent;
  error.value = "";
  submitError.value = "";
  try {
    // 壳可能在上一块就把题面预取好了（composables/useLessonPrefetch）。拿到的是
    // 可能还在飞的 promise，await 它不会重复发请求；预取失败会落成 null，
    // 那就照常请求一次——该报的错由这一次报出来，而不是被预取吞掉。
    const pending = takeProblem(props.block.id);
    const data =
      (pending ? await pending : null) ||
      (await request(`/api/lessons/${props.lessonId}/blocks/${props.block.id}/problem`));
    state.value = data;
    draft.value = data.answer || null;
    // 换了题/刷新了状态就把解析收回去，别让上一题展开的解析跟着漏到这一题。
    showSelfTestAnalysis.value = false;
  } catch (err) {
    error.value = err?.message || "题目加载失败。";
  } finally {
    loading.value = false;
  }
}

async function submit() {
  if (!hasDraft.value || submitting.value) return;
  submitting.value = true;
  submitError.value = "";
  try {
    const data = await request(`/api/lessons/${props.lessonId}/blocks/${props.block.id}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer: draft.value }),
    });
    state.value = { ...state.value, ...data };
    emit("answered");
  } catch (err) {
    // 409（次数已用完）说明前端的作答态和服务端对不上——比如之前已交过、
    // 或重做后次数没退回。回拉一次真实状态，页面落回"已提交/不计分重做"，
    // 学生能看到判定和去路，而不是停在一条报错上。
    // 注意顺序：load 会清 submitError，所以先刷新再写错误文案。
    if (err?.status === 409) await load({ silent: true });
    submitError.value = err?.message || "提交失败，请重试。";
  } finally {
    submitting.value = false;
  }
}

/** 重做本题。
 *
 * 以前这里叫「再试一次」，只把本地的 submitted 抹成 false——次数、作答内容、判定
 * 全都还在服务端，刷新一次立刻打回"已提交"。那是个不起作用的按钮。
 * 现在走服务端：清作答态、保留次数与完成记录（后端 POST …/reset）。
 *
 * 有损操作，点两次才执行：第一次把按钮变成"再点一次确认"，3 秒后自动撤销。
 * 不用 window.confirm——那是浏览器的弹窗，和这一页的观感完全脱节。
 */
async function reset() {
  if (resetting.value) return;
  if (!confirmReset.value) {
    confirmReset.value = true;
    clearTimeout(confirmTimer);
    // 5 秒：够读完变化后的文案再把手移到按钮上。给 3 秒实测会撤销得太快，
    // 学生第二下点空，只会重新进确认态，看起来就是"这个按钮点不动"。
    confirmTimer = setTimeout(() => (confirmReset.value = false), 5000);
    return;
  }
  clearTimeout(confirmTimer);
  confirmReset.value = false;
  resetting.value = true;
  submitError.value = "";
  try {
    const data = await request(`/api/lessons/${props.lessonId}/blocks/${props.block.id}/reset`, {
      method: "POST",
    });
    const coding = isCoding.value;
    state.value = {
      ...state.value,
      ...data,
      verdict: null,
      // 题面对象也要跟着清 last_code。编辑器的初值取自 question.last_code，
      // 而它是**取题那一刻**的快照——不清的话，下面换 key 重挂时旧代码会被
      // 原样填回去，"重做"看起来就像没生效。
      question: coding
        ? { ...state.value.question, last_code: data.last_code ?? "" }
        : state.value.question,
    };
    draft.value = null;
    // 刚清空重来，解析要跟着收起——重做的意义就是"再自己想一遍"。
    showSelfTestAnalysis.value = false;
    // 编辑器的初值只在挂载时读一次，换个 key 才能真的清空。
    if (coding) codingKey.value += 1;
  } catch (err) {
    submitError.value = err?.message || "重做失败，请重试。";
  } finally {
    resetting.value = false;
  }
}

/** 编程题判完：成绩、次数、完成度、后续块解锁全在这一刻变，就地把状态取回来。 */
async function onGraded() {
  await load({ silent: true });
  emit("answered");
}

onBeforeUnmount(() => clearTimeout(confirmTimer));
watch(
  () => props.block.id,
  () => load(),
  { immediate: true },
);
</script>

<template>
  <div class="block-practice qz">
    <p class="leyebrow">
      课中练习<template v-if="state?.display_no"> · 第 {{ state.display_no }} 题</template>
      <span class="ltag on-warn">{{ typeLabel }}</span>
      <span class="ltag">{{ state?.score ?? 0 }} 分</span>
      <span class="ltag">{{ attemptText }}</span>
    </p>

    <!-- 骨架而不是「正在加载题目…」：高度对齐真实题干与选项，内容回来时版式不跳。
         配合相邻块预热，正常情况下学生根本看不到它（交接文档 17 §5 S2-6）。 -->
    <div v-if="loading" class="practice-skeleton" role="status" aria-label="正在加载题目">
      <span class="sk-line sk-w92"></span>
      <span class="sk-line sk-w64"></span>
      <span v-for="n in 4" :key="n" class="sk-opt"></span>
    </div>
    <p v-else-if="error" class="practice-error">{{ error }}</p>

    <!-- 编程题：整块交给工作区（题面 + 编辑器 + 控制台），不套 block-wrap 的窄栏。
         「▶ 运行」不计分，「提交判题」跑全部测试点并计分——两个动作在工作区里。 -->
    <template v-else-if="question && question.type === 'programming'">
      <PracticeCoding
        :key="codingKey"
        :question="question"
        :block-id="block.id"
        :lesson-id="lessonId"
        :can-answer="!!state?.can_answer"
        :tries-left="state?.tries_left ?? null"
        @graded="onGraded"
        @toast="emit('toast', $event)"
      />
    </template>

    <template v-else-if="question">
      <div class="practice-stem"><MarkdownBody :source="question.stem" /></div>

      <!-- 已提交：锁住作答区，避免学生以为还能改 -->
      <div class="practice-answer" :class="{ 'is-locked': submitted }">
        <QuestionChoice
          v-if="
            question.type === 'choice' ||
            question.type === 'multi_choice' ||
            question.type === 'judge'
          "
          :question="question"
          :answer="draft"
          @change="draft = $event"
        />
        <QuestionFill
          v-else-if="question.type === 'fill'"
          :question="question"
          :answer="draft"
          @change="draft = $event"
        />
        <p v-else class="muted">该题型暂不支持在课中练习内作答。</p>
      </div>

      <!-- 判定区：分数、对错、解析。全部来自服务端 -->
      <div
        v-if="submitted && verdict"
        class="practice-verdict"
        :class="{ 'is-bad': !verdict.is_correct }"
      >
        <h4>
          <LessonIcon :name="verdict.is_correct ? 'check' : 'steps'" :size="14" />
          {{ verdict.is_correct ? `回答正确 +${verdict.score} 分` : "回答错误" }}
        </h4>
        <div v-if="verdict.analysis" class="practice-analysis">
          <MarkdownBody :source="verdict.analysis" />
        </div>
        <!-- 解析视频：与 scratch 块同一门控纪律——显示与否只看服务端下发的
             analysis_video（available/processing），播放地址走提交后才放行的签发端点。 -->
        <div v-if="verdict.analysis_video" class="practice-analysis-video">
          <strong>教师解析</strong>
          <VideoPlayer
            v-if="verdict.analysis_video.available"
            :lesson-id="lessonId"
            :play-path="verdict.analysis_video.play_path"
          />
          <p v-else-if="verdict.analysis_video.processing" class="muted">
            解析视频仍在处理中，请稍后再看。
          </p>
        </div>
      </div>

      <!-- 自测态的解析。次数用尽后重做，服务端不再判分，判定区永远不会出现——
           没有这一块，学生答完就只能对着题目发呆。给的是解析文本，不是对错明细：
           哪个选项对仍然不下发（后端 _state_payload 的 self_test 分支）。 -->
      <div
        v-else-if="showSelfTestAnalysis && selfTestAnalysis"
        class="practice-verdict is-selftest"
      >
        <h4>
          <LessonIcon name="steps" :size="14" />
          参考解析（本次不计分）
        </h4>
        <div class="practice-analysis">
          <MarkdownBody :source="selfTestAnalysis" />
        </div>
        <div v-if="selfTestAnalysisVideo" class="practice-analysis-video">
          <strong>教师解析</strong>
          <VideoPlayer
            v-if="selfTestAnalysisVideo.available"
            :lesson-id="lessonId"
            :play-path="selfTestAnalysisVideo.play_path"
          />
          <p v-else-if="selfTestAnalysisVideo.processing" class="muted">
            解析视频仍在处理中，请稍后再看。
          </p>
        </div>
      </div>
    </template>

    <div class="block-foot">
      <slot name="prev" />

      <!-- 编程题的两个动作（运行 / 提交判题）在工作区的操作条里，这里只留去向。 -->
      <template v-if="isCoding">
        <button
          v-if="canReset"
          class="lbtn lbtn-chunky"
          :class="{ 'is-confirming': confirmReset }"
          type="button"
          :disabled="resetting"
          @click="reset"
        >
          {{ confirmReset ? "再点一次清空代码" : "重做本题" }}
        </button>
        <slot name="next" />
        <span v-if="submitError" class="hint hint-error" role="alert">{{ submitError }}</span>
        <span v-else class="hint">{{
          submitted ? "已提交判题，成绩以最后一次为准" : "运行调试满意后点「提交判题」计分"
        }}</span>
      </template>

      <!-- 题目没取回来时也要留一条去路：卡在一个连题目都没有的块上无处可去，
           比让他往下走更糟。 -->
      <template v-else-if="error && !question">
        <slot name="next" />
        <span class="hint">题目暂时取不回来，可以先继续后面的内容</span>
      </template>

      <template v-else-if="!submitted">
        <button
          class="lbtn lbtn-chunky lbtn-accent"
          type="button"
          :disabled="!hasDraft || submitting || loading || selfTestOnly"
          @click="submit"
        >
          {{ submitting ? "提交中…" : "提交答案" }}
        </button>
        <!-- 自测态唯一的反馈出口。没有它，学生答完既提交不了、也对不了答案，
             「重做（不计分）」就成了一条死路。 -->
        <button
          v-if="selfTestAnalysis"
          class="lbtn lbtn-chunky"
          type="button"
          @click="showSelfTestAnalysis = !showSelfTestAnalysis"
        >
          {{ showSelfTestAnalysis ? "收起解析" : "查看解析" }}
        </button>
        <!-- 自测态要留去路。这一支是「未提交」，正常情况下不该给 next——没做完就
             往下走会绕过顺序锁。但自测态是**做完之后**清空重来的，完成记录早就写了
             （重做不回收完成度），此时不给 next，学生一点「重做」就把自己关在这一块里。 -->
        <slot v-if="selfTestOnly" name="next" />
        <span v-if="selfTestOnly" class="hint">
          次数已用完，现在作答仅供自测，不计分
        </span>
        <span v-else-if="!hasDraft && !loading" class="hint">先作答再提交</span>
        <span v-else-if="submitError" class="hint hint-error" role="alert">
          {{ submitError }}
        </span>
      </template>

      <template v-else>
        <button
          class="lbtn lbtn-chunky"
          :class="{ 'is-confirming': confirmReset }"
          type="button"
          :disabled="resetting"
          @click="reset"
        >
          {{ confirmReset ? "再点一次确认" : resetLabel }}
        </button>
        <slot name="next" />
        <span v-if="submitError" class="hint hint-error" role="alert">{{ submitError }}</span>
        <span v-else class="hint">{{ resetHint }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.practice-stem {
  font-size: 15px;
  line-height: 1.85;
  margin: 4px 0 18px;
}
.practice-answer.is-locked {
  pointer-events: none;
  opacity: 0.85;
}
/* 判定区对齐考试页的 .qz .verdict-banner（question.css:689）：整圈边框 + 淡色底。
   两处都是"判定"，长得不一样只会让人以为是两个东西。 */
.practice-verdict {
  margin-top: 18px;
  padding: 12px 16px;
  border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--line));
  border-radius: var(--control-radius);
  background: var(--mint);
}
.practice-verdict.is-bad {
  border-color: color-mix(in srgb, var(--danger) 40%, var(--line));
  background: color-mix(in srgb, var(--danger) 8%, var(--surface));
}
.practice-verdict h4 {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  margin: 0 0 6px;
  color: var(--accent);
}
.practice-verdict.is-bad h4 {
  color: var(--danger);
}
/* 自测态的解析走中性色：这次根本没判分，套 accent（正确）或 danger（错误）
   都会被读成一个判定结果——学生刚自测完，最不该给他一个假的对错信号。
   令牌全部沿用现有的，不新增颜色。 */
.practice-verdict.is-selftest {
  border-color: var(--line);
  background: color-mix(in srgb, var(--muted) 6%, var(--surface));
}
.practice-verdict.is-selftest h4 {
  color: var(--muted);
}
.practice-analysis {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.8;
}
/* 解析视频：判定区内的 16:9 播放器。VideoPlayer 自带深色底与圆角。 */
.practice-analysis-video {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}
.practice-analysis-video strong {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--muted);
}
.practice-error {
  color: var(--danger);
  font-size: 13px;
}
/* 提交/重做的就地报错：跟在按钮后面，颜色沿用 danger 令牌。 */
.block-foot .hint-error {
  color: var(--danger);
}
/* 重做的二次确认态。用告警色而不是危险色：这不是删数据，只是清掉这一遍的作答，
   完成记录和次数都还在。颜色全部取自已有令牌，不新增。 */
.block-practice .lbtn.is-confirming {
  border-color: var(--warn);
  background: var(--cream);
  color: #7a5a1e;
  font-weight: 500;
}
:root.dark .block-practice .lbtn.is-confirming {
  color: var(--warn);
}

/* 取题骨架。尺寸照抄真实元素：题干行高 15px×1.85≈28，选项 = badge 24 + 上下 padding 20
   + 边框 2 = 46，选项间距同 .qz .option-list 的 8px。差太多就等于「加载完跳一下」，
   还不如不做骨架。颜色只用 --mint，不新增灰度色。 */
.practice-skeleton {
  display: grid;
  gap: 8px;
  margin: 4px 0 18px;
}
.sk-line,
.sk-opt {
  display: block;
  background: var(--mint);
  border-radius: var(--control-radius);
  animation: practice-sk-pulse 1.4s ease-in-out infinite;
}
.sk-line {
  height: 15px;
  margin-bottom: 6px;
}
.sk-w92 {
  width: 92%;
}
.sk-w64 {
  width: 64%;
  margin-bottom: 16px;
}
.sk-opt {
  height: 46px;
}
@keyframes practice-sk-pulse {
  0%,
  100% {
    opacity: 0.5;
  }
  50% {
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk-line,
  .sk-opt {
    animation: none;
    opacity: 0.65;
  }
}
</style>
