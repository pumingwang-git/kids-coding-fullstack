<template>
  <div class="pp">
    <header class="topbar">
      <button class="btn-back" type="button" @click="$emit('home')">‹ 返回</button>
      <span class="stage-name">拼音练习</span>
      <span class="stage-progress">{{ index + 1 }} / {{ items.length }}</span>
    </header>

    <main class="pp-main">
      <template v-if="!finished">
        <div class="py-card" :class="{ shake: shaking }">
          <div class="py-char">{{ current.cn }}</div>
          <div class="py-pinyin">
            <span v-for="(ch, i) in current.py.split('')" :key="i" class="p-char" :class="pyStateClass(i)">
              {{ engine && engine.typedChars[i] ? engine.typedChars[i] : (pyStateClass(i) === 'done' ? ch : '_') }}
            </span>
          </div>
          <button class="btn-sound" type="button" @click="speakCurrent">🔊 听读音</button>
        </div>
        <div class="pp-tip">用拼音打出这个汉字（不带声调）</div>
      </template>

      <ResultPanel
        v-else
        title="拼音小能手！"
        :stats="finalStats"
        :record="record"
        @retry="restart"
        @home="$emit('home')"
      />
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
import ResultPanel from '../components/ResultPanel.vue';
import { TypingEngine } from '../engine/typingEngine.js';
import { PINYIN_WORDS } from '../data/words.js';
import { speak, cancelSpeak } from '../utils/speech.js';
import { playCorrect, playWrong, playWin } from '../utils/audio.js';
import { recordGame, getRecord } from '../utils/storage.js';

defineEmits(['home']);

const items = ref([]);
const index = ref(0);
const finished = ref(false);
const shaking = ref(false);
const lastWrong = ref('');
let engine = null;
let correctCount = 0;

const current = computed(() => items.value[index.value] || { cn: '', py: '' });
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
  engine = new TypingEngine(current.value.py, { strategy: 'strict' });
  speakCurrent();
}

function pyStateClass(i) {
  if (!engine) return '';
  if (engine.charStates[i] === 'correct') return 'done';
  if (i === engine.cursor) return 'cur';
  return '';
}

function speakCurrent() {
  speak(current.value.cn, { lang: 'zh-CN', rate: 0.7 });
}

function onKey(char) {
  if (finished.value || !engine) return;
  const res = engine.type(char);
  if (res.ok) {
    if (engine.finished) {
      playWin();
      correctCount++;
      setTimeout(next, 600);
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
    }, 300);
  }
}

function next() {
  if (index.value < items.value.length - 1) {
    index.value++;
    loadQuestion();
  } else {
    finished.value = true;
    cancelSpeak();
    recordGame('pinyin', {
      wpm: Math.round(correctCount / 0.5),
      accuracy: Math.round((correctCount / items.value.length) * 100),
      primaryKey: 'accuracy'
    });
  }
}

const finalStats = computed(() => ({
  wpm: Math.round(correctCount / 0.5),
  accuracy: Math.round((correctCount / Math.max(items.value.length, 1)) * 100),
  maxStreak: correctCount,
  correct: correctCount
}));

const record = computed(() => getRecord('pinyin'));

function restart() {
  items.value = shuffle(PINYIN_WORDS).slice(0, 10);
  index.value = 0;
  finished.value = false;
  correctCount = 0;
  loadQuestion();
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

onMounted(() => {
  restart();
  window.addEventListener('keydown', handleKeydown);
});
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown);
  cancelSpeak();
});
</script>

<style scoped>
.pp {
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
}
.btn-back {
  border: none;
  background: none;
  font-size: 16px;
  color: #854f0b;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
}
.btn-back:hover {
  background: #faeeda;
}
.stage-name {
  font-size: 18px;
  font-weight: 500;
  color: #633806;
}
.stage-progress {
  font-size: 14px;
  color: #5f5e5a;
  background: #f1efe8;
  padding: 4px 12px;
  border-radius: 20px;
}
.pp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.py-card {
  width: min(420px, 92vw);
  background: #ffffff;
  border: 2px solid #fac775;
  border-radius: 20px;
  padding: 28px 20px;
  text-align: center;
}
.py-card.shake {
  animation: shake 0.3s;
}
@keyframes shake {
  25% { transform: translateX(-8px); }
  75% { transform: translateX(8px); }
}
.py-char {
  font-size: 72px;
  color: #633806;
  line-height: 1.2;
  margin-bottom: 14px;
}
.py-pinyin {
  display: flex;
  justify-content: center;
  gap: 6px;
  min-height: 50px;
  margin-bottom: 16px;
}
.p-char {
  width: 30px;
  height: 44px;
  line-height: 44px;
  font-size: 24px;
  font-weight: 500;
  border-bottom: 3px solid #d3d1c7;
  color: #2c2c2a;
}
.p-char.done {
  border-color: #ba7517;
  color: #854f0b;
}
.p-char.cur {
  border-color: #185fa5;
  color: #185fa5;
}
.btn-sound {
  border: 2px solid #854f0b;
  background: #ffffff;
  color: #633806;
  font-size: 14px;
  border-radius: 20px;
  padding: 6px 18px;
  cursor: pointer;
}
.pp-tip {
  font-size: 14px;
  color: #5f5e5a;
}
</style>
