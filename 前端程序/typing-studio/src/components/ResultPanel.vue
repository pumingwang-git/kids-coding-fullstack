<template>
  <div class="result-overlay">
    <div class="result-card">
      <h2 class="result-title">{{ title }}</h2>
      <div class="result-stars" aria-label="星星评级">
        <span v-for="i in 3" :key="i" class="star" :class="{ on: i <= stars }">★</span>
      </div>
      <div class="result-grid">
        <div class="stat">
          <b>{{ stats.wpm }}</b>
          <span>WPM 速度</span>
        </div>
        <div class="stat">
          <b>{{ stats.accuracy }}%</b>
          <span>准确率</span>
        </div>
        <div class="stat">
          <b>{{ stats.maxStreak }}</b>
          <span>最高连击</span>
        </div>
      </div>
      <p v-if="record" class="result-record">最佳成绩：{{ record.best.wpm }} WPM · {{ record.best.accuracy }}%（已玩 {{ record.count }} 次）</p>
      <div class="result-actions">
        <button class="btn btn-primary" type="button" @click="$emit('retry')">再玩一次</button>
        <button class="btn btn-ghost" type="button" @click="$emit('home')">换个模式</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  title: { type: String, default: '完成啦' },
  stats: { type: Object, required: true },
  record: { type: Object, default: null }
});
defineEmits(['retry', 'home']);

const stars = computed(() => {
  const { accuracy } = props.stats;
  if (accuracy >= 95) return 3;
  if (accuracy >= 85) return 2;
  if (accuracy >= 70) return 1;
  return 1;
});
</script>

<style scoped>
.result-overlay {
  position: fixed;
  inset: 0;
  background: rgba(44, 44, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.result-card {
  width: min(420px, 90vw);
  background: #ffffff;
  border-radius: 20px;
  padding: 28px 24px;
  text-align: center;
}
.result-title {
  margin: 0 0 10px;
  font-size: 22px;
  color: #2c2c2a;
}
.result-stars {
  font-size: 34px;
  letter-spacing: 6px;
  margin-bottom: 16px;
}
.star {
  color: #d3d1c7;
}
.star.on {
  color: #ef9f27;
}
.result-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}
.stat {
  background: #f1efe8;
  border-radius: 12px;
  padding: 12px 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stat b {
  font-size: 22px;
  color: #085041;
}
.stat span {
  font-size: 12px;
  color: #5f5e5a;
}
.result-record {
  font-size: 12px;
  color: #5f5e5a;
  margin: 0 0 14px;
}
.result-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}
.btn {
  border: none;
  border-radius: 10px;
  padding: 10px 20px;
  font-size: 15px;
  cursor: pointer;
}
.btn-primary {
  background: #0f6e56;
  color: #ffffff;
}
.btn-ghost {
  background: #f1efe8;
  color: #444441;
}
</style>
