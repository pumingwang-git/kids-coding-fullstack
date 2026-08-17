<template>
  <div class="lp">
    <header class="topbar">
      <button class="btn-back" type="button" @click="$emit('home')">‹ 返回</button>
      <span class="stage-name">{{ phase === 'letter' ? '字母乐园' : '单词乐园' }}</span>
      <button class="btn-sound" type="button" @click="playCurrent">🔊 听发音</button>
    </header>

    <!-- 收集行：打对一个点亮一个 -->
    <div class="collect-row" :class="phase">
      <span
        v-for="(item, i) in collectList"
        :key="i"
        class="collect-chip"
        :class="{ lit: i < collectDone, current: i === collectDone }"
      >{{ phase === 'letter' ? item : '·' }}</span>
    </div>

    <main class="lp-main">
      <template v-if="!finished">
        <!-- 字母固定在屏幕正中央 -->
        <div class="center-card" :class="{ shake: shaking, glow: glowing }">
          <span class="center-letter">{{ current.display }}</span>
          <span v-if="current.type === 'word'" class="center-zh">打完整单词</span>
          <div v-else class="center-case">
            <span class="case">{{ current.value }}</span>
            <span class="case upper">{{ current.value.toUpperCase() }}</span>
          </div>
        </div>
        <div class="lp-tip">按键盘（或点下面键盘）上高亮的键</div>
      </template>

      <div v-else class="lp-done">
        <h2>太棒了！</h2>
        <div class="done-stars">
          <span v-for="i in Math.min(total, 30)" :key="i" class="mini-star">★</span>
        </div>
        <p class="done-text">你收集了全部 {{ total }} 个！</p>
        <div class="done-actions">
          <button class="btn btn-primary" type="button" @click="restart">再玩一次</button>
          <button class="btn btn-ghost" type="button" @click="$emit('home')">换个模式</button>
        </div>
      </div>
    </main>

    <VirtualKeyboard
      v-if="!finished"
      :highlight="nextKey"
      :last-wrong="lastWrong"
      @key="onKey"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import VirtualKeyboard from '../components/VirtualKeyboard.vue';
import { TypingEngine } from '../engine/typingEngine.js';
import { LETTERS } from '../data/words.js';
import { DOLCH_PRE_PRIMER } from '../data/dolch.js';
import { speak, speakLetter, cancelSpeak } from '../utils/speech.js';
import { playCorrect, playWrong, playWin, playStar } from '../utils/audio.js';
import { recordGame, getRecord } from '../utils/storage.js';

defineEmits(['home']);

const LETTER_TOTAL = LETTERS.length; // 26
const WORD_COUNT = 10;
const total = LETTER_TOTAL + WORD_COUNT;

const phase = ref('letter'); // 'letter' | 'word'
const letterIdx = ref(0);
const wordList = ref([]);
const wordIdx = ref(0);
const finished = ref(false);
const shaking = ref(false);
const glowing = ref(false);
const lastWrong = ref('');
let engine = null;

const current = computed(() => {
  if (phase.value === 'letter') {
    return { type: 'letter', value: LETTERS[letterIdx.value], display: LETTERS[letterIdx.value] };
  }
  const w = wordList.value[wordIdx.value];
  return { type: 'word', value: w, display: w };
});

// 收集行数据：字母阶段显示 26 字母，单词阶段显示 10 个点（逐词点亮）
const collectList = computed(() =>
  phase.value === 'letter' ? LETTERS : Array.from({ length: WORD_COUNT }, () => '')
);
const collectDone = computed(() => (phase.value === 'letter' ? letterIdx.value : wordIdx.value));

const nextKey = computed(() => (engine ? engine.target[engine.cursor] || '' : ''));

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function loadQuestion() {
  shaking.value = false;
  engine = new TypingEngine(current.value.value, { strategy: 'strict' });
  playCurrent();
}

function advance() {
  if (phase.value === 'letter') {
    if (letterIdx.value < LETTER_TOTAL - 1) {
      letterIdx.value++;
      loadQuestion();
    } else {
      phase.value = 'word';
      wordList.value = shuffle(DOLCH_PRE_PRIMER.filter((w) => w.length > 1)).slice(0, WORD_COUNT);
      wordIdx.value = 0;
      loadQuestion();
    }
    return;
  }
  if (wordIdx.value < wordList.value.length - 1) {
    wordIdx.value++;
    loadQuestion();
  } else {
    finished.value = true;
    cancelSpeak();
    recordGame('letter-paradise', { stars: total, accuracy: 100 });
  }
}

