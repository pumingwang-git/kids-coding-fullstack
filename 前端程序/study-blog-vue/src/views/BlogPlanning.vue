<script setup>
const topics = [
  ["开发日志", "记录功能为什么这样设计，以及每个阶段的真实进展。"],
  ["前后端实践", "整理 Vue、FastAPI、接口契约与权限边界中的经验。"],
  ["学习笔记", "把值得复习的概念变成可以再次查阅的说明。"],
  ["部署与排错", "保留问题现象、定位证据、修复过程和验收结果。"],
];
</script>

<template>
  <main class="portal-page blog-planning portal-section">
    <header class="page-intro blog-intro">
      <div>
        <span class="status-planning">正在筹备</span>
        <h1>先把真实经验积累下来，<br />再认真开始写博客</h1>
        <p>目前还没有正式发布的文章，因此这里不展示演示文章或虚构阅读量。</p>
      </div>
      <img src="/assets/otter-writing.png" alt="水獭正在整理笔记" />
    </header>
    <section class="topic-lines" aria-label="计划中的博客内容">
      <article v-for="(topic, index) in topics" :key="topic[0]">
        <span>{{ String(index + 1).padStart(2, "0") }}</span>
        <div>
          <h2>{{ topic[0] }}</h2>
          <p>{{ topic[1] }}</p>
        </div>
      </article>
    </section>
    <section class="blog-promise">
      <h2>什么时候会变成文章列表？</h2>
      <p>
        当第一篇真实文章完成后，再建设列表、标签和详情页。在这之前，这个页面只说明准备写什么，不用假内容填满版面。
      </p>
    </section>
  </main>
</template>
