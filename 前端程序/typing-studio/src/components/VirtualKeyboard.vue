<template>
  <div class="vk" role="group" aria-label="虚拟键盘">
    <div v-for="(row, ri) in rows" :key="ri" class="vk-row">
      <button
        v-for="k in row"
        :key="k"
        class="vk-key"
        :class="{ hot: k === hotKey, miss: k === lastWrong }"
        type="button"
        @click="$emit('key', k)"
      >
        {{ k }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  // 当前应按的键（小写字母），高亮提示
  highlight: { type: String, default: '' },
  // 最近按错的键，短暂标红提示
  lastWrong: { type: String, default: '' }
});
defineEmits(['key']);

const rows = [
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm']
];

const hotKey = computed(() => (props.highlight || '').toLowerCase());
</script>

<style scoped>
.vk {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  background: #f1efe8;
  border-radius: 14px;
  user-select: none;
}
.vk-row {
  display: flex;
  gap: 6px;
  justify-content: center;
}
.vk-key {
  min-width: 40px;
  height: 44px;
  border: none;
  border-radius: 8px;
  background: #ffffff;
  color: #444441;
  font-size: 18px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 2px 0 #d3d1c7;
  transition: transform 0.06s;
}
.vk-key:active {
  transform: translateY(2px);
  box-shadow: none;
}
.vk-key.hot {
  background: #9fe1cb;
  color: #085041;
  box-shadow: 0 2px 0 #0f6e56;
  transform: scale(1.12);
}
.vk-key.miss {
  background: #f7c1c1;
  color: #791f1f;
}
</style>
