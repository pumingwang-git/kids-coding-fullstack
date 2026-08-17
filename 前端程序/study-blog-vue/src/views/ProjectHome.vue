<script setup>
import { RouterLink } from "vue-router";
</script>

<template>
  <main class="portal-page project-page portal-section">
    <header class="page-intro project-intro">
      <div>
        <p>项目介绍</p>
        <h1>一个把学习内容与真实学习过程连接起来的平台</h1>
        <p>它既是可使用的课程产品，也是持续演进的前后端技术项目。</p>
      </div>
      <img src="/assets/otter-thinking-720.webp" alt="水獭正在思考" />
    </header>
    <section class="project-problem">
      <h2>要解决的问题</h2>
      <p>
        课程网站不该只是一排视频。学习者需要知道下一步做什么、是否完成、哪里需要反馈；管理者需要在可靠的权限和数据规则下维护课程、题目与考试。
      </p>
    </section>
    <section class="dual-loop">
      <article>
        <span>学习者闭环</span>
        <h2>选课 → 学习 → 作答 → 反馈 → 继续</h2>
        <p>课包、章节、课时与内容块组成学习路径，进度、作答和成绩帮助学习者接着往前。</p>
      </article>
      <article>
        <span>管理者闭环</span>
        <h2>组织 → 发布 → 授权 → 查看 → 调整</h2>
        <p>后台负责课程内容、题库试卷、考试入口与结果管理，重要判断仍由服务端完成。</p>
      </article>
    </section>
    <section class="project-details">
      <div>
        <h2>技术结构</h2>
        <p>
          前端使用 Vue 与 Vite 构建交互界面，后端使用 FastAPI
          提供身份、课程、内容块、进度和作答接口，数据库迁移记录结构变化。
        </p>
      </div>
      <div>
        <h2>权限与数据安全</h2>
        <p>
          身份、资源范围、判分、进度和写入权限由服务端负责。普通学员不能进入后台接口，演示账号也不会在安全隔离完成前公开真实管理员凭据。
        </p>
      </div>
      <div>
        <h2>当前阶段</h2>
        <p>
          课程列表、课包详情、课时内容块、练习作业、考试、登录续期和后台入口已有基础；门户与少儿专区正在形成统一的信息结构。
        </p>
      </div>
      <div>
        <h2>后续计划</h2>
        <p>
          先接入学习首页的真实聚合数据，再逐步建设作品、活动、竞赛和直播，最后扩展 Python
          与前端专区的专用课时模板。
        </p>
      </div>
    </section>
    <footer class="project-cta">
      <div>
        <h2>从现有能力开始体验</h2>
        <p>首个可进入的学习方向是少儿编程。</p>
      </div>
      <RouterLink class="primary-action" to="/study">开始学习</RouterLink>
    </footer>
  </main>
</template>
