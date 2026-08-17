<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  ArrowLeft, ArrowRight, Check, CheckCircle2, CircleAlert, Clock3, Eraser, Eye, EyeOff,
  Lightbulb, Medal, Parentheses, RefreshCw, RotateCcw, Settings, Trophy, X,
} from "@lucide/vue";
import { generatePuzzle, puzzleKey, solvePuzzle, tokensToDisplay, validateExpression } from "../engine/game24";

const route = useRoute();
const router = useRouter();
const mode = ref(["practice", "challenge"].includes(route.query.mode) ? route.query.mode : "practice");
const difficulty = ref(["easy", "medium", "hard"].includes(route.query.difficulty) ? route.query.difficulty : "easy");
const modeLabel = computed(() => mode.value === "challenge" ? "60 秒挑战" : "自由练习");
const difficultyLabel = computed(() => ({ easy: "热身", medium: "进阶", hard: "高手" })[difficulty.value]);
const encouragingOtter = `${import.meta.env.BASE_URL}assets/otter-encouraging.png`;
const CHALLENGE_SECONDS = 60;

const modes = [
  { key: "practice", title: "自由练习" },
  { key: "challenge", title: "60 秒挑战" },
];
const difficulties = [
  { key: "easy", title: "热身" },
  { key: "medium", title: "进阶" },
  { key: "hard", title: "高手" },
];
const settingsOpen = ref(false);
const settingsPanel = ref(null);
const settingsButton = ref(null);
const draftMode = ref(mode.value);
const draftDifficulty = ref(difficulty.value);
const settingsPausedTimer = ref(false);

const puzzle = ref(generatePuzzle(difficulty.value));
const tokens = ref([]);
const feedback = ref(null);
const showAnswer = ref(false);
const transitioning = ref(false);
const phase = ref(mode.value === "challenge" ? "intro" : "playing");
const remaining = ref(CHALLENGE_SECONDS);
const usedPuzzles = new Set();
const startedAt = ref(mode.value === "practice" ? Date.now() : null);
const solvedCurrent = ref(false);
let timer = null;
let advanceTimer = null;

const round = reactive({ score: 0, correct: 0, wrong: 0, combo: 0, maxCombo: 0 });
const expression = computed(() => tokensToDisplay(tokens.value));
const answer = computed(() => solvePuzzle(puzzle.value)?.expression || "这道题暂时没有答案");
const usedSources = computed(() => new Set(tokens.value.filter((item) => item.type === "number").map((item) => item.source)));
const lastToken = computed(() => tokens.value.at(-1));
const unmatchedLeft = computed(() => tokens.value.reduce((count, item) => item.type === "parenthesis" ? count + (item.value === "(" ? 1 : -1) : count, 0));
const canAddNumber = computed(() => !lastToken.value || lastToken.value.type === "operator" || (lastToken.value.type === "parenthesis" && lastToken.value.value === "("));
const canAddOperator = computed(() => lastToken.value?.type === "number" || (lastToken.value?.type === "parenthesis" && lastToken.value.value === ")"));
const canCloseParenthesis = computed(() => unmatchedLeft.value > 0 && canAddOperator.value);
const canPlay = computed(() => phase.value === "playing" && !transitioning.value && !solvedCurrent.value);
const accuracy = computed(() => {
  const total = round.correct + round.wrong;
  return total ? Math.round((round.correct / total) * 100) : 0;
});
const timeProgress = computed(() => remaining.value / CHALLENGE_SECONDS);

function resetInput() {
  tokens.value = [];
  feedback.value = null;
  showAnswer.value = false;
  transitioning.value = false;
  solvedCurrent.value = false;
}

function nextPuzzle() {
  usedPuzzles.add(puzzleKey(puzzle.value));
  puzzle.value = generatePuzzle(difficulty.value, usedPuzzles);
  resetInput();
}

function appendNumber(source) {
  if (!canPlay.value || !canAddNumber.value || usedSources.value.has(source)) return;
  tokens.value.push({ type: "number", value: puzzle.value[source], source });
  feedback.value = null;
}

function appendOperator(value) {
  if (!canPlay.value || !canAddOperator.value) return;
  tokens.value.push({ type: "operator", value });
  feedback.value = null;
}

function appendParenthesis(value) {
  if (!canPlay.value) return;
  if (value === "(" && canAddNumber.value) tokens.value.push({ type: "parenthesis", value });
  if (value === ")" && canCloseParenthesis.value) tokens.value.push({ type: "parenthesis", value });
}

