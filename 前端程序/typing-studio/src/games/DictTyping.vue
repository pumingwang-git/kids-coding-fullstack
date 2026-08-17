<template>
  <div class="dt">
    <header class="topbar">
      <button class="btn-back" type="button" @click="$emit('home')">‹ 返回</button>
      <select class="dict-select" :value="dictId" @change="onDictChange">
        <optgroup v-for="(group, cat) in groupedDicts" :key="cat" :label="cat">
          <option v-for="d in group" :key="d.id" :value="d.id">{{ d.name }}</option>
        </optgroup>
      </select>
      <div class="live-stats">
        <span class="stat-pill">{{ elapsedText }}</span>
        <span class="stat-pill">{{ wpm }} WPM</span>
        <span class="stat-pill">{{ acc }}% 准</span>
      </div>
    </header>

    <main class="dt-main">
      <template v-if="loading">
        <div class="dt-loading">词库加载中…</div>
      </template>

      <template v-else-if="!roundDone">
        <!-- 单词卡：qwerty-learner 式逐词打字 -->
        <div class="word-card" :class="{ shake: shaking }">
          <!-- 默写模式：只给中文，打英文 -->
          <div v-if="blind" class="word-blind">
            <div class="word-zh-main">{{ currentTrans }}</div>
            <div class="word-mask">{{ letterMask }}</div>
          </div>
          <!-- 明背模式：英文大字 + 音标 -->
          <div v-else class="word-show">
            <div class="word-letters" :style="{ '--word-size': wordFontSize }">
              <span
                v-for="(ch, i) in letters"
                :key="i"
                class="w-char"
                :class="letterClass(i)"
              >{{ ch }}</span>
            </div>
            <div v-if="current.usphone" class="word-phonetic">[{{ current.usphone }}]</div>
          </div>

          <!-- 打完单词 → 显示中文（"打完显示中文"核心交互） -->
          <transition name="fade">
            <div v-if="phase === 'reveal' && !blind" class="word-reveal">
              {{ currentTrans }}
            </div>
          </transition>
        </div>

        <div class="dt-actions">
          <button v-if="speakable" class="btn-sound" type="button" @click="speakCurrent">🔊 发音</button>
          <button class="btn-skip" type="button" @click="skip">跳过 ›</button>
          <label class="blind-toggle">
            <input type="checkbox" v-model="blind" /> 默写模式
          </label>
        </div>
        <div class="dt-progress">{{ idx + 1 }} / {{ queue.length }} · 对 {{ correctCount }} · 错 {{ wrongCount }}</div>
      </template>

      <ResultPanel
        v-else
        title="本组完成！"
        :stats="finalStats"
        :record="record"
        @retry="restart"
        @home="$emit('home')"
      />
    </main>

    <VirtualKeyboard
      v-if="!loading && !roundDone && showKeyboard"
      :highlight="nextKey"
      :last-wrong="lastWrong"
      @key="onKey"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import VirtualKeyboard from '../components/VirtualKeyboard.vue';
import ResultPanel from '../components/ResultPanel.vue';
import { TypingEngine } from '../engine/typingEngine.js';
import { DICT_GROUPS, loadDict, findDict } from '../data/registry.js';
import { speakWordYoudao, cancelSpeak } from '../utils/speech.js';
import { playCorrect, playWrong, playWin } from '../utils/audio.js';
import { recordGame, getRecord } from '../utils/storage.js';

const props = defineProps({
  ageGroup: { type: String, default: '13+' }
});
defineEmits(['home']);

const isKids = props.ageGroup === '7-12';
const showKeyboard = isKids;
const ROUND_SIZE = 20;

const dictOptions = DICT_GROUPS[props.ageGroup] || DICT_GROUPS['13+'];
const dictId = ref(dictOptions[0].id);

// 按 category 分组渲染 optgroup（英语教材 / 英语考试 / 编程 / 其他）
const groupedDicts = computed(() => {
  const groups = {};
  for (const d of dictOptions) {
    const cat = d.category || '其他';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(d);
  }
  return groups;
});

