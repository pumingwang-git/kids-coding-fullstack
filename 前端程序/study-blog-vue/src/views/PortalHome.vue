<script setup>
import { RouterLink } from "vue-router";
import AppIcon from "../components/AppIcon.vue";

const features = [
  ["课程学习", "按课包、章节和课时组织学习路线。"],
  ["内容块学习", "视频、阅读、练习、作业和资料一次专注一项。"],
  ["练习与作业", "学习后及时作答，提交状态清楚可见。"],
  ["考试反馈", "沿用统一题库、判题和成绩流程。"],
  ["学习进度", "记录已学内容，回到上次停止的位置。"],
  ["后台管理", "课程、内容、题目和考试由管理端统一维护。"],
];
</script>

<template>
  <main class="portal-home">
    <section class="portal-hero portal-section">
      <div class="portal-hero-copy">
        <p class="hero-kicker">从一节课出发，完成一次真正的学习</p>
        <h1>课程、练习、反馈与进度，<br />都在一条清楚的学习路径里</h1>
        <p class="hero-lead">面向少儿编程学习，也为后续 Python、前端与资料专区预留了清晰的位置。</p>
        <div class="hero-actions">
          <RouterLink class="primary-action" to="/study"
            >开始学习 <AppIcon name="arrow-right"
          /></RouterLink>
          <RouterLink class="secondary-action" to="/project">了解这个项目</RouterLink>
        </div>
        <p class="hero-note">已有账号可直接进入；未登录时会先完成登录，再返回学习空间。</p>
      </div>
      <div class="learning-route" aria-label="学习路径示意">
        <img class="hero-otter" src="/assets/otter-hero.png" alt="水獭学习伙伴" />
        <ol>
          <li><span>01</span><b>选课程</b><small>找到适合的学习内容</small></li>
          <li><span>02</span><b>学内容</b><small>一次专注一个内容块</small></li>
          <li><span>03</span><b>做任务</b><small>练习、作业或考试</small></li>
          <li><span>04</span><b>看反馈</b><small>记录进度，继续前进</small></li>
        </ol>
      </div>
    </section>

    <section class="portal-section areas-section">
      <div class="section-heading">
        <div>
          <p>学习专区</p>
          <h2>先选方向，再进入对应的学习空间</h2>
        </div>
        <RouterLink to="/learning">查看全部专区 <AppIcon name="arrow-right" /></RouterLink>
      </div>
      <div class="area-showcase">
        <RouterLink class="area-main" to="/study">
          <div>
            <span class="status-live">已开放</span>
            <h3>少儿编程</h3>
            <p>适合 8–14 岁学习者，从课程到任务形成完整闭环。</p>
          </div>
          <img src="/assets/otter-coding-720.webp" alt="水獭正在编程" width="720" height="720" loading="lazy" decoding="async" />
          <span class="area-enter">进入专区 <AppIcon name="arrow-right" /></span>
        </RouterLink>
        <div class="area-upcoming">
          <article>
            <span>规划中</span>
            <h3>Python 专区</h3>
            <p>面向进阶学习，未来使用更适合代码课程的课时模板。</p>
          </article>
          <article>
            <span>规划中</span>
            <h3>前端专区</h3>
            <p>围绕网页、交互和项目实践组织内容。</p>
          </article>
        </div>
      </div>
      <div class="resource-strip">
        <div>
          <AppIcon name="book" /><span
            ><b>资源中心</b><small>资料是查阅资源，不伪装成课程。</small></span
          >
        </div>
        <span class="status-planning">正在规划内容结构</span>
      </div>
    </section>

    <section class="portal-section capability-section">
      <div class="section-heading">
        <div>
          <p>网站能力</p>
          <h2>学习者看到路径，管理者维护内容</h2>
        </div>
      </div>
      <div class="capability-layout">
        <div class="capability-intro">
          <img src="/assets/otter-reading.png" alt="水獭正在阅读" loading="lazy" decoding="async" />
          <p>平台把已经实现的课程、内容块、作答与权限能力串成一条可持续扩展的学习路径。</p>
        </div>
        <ol class="feature-list">
          <li v-for="(feature, index) in features" :key="feature[0]">
            <span>{{ String(index + 1).padStart(2, "0") }}</span>
            <div>
              <h3>{{ feature[0] }}</h3>
              <p>{{ feature[1] }}</p>
            </div>
          </li>
        </ol>
      </div>
    </section>

    <section class="portal-section portal-bridge">
      <div class="project-summary">
        <p>项目介绍</p>
        <h2>不只展示页面，也说明学习与管理如何闭环</h2>
        <p>项目页会交代解决的问题、技术架构、权限与数据安全、当前完成度和下一步计划。</p>
        <RouterLink class="text-action" to="/project"
          >阅读项目介绍 <AppIcon name="arrow-right"
        /></RouterLink>
      </div>
      <div class="blog-summary">
        <span class="status-planning">正在筹备</span>
        <h2>博客</h2>
        <p>未来记录开发日志、前后端实践、学习笔记以及部署与排错。目前不展示虚构文章。</p>
        <RouterLink class="text-action" to="/blog"
          >查看筹备说明 <AppIcon name="arrow-right"
        /></RouterLink>
      </div>
    </section>

    <section class="portal-section final-actions">
      <div>
        <h2>准备好继续学习了吗？</h2>
        <p>学习入口是主路径，后台管理是内容维护工具。</p>
      </div>
      <div>
        <RouterLink class="primary-action" to="/study">进入少儿编程</RouterLink
        ><a class="secondary-action" href="/admin/login.html">后台管理</a>
      </div>
    </section>
  </main>
</template>