function undo() {
  if (!canPlay.value) return;
  tokens.value.pop();
  feedback.value = null;
}

function clearExpression() {
  if (!canPlay.value) return;
  tokens.value = [];
  feedback.value = null;
}

function submit() {
  if (!canPlay.value) return;
  const result = validateExpression(tokens.value, puzzle.value);
  feedback.value = { kind: result.ok ? "correct" : result.kind, message: result.message };
  if (result.ok) {
    round.score += 10;
    round.correct += 1;
    round.combo += 1;
    round.maxCombo = Math.max(round.maxCombo, round.combo);
    solvedCurrent.value = true;
    if (mode.value === "challenge") {
      advanceTimer = window.setTimeout(nextPuzzle, 550);
    }
    return;
  }
  if (result.kind === "wrong") {
    round.wrong += 1;
    round.combo = 0;
    if (mode.value === "challenge") {
      transitioning.value = true;
      advanceTimer = window.setTimeout(nextPuzzle, 850);
    }
  }
}

function startChallenge() {
  phase.value = "playing";
  startedAt.value = Date.now();
  remaining.value = CHALLENGE_SECONDS;
  nextPuzzle();
  runChallengeTimer();
}

function runChallengeTimer() {
  window.clearInterval(timer);
  const deadline = Date.now() + remaining.value * 1000;
  timer = window.setInterval(() => {
    remaining.value = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    if (remaining.value === 0) finishRound();
  }, 250);
}

function finishRound() {
  window.clearInterval(timer);
  window.clearTimeout(advanceTimer);
  timer = null;
  advanceTimer = null;
  phase.value = "finished";
}

function playAgain() {
  Object.assign(round, { score: 0, correct: 0, wrong: 0, combo: 0, maxCombo: 0 });
  usedPuzzles.clear();
  resetInput();
  if (mode.value === "challenge") {
    phase.value = "intro";
    remaining.value = CHALLENGE_SECONDS;
    startedAt.value = null;
  } else {
    phase.value = "playing";
    startedAt.value = Date.now();
    nextPuzzle();
  }
}

function handleKeydown(event) {
  if (settingsOpen.value) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSettings();
    }
    return;
  }
  const target = event.target;
  if (!canPlay.value || event.ctrlKey || event.metaKey || event.altKey || target?.closest?.("button, a, input, textarea, select")) return;
  const operators = { "+": "+", "-": "-", "*": "*", "/": "/" };
  if (operators[event.key]) appendOperator(operators[event.key]);
  else if (event.key === "(") appendParenthesis("(");
  else if (event.key === ")") appendParenthesis(")");
  else if (event.key === "Backspace") undo();
  else if (event.key === "Escape") clearExpression();
  else if (event.key === "Enter") submit();
  else if (/^[1-9]$/.test(event.key)) {
    const source = puzzle.value.findIndex((value, index) => value === Number(event.key) && !usedSources.value.has(index));
    if (source >= 0) appendNumber(source);
  } else return;
  event.preventDefault();
}

function openSettings() {
  draftMode.value = mode.value;
  draftDifficulty.value = difficulty.value;
  settingsPausedTimer.value = mode.value === "challenge" && phase.value === "playing" && timer !== null;
  if (settingsPausedTimer.value) {
    window.clearInterval(timer);
    timer = null;
  }
  settingsOpen.value = true;
  document.body.style.overflow = "hidden";
  nextTick(() => settingsPanel.value?.focus());
}

function closeSettings() {
  settingsOpen.value = false;
  document.body.style.overflow = "";
  if (settingsPausedTimer.value) runChallengeTimer();
  settingsPausedTimer.value = false;
  nextTick(() => settingsButton.value?.focus());
}

function applySettings() {
  window.clearInterval(timer);
  window.clearTimeout(advanceTimer);
  timer = null;
  advanceTimer = null;
  mode.value = draftMode.value;
  difficulty.value = draftDifficulty.value;
  Object.assign(round, { score: 0, correct: 0, wrong: 0, combo: 0, maxCombo: 0 });
  usedPuzzles.clear();
  resetInput();
  puzzle.value = generatePuzzle(difficulty.value);
  remaining.value = CHALLENGE_SECONDS;
  phase.value = mode.value === "challenge" ? "intro" : "playing";
  startedAt.value = mode.value === "practice" ? Date.now() : null;
  settingsPausedTimer.value = false;
  settingsOpen.value = false;
  document.body.style.overflow = "";
  router.replace({ name: "game24-play", query: { mode: mode.value, difficulty: difficulty.value } });
  nextTick(() => settingsButton.value?.focus());
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown);
});
onBeforeUnmount(() => {
  window.clearInterval(timer);
  window.clearTimeout(advanceTimer);
  window.removeEventListener("keydown", handleKeydown);
  document.body.style.overflow = "";
});
</script>