const currentDict = computed(() => findDict(props.ageGroup, dictId.value));
const speakable = computed(() => currentDict.value?.speakable !== false);

// 编程词条较长（如 str.upper()），按词长缩字号
const wordFontSize = computed(() => {
  const len = (current.value?.name || '').length;
  if (len > 14) return '26px';
  if (len > 9) return '34px';
  return '44px';
});

const words = ref([]);
const queue = ref([]);
const idx = ref(0);
const loading = ref(true);
const roundDone = ref(false);
const blind = ref(false);
const phase = ref('typing'); // 'typing' | 'reveal'
const shaking = ref(false);
const lastWrong = ref('');
const correctCount = ref(0);
const wrongCount = ref(0);
const wpm = ref(0);
const acc = ref(100);
const startTime = ref(0);
const elapsedSec = ref(0);
let timerId = null;
let engine = null;

const current = computed(() => queue.value[idx.value] || { name: '', trans: [] });
const letters = computed(() => (current.value.name || '').split(''));
const currentTrans = computed(() => (current.value.trans || []).join('；') || '（无释义）');
const nextKey = computed(() => (engine && phase.value === 'typing' ? engine.target[engine.cursor] || '' : ''));
const letterMask = computed(() => letters.value.map(() => '_').join(' '));

const elapsedText = computed(() => {
  const m = Math.floor(elapsedSec.value / 60);
  const s = String(elapsedSec.value % 60).padStart(2, '0');
  return `${m}:${s}`;
});

const gameKey = `dict-${props.ageGroup}`;

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function syncStats() {
  if (!engine) return;
  const s = engine.stats;
  wpm.value = s.wpm;
  acc.value = s.accuracy;
}

function startTimer() {
  stopTimer();
  startTime.value = Date.now();
  timerId = setInterval(() => {
    elapsedSec.value = Math.floor((Date.now() - startTime.value) / 1000);
  }, 1000);
}

function stopTimer() {
  if (timerId) clearInterval(timerId);
  timerId = null;
}

function loadWord() {
  engine = new TypingEngine(current.value.name, {
    strategy: 'strict',
    onUpdate: syncStats
  });
  phase.value = 'typing';
  if (!blind.value && speakable.value) speakCurrent();
}

async function loadDictById(id) {
  loading.value = true;
  try {
    const dict = dictOptions.find((d) => d.id === id);
    const list = await loadDict(dict);
    words.value = list.filter((w) => w.name && /^[a-zA-Z][a-zA-Z' -]*$/.test(w.name));
  } catch {
    words.value = [];
  } finally {
    loading.value = false;
  }
  restart();
}

function restart() {
  queue.value = shuffle(words.value).slice(0, ROUND_SIZE);
  idx.value = 0;
  correctCount.value = 0;
  wrongCount.value = 0;
  wpm.value = 0;
  acc.value = 100;
  elapsedSec.value = 0;
  roundDone.value = false;
  if (!queue.value.length) return;
  loadWord();
  startTimer();
}

function nextWord() {
  if (idx.value < queue.value.length - 1) {
    idx.value++;
    loadWord();
  } else {
    roundDone.value = true;
    stopTimer();
    cancelSpeak();
    recordGame(gameKey, {
      wpm: wpm.value,
      accuracy: acc.value,
      primaryKey: 'wpm'
    });
  }
}

function onKey(char) {
  if (roundDone.value || phase.value !== 'typing' || !engine) return;
  const res = engine.type(char);
  if (res.ok) {
    playCorrect();
    if (res.finished) {
      correctCount.value++;
      if (speakable.value) speakWordYoudao(current.value.name);
      // 打完单词 → 显示中文释义，停顿后下一词（默写模式略过展示）
      phase.value = 'reveal';
      playWin();
      setTimeout(nextWord, blind.value ? 350 : 1100);
    }
  } else {
    playWrong();
    wrongCount.value++;
    shaking.value = true;
    lastWrong.value = char;
    setTimeout(() => {
      shaking.value = false;
      lastWrong.value = '';
    }, 280);
  }
}

function skip() {
  if (phase.value !== 'typing') return;
  wrongCount.value++;
  nextWord();
}

function speakCurrent() {
  if (current.value.name) speakWordYoudao(current.value.name);
}

function onDictChange(e) {
  dictId.value = e.target.value;
  loadDictById(dictId.value);
}

function letterClass(i) {
  if (!engine) return '';
  if (engine.charStates[i] === 'correct') return 'ok';
  if (i === engine.cursor && phase.value === 'typing') return 'cur';
  return '';
}

const finalStats = computed(() => ({
  wpm: wpm.value,
  accuracy: acc.value,
  maxStreak: correctCount.value,
  correct: correctCount.value
}));
const record = computed(() => getRecord(gameKey));

function handleKeydown(e) {
  if (roundDone.value || loading.value) return;
  if (e.key === 'Backspace') {
    e.preventDefault();
    if (engine && phase.value === 'typing') engine.backspace();
    return;
  }
  // 放宽到全部可打印 ASCII：编程词条含 () . _ < > 等符号，保留原始大小写
  if (/^[\x20-\x7e]$/.test(e.key)) {
    e.preventDefault();
    onKey(e.key);
  }
}

onMounted(() => {
  loadDictById(dictId.value);
  window.addEventListener('keydown', handleKeydown);
});
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown);
  stopTimer();
  cancelSpeak();
});
</script>

