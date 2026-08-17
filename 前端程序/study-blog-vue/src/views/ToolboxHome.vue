<script setup>
// 工具箱中的已上线项目都作为独立子应用在新标签页打开。

const tools = [
  {
    key: "typing",
    title: "打字星球",
    desc: "3-6 岁字母乐园 · 单词打字 · 中文打字 · 编程词库。PEP 教材/中考/高考/CET 全词库，默写模式、错题本、数据统计",
    icon: "⌨️",
    tag: "已上线",
    active: true,
    ages: ["3-6 岁", "7-12 岁", "13+"],
    href: "/typing-studio-qwerty/",
  },
  {
    key: "math",
    title: "数学星球",
    desc: "四个数字各用一次，选择自由探索或 60 秒冲刺，拼出刚好等于 24 的算式",
    icon: "24",
    tag: "7–12 岁",
    active: true,
    ages: [],
    href: "/math-studio/",
  },
  {
    key: "focus",
    title: "专注星球",
    desc: "小番茄番茄钟：15 分钟专心学，任务清单 + 专注记录，劳逸结合更高效",
    icon: "🍅",
    tag: "已上线",
    active: true,
    ages: ["7-12 岁", "13+"],
    href: "/focus-studio/",
  },
];

function openTool(tool) {
  if (!tool.active) return;
  window.open(tool.href, "_blank");
}
</script>

<template>
  <main class="kids-page toolbox-page">
    <header class="kids-page-heading toolbox-heading">
      <div>
        <h1>工具箱</h1>
        <span>
          轻量学习工具集合：打字、口算、换算……即开即用，边玩边练。
          第一个工具「打字星球」已经上线，去试试手速吧！
        </span>
      </div>
    </header>

    <section class="toolbox-grid">
      <article
        v-for="tool in tools"
        :key="tool.key"
        class="tool-card"
        :class="{ active: tool.active, disabled: !tool.active }"
        @click="openTool(tool)"
      >
        <div class="tool-icon">{{ tool.icon }}</div>
        <div class="tool-body">
          <div class="tool-title-row">
            <h2>{{ tool.title }}</h2>
            <span class="tool-tag" :class="{ on: tool.active }">{{ tool.tag }}</span>
          </div>
          <p class="tool-desc">{{ tool.desc }}</p>
          <div v-if="tool.ages.length" class="tool-ages">
            <span v-for="a in tool.ages" :key="a" class="age-chip">{{ a }}</span>
          </div>
        </div>
        <button class="tool-action" :disabled="!tool.active">
          {{ tool.active ? "开始游戏 ›" : "敬请期待" }}
        </button>
      </article>
    </section>
  </main>
</template>

<style scoped>
.toolbox-heading {
  --area-surface: #e1f5ee;
}
.toolbox-grid {
  margin-top: 28px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}
.tool-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: #ffffff;
  border: 1px solid #e4e2da;
  border-radius: 20px;
  padding: 24px;
  transition:
    transform 0.12s,
    box-shadow 0.12s;
}
.tool-card.active {
  cursor: pointer;
  border-color: #9fe1cb;
  box-shadow: 0 6px 20px rgba(15, 110, 86, 0.1);
}
.tool-card.active:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 26px rgba(15, 110, 86, 0.16);
}
.tool-card.disabled {
  background: #f8f7f3;
  opacity: 0.62;
}
.tool-icon {
  font-size: 40px;
  line-height: 1;
}
.tool-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.tool-title-row h2 {
  margin: 0;
  font-size: 20px;
  color: #2c2c2a;
}
.tool-tag {
  font-size: 12px;
  color: #888780;
  background: #f1efe8;
  border-radius: 20px;
  padding: 3px 10px;
}
.tool-tag.on {
  color: #085041;
  background: #e1f5ee;
}
.tool-desc {
  margin: 0;
  font-size: 14px;
  color: #5f5e5a;
  line-height: 1.7;
}
.tool-ages {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.age-chip {
  font-size: 12px;
  color: #0f6e56;
  background: #f2faf6;
  border: 1px solid #9fe1cb;
  border-radius: 20px;
  padding: 2px 10px;
}
.tool-action {
  margin-top: auto;
  border: none;
  border-radius: 12px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  background: #e1f5ee;
  color: #085041;
}
.tool-action:disabled {
  background: #f1efe8;
  color: #888780;
  cursor: not-allowed;
}
</style>
