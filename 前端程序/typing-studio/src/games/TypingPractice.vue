<template>
  <div class="tp">
    <header class="topbar">
      <button class="btn-back" type="button" @click="$emit('home')">‹ 返回</button>
      <span class="stage-name">{{ title }}</span>
      <div class="live-stats">
        <span class="stat-pill">{{ wpm }} WPM</span>
        <span class="stat-pill">{{ acc }}% 准</span>
        <span class="stat-pill">连击 {{ streak }}</span>
      </div>
    </header>

    <main class="tp-main">
      <div v-if="!finished" class="text-flow" @click="focusHint = true">
        <span
          v-for="(ch, i) in chars"
          :key="i"
          class="t-char"
          :class="charClass(i)"
        >{{ ch }}</span>
      </div>

      <div v-if="!finished" class="tp-tip">
        直接打字 · 打错标红可以继续往后打 · 退格可回头改
      </div>

      <ResultPanel
        v-else
        title="完成！"
        :stats="finalStats"
        :record="record"
        @retry="restart"
        @home="$emit('home')"
      />
    </main>

    <VirtualKeyboard
      v-if="!finished && showKeyboard"
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
import { FRY_100, FRY_SECOND_100 } from '../data/fry.js';
import ENGLISH from '../data/english.json';
import { playCorrect, playWrong, playWin } from '../utils/audio.js';
import { recordGame, getRecord } from '../utils/storage.js';

const props = defineProps({
  // '7-12' → Fry 儿童高频词；'13+' → Monkeytype 开源英语词库
  ageGroup: { type: String, default: '13+' }
});
defineEmits(['home']);

const isKids = props.ageGroup === '7-12';
const title = isKids ? '单词练习' : '快速打字';
// 7-12 保留虚拟键盘（指法提示+触屏），13+ 纯键盘
const showKeyboard = isKids;
const WORD_COUNT = isKids ? 15 : 25;

const target = ref('');
const chars = computed(() => target.value.split(''));
const finished = ref(false);
const wpm = ref(0);
const acc = ref(100);
const streak = ref(0);
const lastWrong = ref('');
let engine = null;

const gameKey = isKids ? 'practice-kids' : 'practice-13';

const nextKey = computed(() => (engine ? engine.target[engine.cursor] || '' : ''));

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function buildTarget() {
  const pool = isKids ? [...FRY_100, ...FRY_SECOND_100] : ENGLISH.words;
  return shuffle(pool).slice(0, WORD_COUNT).join(' ').toLowerCase();
}

function syncStats() {
  if (!engine) return;
  const s = engine.stats;
  wpm.value = s.wpm;
  acc.value = s.accuracy;
  streak.value = s.streak;
}

function load() {
  target.value = buildTarget();
  finished.value = false;
  wpm.value = 0;
  acc.value = 100;
  streak.value = 0;
  engine = new TypingEngine(target.value, {
    strategy: 'flow',
    onUpdate: syncStats
  });
}

function onKey(char) {
  if (finished.value || !engine) return;
  const res = engine.type(char);
  if (res.ok) {
    playCorrect();
  } else {
    playWrong();
    lastWrong.value = char;
    setTimeout(() => (lastWrong.value = ''), 260);
  }
  if (res.finished) {
    finished.value = true;
    playWin();
    recordGame(gameKey, {
      wpm: engine.stats.wpm,
      accuracy: engine.stats.accuracy,
      primaryKey: 'wpm'
    });
  }
}

function charClass(i) {
  if (!engine) return '';
  const s = engine.charStates[i];
  if (s === 'correct') return 'ok';
  if (s === 'incorrect') return 'err';
  if (i === engine.cursor) return 'cur';
  return '';
}

const finalStats = computed(() => (engine ? engine.stats : { wpm: 0, accuracy: 100, maxStreak: 0 }));
const record = computed(() => getRecord(gameKey));

function handleKeydown(e) {
  if (finished.value) return;
  if (e.key === 'Backspace') {
    e.preventDefault();
    if (engine) engine.backspace();
    return;
  }
  // 接受字母与空格
  const k = e.key.toLowerCase();
  if (/^[a-z ]$/.test(k)) {
    e.preventDefault();
    onKey(k);
  }
}

function restart() {
  load();
}

onMounted(() => {
  load();
  window.addEventListener('keydown', handleKeydown);
});
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown);
});
</script>

<style scoped>
.tp {
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
  color: #5f5e5a;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
}
.btn-back:hover {
  background: #f1efe8;
}
.stage-name {
  font-size: 18px;
  font-weight: 500;
  color: #2c2c2a;
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
}
.tp-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.text-flow {
  width: min(760px, 94vw);
  font-family: var(--font-mono, monospace);
  font-size: 26px;
  line-height: 2.1;
  letter-spacing: 0.5px;
  color: #b4b2a9;
  padding: 24px 28px;
  background: #ffffff;
  border: 1.5px solid #e8e6dd;
  border-radius: 16px;
  min-height: 140px;
  cursor: text;
  user-select: none;
}
.t-char {
  transition: color 0.06s, background-color 0.06s;
}
.t-char.ok {
  color: #2c2c2a;
}
.t-char.err {
  color: #e24b4a;
  background: #fcebeb;
  border-radius: 3px;
}
.t-char.cur {
  position: relative;
  color: #185fa5;
  animation: caret 1.05s steps(1) infinite;
}
@keyframes caret {
  50% { background: #b5d4f4; }
}
.tp-tip {
  font-size: 13px;
  color: #888780;
  text-align: center;
}
</style>
