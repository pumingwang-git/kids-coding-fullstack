<template>
  <div class="home">
    <header class="home-head">
      <h1 class="home-title">打字星球</h1>
      <p class="home-sub">学生端工具箱 · 打字游戏</p>
      <div class="age-switch">
        <button
          v-for="opt in AGE_OPTIONS"
          :key="opt.value"
          class="age-btn"
          :class="{ active: age === opt.value }"
          type="button"
          @click="$emit('change-age', opt.value)"
        >
          {{ opt.label }}<small>{{ opt.sub }}</small>
        </button>
      </div>
    </header>

    <main class="home-main">
      <div class="mode-grid">
        <button
          v-for="m in modes"
          :key="m.key"
          class="mode-card"
          :class="`tone-${m.tone}`"
          type="button"
          @click="$emit('select', m.key)"
        >
          <span class="mode-icon">{{ m.icon }}</span>
          <span class="mode-title">{{ m.title }}</span>
          <span class="mode-desc">{{ m.desc }}</span>
          <span class="mode-go">开始 ›</span>
        </button>

        <div v-if="moreComing" class="mode-card tone-gray placeholder">
          <span class="mode-icon">🔧</span>
          <span class="mode-title">更多玩法</span>
          <span class="mode-desc">开发中，敬请期待</span>
        </div>
      </div>
    </main>

    <footer class="home-foot">
      <span>词库：qwerty-learner 开源词库（PEP/中考/高考/CET）· Monkeytype · Fry · Dolch</span>
    </footer>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { AGE_OPTIONS } from '../data/words.js';

const props = defineProps({
  age: { type: String, default: '7-12' }
});
defineEmits(['select', 'change-age']);

const MODES = {
  '3-6': [
    { key: 'letter', title: '字母乐园', desc: '打完一个字母，收集点亮一个', icon: '⭐', tone: 'teal' }
  ],
  '7-12': [
    { key: 'dict', title: '单词练习', desc: 'PEP 教材词库可选，打完单词显示中文', icon: '📖', tone: 'blue' },
    { key: 'pinyin', title: '拼音练习', desc: '打出拼音，拼出汉字', icon: '🔤', tone: 'blue' },
    { key: 'chinese', title: '中文打字', desc: '绕口令古诗，用输入法打汉字', icon: '🀄', tone: 'blue' }
  ],
  '13+': [
    { key: 'dict', title: '单词练习', desc: '中考/高考/四级词库，打完显示中文', icon: '📖', tone: 'amber' },
    { key: 'practice', title: '快速打字', desc: '开源英语词库，直接打字刷 WPM', icon: '⌨', tone: 'amber' },
    { key: 'chinese', title: '中文打字', desc: '名言古诗，用输入法打汉字', icon: '🀄', tone: 'amber' }
  ]
};

const modes = computed(() => MODES[props.age] || MODES['7-12']);
// 13+ 只有 1 个模式时展示"更多玩法"占位卡
const moreComing = computed(() => modes.value.length < 3);
</script>

<style scoped>
.home {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 24px 20px 16px;
  display: flex;
  flex-direction: column;
}
.home-head {
  text-align: center;
}
.home-title {
  margin: 0;
  font-size: 32px;
  color: #085041;
}
.home-sub {
  margin: 4px 0 16px;
  font-size: 13px;
  color: #5f5e5a;
}
.age-switch {
  display: inline-flex;
  background: #f1efe8;
  border-radius: 24px;
  padding: 4px;
  gap: 4px;
}
.age-btn {
  border: none;
  background: none;
  border-radius: 20px;
  padding: 8px 18px;
  font-size: 15px;
  color: #444441;
  cursor: pointer;
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.age-btn small {
  font-size: 11px;
  color: #888780;
}
.age-btn.active {
  background: #0f6e56;
  color: #ffffff;
}
.age-btn.active small {
  color: #d9f2e8;
}
.home-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
}
.mode-grid {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 16px;
  max-width: 640px;
}
.mode-card {
  width: 190px;
  min-height: 150px;
  border-radius: 18px;
  border: none;
  padding: 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  text-align: center;
  transition: transform 0.1s;
}
.mode-card:hover {
  transform: translateY(-3px);
}
.mode-card:active {
  transform: scale(0.97);
}
.mode-card.placeholder {
  cursor: default;
}
.tone-teal {
  background: #e1f5ee;
  border: 2px solid #0f6e56;
}
.tone-blue {
  background: #e6f1fb;
  border: 2px solid #185fa5;
}
.tone-amber {
  background: #faeeda;
  border: 2px solid #854f0b;
}
.tone-gray {
  background: #f1efe8;
  border: 2px dashed #b4b2a9;
}
.mode-icon {
  font-size: 38px;
  line-height: 1;
}
.mode-title {
  font-size: 18px;
  font-weight: 500;
}
.tone-teal .mode-title { color: #085041; }
.tone-blue .mode-title { color: #0c447c; }
.tone-amber .mode-title { color: #633806; }
.tone-gray .mode-title { color: #5f5e5a; }
.mode-desc {
  font-size: 12px;
  color: #5f5e5a;
}
.mode-go {
  margin-top: auto;
  font-size: 13px;
  font-weight: 500;
}
.tone-teal .mode-go { color: #0f6e56; }
.tone-blue .mode-go { color: #185fa5; }
.tone-amber .mode-go { color: #854f0b; }
.home-foot {
  text-align: center;
  font-size: 11px;
  color: #b4b2a9;
}
</style>
