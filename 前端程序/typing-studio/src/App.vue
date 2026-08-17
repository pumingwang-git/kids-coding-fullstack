<template>
  <!-- mode=home → 模式选择首页；否则渲染对应游戏 -->
  <HomeView v-if="mode === 'home'" :age="age" @select="startMode" @change-age="changeAge" />
  <component
    :is="gameComponent"
    v-else
    :age-group="age"
    @home="goHome"
  />
</template>

<script setup>
import { ref, computed } from 'vue';
import HomeView from './components/HomeView.vue';
import LetterParadise from './games/LetterParadise.vue';
import PinyinPractice from './games/PinyinPractice.vue';
import TypingPractice from './games/TypingPractice.vue';
import DictTyping from './games/DictTyping.vue';
import ChineseTyping from './games/ChineseTyping.vue';
import { getQuery, setQuery } from './utils/query.js';

// URL 约定：/typing-studio/?age=7-12&mode=dict
// age: 3-6 | 7-12 | 13+    mode: home | letter | pinyin | dict | practice | chinese
const age = ref(getQuery('age') || '7-12');
const mode = ref(getQuery('mode') || 'home');

const GAME_MAP = {
  letter: LetterParadise,
  pinyin: PinyinPractice,
  dict: DictTyping,
  practice: TypingPractice,
  chinese: ChineseTyping
};

const gameComponent = computed(() => GAME_MAP[mode.value] || null);

function startMode(m) {
  mode.value = m;
  setQuery('mode', m);
}

function changeAge(a) {
  age.value = a;
  mode.value = 'home';
  setQuery('age', a);
  setQuery('mode', 'home');
}

function goHome() {
  mode.value = 'home';
  setQuery('mode', 'home');
}
</script>