<style scoped>
.dt {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  box-sizing: border-box;
  padding: 12px 16px 20px;
  gap: 12px;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.btn-back {
  border: none;
  background: none;
  font-size: 16px;
  color: #5f5e5a;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
  flex-shrink: 0;
}
.btn-back:hover {
  background: #f1efe8;
}
.dict-select {
  flex: 1;
  max-width: 260px;
  border: 1.5px solid #d3d1c7;
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 14px;
  color: #2c2c2a;
  background: #ffffff;
  cursor: pointer;
}
.live-stats {
  display: flex;
  gap: 8px;
}
.stat-pill {
  font-size: 13px;
  color: #444441;
  background: #f1efe8;
  padding: 4px 10px;
  border-radius: 20px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.dt-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.dt-loading {
  font-size: 15px;
  color: #888780;
}
.word-card {
  width: min(560px, 92vw);
  min-height: 220px;
  background: #ffffff;
  border: 2px solid #d3d1c7;
  border-radius: 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 28px 20px;
  position: relative;
}
.word-card.shake {
  animation: shake 0.28s;
  border-color: #f0997b;
}
@keyframes shake {
  25% { transform: translateX(-8px); }
  75% { transform: translateX(8px); }
}
.word-letters {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 2px;
  font-family: var(--font-mono, monospace);
}
.w-char {
  font-size: var(--word-size, 44px);
  font-weight: 500;
  color: #b4b2a9;
  transition: color 0.08s;
  line-height: 1.25;
}
.w-char.ok {
  color: #085041;
}
.w-char.cur {
  color: #185fa5;
  animation: caret 1.05s steps(1) infinite;
}
@keyframes caret {
  50% { background: #b5d4f4; }
}
.word-phonetic {
  font-size: 16px;
  color: #888780;
  font-family: var(--font-mono, monospace);
}
.word-reveal {
  font-size: 22px;
  color: #0f6e56;
  font-weight: 500;
}
.fade-enter-active {
  transition: opacity 0.25s, transform 0.25s;
}
.fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.word-blind .word-zh-main {
  font-size: 30px;
  color: #2c2c2a;
  font-weight: 500;
}
.word-blind .word-mask {
  font-size: 22px;
  color: #b4b2a9;
  letter-spacing: 4px;
  font-family: var(--font-mono, monospace);
}
.dt-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.btn-sound,
.btn-skip {
  border: 1.5px solid #d3d1c7;
  background: #ffffff;
  color: #444441;
  font-size: 13px;
  border-radius: 18px;
  padding: 6px 14px;
  cursor: pointer;
}
.blind-toggle {
  font-size: 13px;
  color: #444441;
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
}
.dt-progress {
  font-size: 13px;
  color: #888780;
}
</style>
