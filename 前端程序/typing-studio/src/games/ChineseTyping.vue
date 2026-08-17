<template>
  <div class="ct">
    <header class="topbar">
      <button class="btn-back" type="button" @click="$emit('home')">‹ 返回</button>
      <select class="text-select" :value="textId" @change="onTextChange">
        <option v-for="t in CHINESE_TEXTS" :key="t.id" :value="t.id">{{ t.name }}</option>
      </select>
      <div class="live-stats">
        <span class="stat-pill">{{ cpm }} 字/分</span>
        <span class="stat-pill">{{ acc }}% 准</span>
      </div>
    </header>

    <main class="ct-main">
      <div v-if="!finished" class="cn-text">
        <span
          v-for="(ch, i) in chars"
          :key="i"
          class="c-char"
          :class="charClass(i)"
        >{{ ch }}</span>
      </div>

      <!-- 真实输入框：拼音输入法在这里正常工作，打的是汉字 -->
      <textarea
        v-if="!finished"
        ref="inputEl"
        class="cn-input"
        v-model="input"
        :placeholder="'用输入法打出上面的文字…'"
        autofocus
      ></textarea>

      <ResultPanel
        v-else
        title="完成！"
        :stats="finalStats"
        :record="record"
        @retry="restart"
        @home="$emit('home')"
      />
    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import ResultPanel from '../components/ResultPanel.vue';
import { CHINESE_TEXTS } from '../data/chinese.js';
import { recordGame, getRecord } from '../utils/storage.js';

defineEmits(['home']);

const textId = ref(CHINESE_TEXTS[0].id);
const target = ref(CHINESE_TEXTS[0].text);
const input = ref('');
const finished = ref(false);
const startTime = ref(0);
const endTime = ref(0);
const inputEl = ref(null);

const chars = computed(() => target.value.split(''));
const cursor = computed(() => input.value.length);

const correctCount = computed(() => {
  let n = 0;
  const v = input.value;
  for (let i = 0; i < v.length && i < target.value.length; i++) {
    if (v[i] === target.value[i]) n++;
  }
  return n;
});

const cpm = computed(() => {
  const end = endTime.value || Date.now();
  const mins = (end - startTime.value) / 60000;
  return mins > 0 ? Math.round(correctCount.value / mins) : 0;
});

const acc = computed(() =>
  input.value.length ? Math.round((correctCount.value / input.value.length) * 100) : 100
);

function charClass(i) {
  if (i >= input.value.length) return i === input.value.length ? 'cur' : '';
  return input.value[i] === target.value[i] ? 'ok' : 'err';
}

watch(input, (val) => {
  if (!startTime.value && val.length) startTime.value = Date.now();
  if (val.length >= target.value.length) {
    endTime.value = Date.now();
    finished.value = true;
    recordGame('chinese', {
      wpm: cpm.value,
      accuracy: acc.value,
      primaryKey: 'wpm'
    });
  }
});

function onTextChange(e) {
  const t = CHINESE_TEXTS.find((x) => x.id === e.target.value);
  textId.value = t.id;
  target.value = t.text;
  restart();
}

function restart() {
  input.value = '';
  finished.value = false;
  startTime.value = 0;
  endTime.value = 0;
  nextTick(() => inputEl.value && inputEl.value.focus());
}

const finalStats = computed(() => ({
  wpm: cpm.value,
  accuracy: acc.value,
  maxStreak: correctCount.value
}));
const record = computed(() => getRecord('chinese'));

onMounted(() => nextTick(() => inputEl.value && inputEl.value.focus()));
</script>

<style scoped>
.ct {
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
.text-select {
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
}
.ct-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.cn-text {
  width: min(680px, 94vw);
  font-size: 26px;
  line-height: 2;
  letter-spacing: 2px;
  color: #b4b2a9;
  padding: 24px 28px;
  background: #ffffff;
  border: 1.5px solid #e8e6dd;
  border-radius: 16px;
  user-select: none;
}
.c-char.ok {
  color: #085041;
}
.c-char.err {
  color: #e24b4a;
  background: #fcebeb;
}
.c-char.cur {
  color: #185fa5;
  animation: caret 1.05s steps(1) infinite;
}
@keyframes caret {
  50% { background: #b5d4f4; }
}
.cn-input {
  width: min(680px, 94vw);
  min-height: 90px;
  font-size: 20px;
  line-height: 1.8;
  padding: 14px 18px;
  border: 2px solid #d3d1c7;
  border-radius: 14px;
  resize: vertical;
  font-family: inherit;
  color: #2c2c2a;
}
.cn-input:focus {
  outline: none;
  border-color: #185fa5;
}
</style>