function onKey(char) {
  if (finished.value || glowing.value || !engine) return;
  const res = engine.type(char);
  if (res.ok) {
    if (engine.finished) {
      // 收集点亮：中央卡片发光，星星音效，然后出下一个
      glowing.value = true;
      playWin();
      playStar();
      setTimeout(() => {
        glowing.value = false;
        advance();
      }, 520);
    } else {
      playCorrect();
    }
  } else {
    playWrong();
    shaking.value = true;
    lastWrong.value = char;
    setTimeout(() => {
      shaking.value = false;
      lastWrong.value = '';
    }, 320);
  }
}

function playCurrent() {
  if (current.value.type === 'letter') {
    speakLetter(current.value.value);
  } else {
    speak(current.value.value, { lang: 'en-US', rate: 0.75 });
  }
}

function handleKeydown(e) {
  if (finished.value) return;
  const k = e.key.toLowerCase();
  if (/^[a-z]$/.test(k)) {
    e.preventDefault();
    onKey(k);
  } else if (e.key === 'Backspace' && engine) {
    e.preventDefault();
    engine.backspace();
  }
}

function restart() {
  phase.value = 'letter';
  letterIdx.value = 0;
  wordIdx.value = 0;
  wordList.value = [];
  finished.value = false;
  loadQuestion();
}

onMounted(() => {
  loadQuestion();
  window.addEventListener('keydown', handleKeydown);
});
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown);
  cancelSpeak();
});
</script>

<style scoped>
.lp {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  box-sizing: border-box;
  padding: 12px 16px 20px;
  gap: 10px;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.btn-back {
  border: none;
  background: none;
  font-size: 16px;
  color: #0f6e56;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
}
.btn-back:hover {
  background: #e1f5ee;
}
.stage-name {
  font-size: 18px;
  font-weight: 500;
  color: #085041;
}
.btn-sound {
  border: 2px solid #0f6e56;
  background: #ffffff;
  color: #085041;
  font-size: 14px;
  border-radius: 20px;
  padding: 6px 16px;
  cursor: pointer;
}
.collect-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  justify-content: center;
  padding: 8px 4px;
  min-height: 34px;
}
.collect-chip {
  width: 24px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  font-size: 15px;
  font-weight: 500;
  background: #f1efe8;
  color: #b4b2a9;
  transition: all 0.25s;
}
.collect-chip.lit {
  background: #9fe1cb;
  color: #085041;
}
.collect-chip.current {
  background: #e1f5ee;
  color: #0f6e56;
  box-shadow: 0 0 0 2px #1d9e75;
}
.lp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
}
.center-card {
  width: min(320px, 80vw);
  min-height: 240px;
  background: #ffffff;
  border: 3px solid #9fe1cb;
  border-radius: 26px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: transform 0.18s, border-color 0.18s, box-shadow 0.18s;
}
.center-card.shake {
  animation: shake 0.3s;
  border-color: #f0997b;
}
@keyframes shake {
  25% { transform: translateX(-10px); }
  75% { transform: translateX(10px); }
}
.center-card.glow {
  border-color: #ef9f27;
  box-shadow: 0 0 0 8px #faeeda;
  transform: scale(1.05);
}
.center-letter {
  font-size: 96px;
  font-weight: 500;
  color: #085041;
  line-height: 1.1;
}
.center-case {
  display: flex;
  gap: 22px;
  font-size: 34px;
}
.case {
  color: #b4b2a9;
}
.case.upper {
  color: #5dcaa5;
}
.center-zh {
  font-size: 15px;
  color: #888780;
}
.lp-tip {
  font-size: 14px;
  color: #5f5e5a;
}
.lp-done {
  text-align: center;
  padding: 40px 16px;
}
.lp-done h2 {
  font-size: 26px;
  color: #085041;
  margin: 0 0 12px;
}
.done-stars {
  font-size: 18px;
  color: #ef9f27;
  line-height: 1.8;
  margin-bottom: 12px;
}
.mini-star {
  margin: 0 2px;
}
.done-text {
  font-size: 15px;
  color: #444441;
  margin: 0 0 20px;
}
.done-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
.btn {
  border: none;
  border-radius: 10px;
  padding: 10px 22px;
  font-size: 15px;
  cursor: pointer;
}
.btn-primary {
  background: #0f6e56;
  color: #fff;
}
.btn-ghost {
  background: #f1efe8;
  color: #444441;
}
</style>