<template>
  <main class="play-page">
    <header class="play-bar">
      <RouterLink class="back-link" to="/"><ArrowLeft :size="19" />返回游戏大厅</RouterLink>
      <div class="mini-brand"><span aria-hidden="true">24</span><strong>{{ modeLabel }}</strong></div>
      <div class="play-tools">
        <span class="difficulty-badge">{{ difficultyLabel }}</span>
        <button ref="settingsButton" class="settings-command" type="button" aria-haspopup="dialog" @click="openSettings"><Settings :size="17" />设置</button>
      </div>
    </header>

    <section v-if="phase === 'intro'" class="challenge-intro-screen">
      <div class="intro-timer"><Clock3 :size="44" aria-hidden="true" /><strong>60</strong><span>秒</span></div>
      <h1>准备好连续解题了吗？</h1>
      <p>答对一题得 10 分；答错会自动换题，连对记录会重新开始。</p>
      <button class="primary-command" type="button" @click="startChallenge">开始计时<ArrowRight :size="21" /></button>
    </section>

    <section v-else-if="phase === 'finished'" class="result-screen" aria-labelledby="result-title">
      <div class="result-emblem"><Trophy :size="46" aria-hidden="true" /></div>
      <h1 id="result-title">本轮任务完成</h1>
      <p>{{ round.correct ? `你解出了 ${round.correct} 道题。` : "先熟悉数字组合，下一局会更顺手。" }}</p>
      <dl class="result-stats">
        <div><dt>得分</dt><dd>{{ round.score }}</dd></div>
        <div><dt>正确率</dt><dd>{{ accuracy }}<small>%</small></dd></div>
        <div><dt>答对</dt><dd>{{ round.correct }}</dd></div>
        <div><dt>答错</dt><dd>{{ round.wrong }}</dd></div>
         <div><dt>最高连对</dt><dd>{{ round.maxCombo }}</dd></div>
      </dl>
      <div class="result-actions">
        <button class="primary-command" type="button" @click="playAgain"><RefreshCw :size="20" />再来一局</button>
        <button class="secondary-command" type="button" @click="openSettings"><Settings :size="18" />调整设置</button>
        <RouterLink class="secondary-command" to="/">返回游戏大厅</RouterLink>
      </div>
    </section>

    <template v-else>
      <section class="play-status" aria-label="本轮状态">
        <div v-if="mode === 'challenge'" class="timer-status">
          <Clock3 :size="19" /><strong>{{ remaining }} 秒</strong>
          <span class="timer-track" aria-hidden="true"><i :style="{ transform: `scaleX(${timeProgress})` }"></i></span>
        </div>
        <div class="live-score"><span>得分 <strong>{{ round.score }}</strong></span><span>连对 <strong>{{ round.combo }}</strong></span></div>
      </section>

       <div class="play-layout">
       <section class="game-workbench" aria-labelledby="board-title">
        <div class="board-heading">
          <div><h1 id="board-title">拼出你的算式</h1><p>四个数字都要用，而且每个只能用一次。</p></div>
          <div class="target-orb"><span>目标</span><strong>24</strong></div>
        </div>

        <div class="expression-display" :class="feedback?.kind" aria-live="polite">
          <span v-if="expression">{{ expression }}</span>
          <span v-else class="expression-placeholder">先选择一个数字</span>
          <strong>= 24</strong>
        </div>

        <div class="number-rail" aria-label="本题数字">
          <button
            v-for="(value, index) in puzzle"
            :key="`${value}-${index}`"
            class="number-key"
            :class="{ used: usedSources.has(index) }"
            type="button"
            :disabled="usedSources.has(index) || !canAddNumber || solvedCurrent"
            :aria-label="`使用数字 ${value}`"
            @click="appendNumber(index)"
          >{{ value }}</button>
        </div>

        <div class="operation-console" aria-label="运算工具">
          <button v-for="item in [{ value: '+', label: '+' }, { value: '-', label: '−' }, { value: '*', label: '×' }, { value: '/', label: '÷' }]" :key="item.value" type="button" :disabled="!canAddOperator || solvedCurrent" :aria-label="`添加${item.label}号`" @click="appendOperator(item.value)">{{ item.label }}</button>
          <button type="button" :disabled="!canAddNumber || solvedCurrent" aria-label="添加左括号" @click="appendParenthesis('(')">(</button>
          <button type="button" :disabled="!canCloseParenthesis || solvedCurrent" aria-label="添加右括号" @click="appendParenthesis(')')">)</button>
          <button class="icon-button" type="button" :disabled="!tokens.length || solvedCurrent" aria-label="撤销一步" title="撤销一步" @click="undo"><RotateCcw :size="20" /></button>
          <button class="icon-button" type="button" :disabled="!tokens.length || solvedCurrent" aria-label="清空算式" title="清空算式" @click="clearExpression"><Eraser :size="20" /></button>
        </div>

        <p v-if="feedback" class="game-feedback" :class="feedback.kind" role="status">
          <CheckCircle2 v-if="feedback.kind === 'correct'" :size="20" />
          <CircleAlert v-else :size="20" />
          {{ feedback.message }}
        </p>

        <div class="board-actions">
          <button v-if="!solvedCurrent" class="primary-command" type="button" :disabled="!tokens.length" @click="submit">验证算式<ArrowRight :size="20" /></button>
          <button v-else class="primary-command" type="button" @click="nextPuzzle">下一题<ArrowRight :size="20" /></button>
          <button v-if="mode === 'practice'" class="secondary-command" type="button" @click="showAnswer = !showAnswer">
            <EyeOff v-if="showAnswer" :size="19" /><Eye v-else :size="19" />{{ showAnswer ? "收起答案" : "查看答案" }}
          </button>
          <button v-if="mode === 'practice'" class="secondary-command" type="button" @click="nextPuzzle"><RefreshCw :size="19" />换一题</button>
          <button v-if="mode === 'practice'" class="finish-practice" type="button" @click="finishRound"><Medal :size="19" />结束本次练习</button>
        </div>

        <div v-if="showAnswer && mode === 'practice'" class="answer-panel" aria-live="polite">
          <Lightbulb :size="21" /><span>一种解法</span><strong>{{ answer }} = 24</strong>
        </div>
       </section>

       <aside class="coach-strip" aria-label="解题提示">
        <img :src="encouragingOtter" alt="为你加油的水獭" />
        <Lightbulb :size="22" aria-hidden="true" />
        <div><strong>卡住时，先找小目标</strong><span>试着凑出 6、8 或 12，再和剩下的数字组合。</span></div>
        <Parentheses :size="22" aria-hidden="true" />
         <div><strong>括号会改变顺序</strong><span>高手难度里，它常常是关键。</span></div>
       </aside>
       </div>
    </template>

    <div v-if="settingsOpen" class="settings-backdrop" @click.self="closeSettings">
      <section
        ref="settingsPanel"
        class="settings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        tabindex="-1"
      >
        <header class="settings-dialog__header">
          <h2 id="settings-title">游戏设置</h2>
          <button class="dialog-close" type="button" aria-label="关闭设置" title="关闭设置" @click="closeSettings"><X :size="21" /></button>
        </header>

        <fieldset class="settings-group">
          <legend>玩法</legend>
          <div class="setting-segments setting-segments--mode">
            <button
              v-for="item in modes"
              :key="item.key"
              type="button"
              :class="{ selected: draftMode === item.key }"
              :aria-pressed="draftMode === item.key"
              @click="draftMode = item.key"
            >
              {{ item.title }}<Check v-if="draftMode === item.key" :size="17" aria-hidden="true" />
            </button>
          </div>
        </fieldset>

        <fieldset class="settings-group">
          <legend>难度</legend>
          <div class="setting-segments setting-segments--difficulty">
            <button
              v-for="item in difficulties"
              :key="item.key"
              type="button"
              :class="{ selected: draftDifficulty === item.key }"
              :aria-pressed="draftDifficulty === item.key"
              @click="draftDifficulty = item.key"
            >
              {{ item.title }}<Check v-if="draftDifficulty === item.key" :size="17" aria-hidden="true" />
            </button>
          </div>
        </fieldset>

        <p class="settings-note">应用后将重新开始本轮。</p>
        <footer class="settings-dialog__actions">
          <button class="secondary-command" type="button" @click="closeSettings">取消</button>
          <button class="primary-command" type="button" @click="applySettings">应用设置</button>
        </footer>
      </section>
    </div>
  </main>
</template>
