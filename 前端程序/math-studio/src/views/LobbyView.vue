<script setup>
import { RouterLink } from "vue-router";
import { ArrowRight, CheckCircle2, Clock3, Gamepad2, LockKeyhole, Sparkles } from "@lucide/vue";
import { getUser } from "../platform/session";

const user = getUser();
const thinkingOtter = `${import.meta.env.BASE_URL}assets/otter-thinking-720.webp`;
</script>

<template>
  <main class="lobby-page">
    <header class="site-bar lobby-bar">
      <RouterLink class="brand-lockup" to="/" aria-label="数学星球首页">
        <span class="brand-mark" aria-hidden="true">Σ</span>
        <span>数学星球</span>
      </RouterLink>
      <div class="student-chip">
        <span class="student-dot" aria-hidden="true"></span>
        {{ user?.username || "同学" }}
      </div>
    </header>

    <section class="entry-stage" aria-labelledby="lobby-title">
      <div class="entry-heading">
        <span class="entry-mark" aria-hidden="true">Σ</span>
        <h1 id="lobby-title">数学星球</h1>
        <p>选一个任务，开始你的数字冒险</p>
      </div>

      <div class="game-choices">
        <RouterLink class="active-mission" to="/games/24/play">
          <span class="mission-number" aria-hidden="true">24</span>
          <span class="mission-detail">
            <span class="mission-status"><CheckCircle2 :size="16" />可以开始</span>
            <strong>24 点</strong>
            <span>四个数字各用一次，拼出等于 24 的算式。</span>
            <span class="mission-facts" aria-label="24 点玩法"><span><Gamepad2 :size="16" />自由练习</span><span><Clock3 :size="16" />60 秒挑战</span><span><Sparkles :size="16" />三档难度</span></span>
          </span>
          <span class="mission-launch">进入<ArrowRight :size="20" /></span>
        </RouterLink>

        <div class="future-bay" aria-labelledby="future-title">
          <div class="future-icon" aria-hidden="true"><LockKeyhole :size="23" /></div>
          <div><h2 id="future-title">更多数学任务</h2><p>正在准备中，新的规则和玩法完成后开放。</p></div>
        </div>
      </div>

      <img class="entry-otter" :src="thinkingOtter" alt="正在思考数字任务的水獭领航员" />
    </section>
  </main>
</template>
