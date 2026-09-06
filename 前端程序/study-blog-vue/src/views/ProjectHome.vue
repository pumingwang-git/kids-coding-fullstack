<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import AppIcon from "../components/AppIcon.vue";

const shots = {
  studyHome: "/assets/project/study-home.png",
  lesson: "/assets/project/lesson.png",
  coding: "/assets/project/coding-problem.png",
  scratch: "/assets/project/scratch-editor.png",
  admin: "/assets/project/admin.png",
};

const stages = [
  {
    key: "courses",
    index: "01",
    label: "选择课程",
    title: "先找到适合的课程",
    description: "课程按方向、类型和章节组织，进入后能先看清学习目录。",
    caption: "学习空间会保留继续学习的位置和专区功能入口",
    image: shots.studyHome,
    alt: "学生学习首页",
  },
  {
    key: "lesson",
    index: "02",
    label: "专注课时",
    title: "课时一次专注一项",
    description: "视频、阅读、练习、作业和资料按内容块呈现，右侧时间轴保留学习位置。",
    caption: "课时内容与进度导航并排呈现，帮助学生专注当下的学习内容",
    image: shots.lesson,
    alt: "带有课时导航的资料阅读界面",
  },
  {
    key: "practice",
    index: "03",
    label: "编程练习",
    title: "动手写，再查看反馈",
    description: "编程题提供代码编辑、样例运行和提交判题，作答结果回到统一的学习记录里。",
    caption: "代码编辑、样例运行和提交判题在一次练习中完成",
    image: shots.coding,
    alt: "带代码编辑器和运行结果的编程练习界面",
  },
];

const activeStageKey = ref(stages[0].key);
const activeStage = computed(
  () => stages.find((stage) => stage.key === activeStageKey.value) || stages[0],
);
</script>

<template>
  <main class="portal-page project-page portal-section">
    <header class="project-hero">
      <div class="project-hero-copy">
        <p class="project-label">少儿编程学习与实践平台</p>
        <h1>把一节课，变成一次完整的学习</h1>
        <p class="project-lead">
          启程学堂把课程内容、练习反馈、作品创作和学习记录放进同一条路径，让学生知道现在学什么、接下来做什么，以及已经完成了什么。
        </p>
        <div class="project-hero-actions">
          <RouterLink class="primary-action" to="/study"
            >进入少儿编程 <AppIcon name="arrow-right"
          /></RouterLink>
          <a class="text-action" href="#learning-flow"
            >看看学习如何展开 <AppIcon name="arrow-right"
          /></a>
        </div>
      </div>
      <figure class="hero-screen">
        <img :src="shots.studyHome" alt="少儿编程学习空间，展示继续学习和专区功能入口" />
        <figcaption>学生登录后，从自己的学习空间继续前进</figcaption>
      </figure>
    </header>

    <section class="project-purpose" aria-labelledby="purpose-title">
      <div>
        <h2 id="purpose-title">课程不该只是一排视频</h2>
        <p>
          对学生来说，学习不应止于“看完”。课程需要给出下一步，练习需要及时反馈，完成的内容需要被真实记录。对教学管理者来说，课程、题目、任务和结果也需要在清楚的权限边界里维护。
        </p>
      </div>
      <ul>
        <li><span>课程</span><b>知道从哪里开始</b></li>
        <li><span>练习</span><b>马上检验是否理解</b></li>
        <li><span>记录</span><b>下次从上次停下的位置继续</b></li>
      </ul>
    </section>

    <section
      id="learning-flow"
      class="project-section learning-flow"
      aria-labelledby="learning-flow-title"
    >
      <header class="section-intro">
        <div>
          <p>学习闭环</p>
          <h2 id="learning-flow-title">从选课，到完成一次练习</h2>
        </div>
        <p>课程、课时、练习和反馈各自做好一件事，再顺着学习路径连接起来。</p>
      </header>
      <div class="learning-showcase">
        <div class="stage-tabs" role="tablist" aria-label="学习过程">
          <button
            v-for="stage in stages"
            :id="`stage-tab-${stage.key}`"
            :key="stage.key"
            class="stage-tab"
            :class="{ active: stage.key === activeStage.key }"
            type="button"
            role="tab"
            :aria-selected="stage.key === activeStage.key"
            :aria-controls="`stage-panel-${stage.key}`"
            @click="activeStageKey = stage.key"
          >
            <span>{{ stage.index }}</span
            ><b>{{ stage.label }}</b>
          </button>
        </div>
        <Transition name="stage-swap" mode="out-in">
          <article
            :id="`stage-panel-${activeStage.key}`"
            :key="activeStage.key"
            class="showcase-stage"
            role="tabpanel"
            :aria-labelledby="`stage-tab-${activeStage.key}`"
          >
            <div class="showcase-copy">
              <span>{{ activeStage.index }}</span>
              <h3>{{ activeStage.title }}</h3>
              <p>{{ activeStage.description }}</p>
            </div>
            <figure>
              <img :src="activeStage.image" :alt="activeStage.alt" />
              <figcaption>{{ activeStage.caption }}</figcaption>
            </figure>
          </article>
        </Transition>
      </div>
    </section>

    <section class="project-section making-section" aria-labelledby="making-title">
      <div class="making-copy">
        <p>探索与创作</p>
        <h2 id="making-title">学会之后，把想法做出来</h2>
        <p>
          Scratch
          图形化编程工作台让学生用积木搭建程序、运行和调整作品。完成作品后，可以在作品广场浏览和运行公开作品，让学习从完成题目延伸到自由创作。
        </p>
        <RouterLink class="text-action" to="/areas/kids/explore"
          >进入探索创作 <AppIcon name="arrow-right"
        /></RouterLink>
      </div>
      <figure class="making-screen">
        <img :src="shots.scratch" alt="Scratch 图形化编程工作台" loading="lazy" />
        <figcaption>积木、舞台和作品运行结果，在同一个创作空间里</figcaption>
      </figure>
    </section>

    <section class="project-section management-section" aria-labelledby="management-title">
      <div class="management-screen">
        <img :src="shots.admin" alt="教学管理后台总览" loading="lazy" />
      </div>
      <div class="management-copy">
        <p>教学与运营</p>
        <h2 id="management-title">学生端背后，有一套真实的管理流程</h2>
        <p>
          管理后台按配题、配课和运营组织工作：维护题库、试卷、课包、内容块和资料，安排班级任务，查看学习与成绩情况。学生端看到的课程、作答次数、评分和完成状态，都以服务端规则为准。
        </p>
        <dl>
          <div>
            <dt>配题</dt>
            <dd>题库、试卷与考试链接</dd>
          </div>
          <div>
            <dt>配课</dt>
            <dd>课包、目录、内容块、资料与视频</dd>
          </div>
          <div>
            <dt>运营</dt>
            <dd>班级、任务、成绩、账号与角色</dd>
          </div>
        </dl>
      </div>
    </section>

    <section class="project-section implementation-section" aria-labelledby="implementation-title">
      <header class="section-intro">
        <div>
          <p>技术实现</p>
          <h2 id="implementation-title">界面呈现学习，服务端守住学习数据</h2>
        </div>
        <p>项目的技术重点不是堆叠功能，而是让学习状态、评分和权限有可靠的来源。</p>
      </header>
      <div class="implementation-grid">
        <article>
          <h3>学生端与管理端</h3>
          <p>
            学生端使用 Vue 3 与 Vite 构建，管理端采用独立的原生 HTML 与 JavaScript 界面；Scratch
            和学习工具作为独立子应用接入。
          </p>
        </article>
        <article>
          <h3>课程与作答服务</h3>
          <p>
            FastAPI 提供身份、课程、内容块、进度和作答接口；PostgreSQL 保存业务数据，Alembic
            管理数据库结构变更。
          </p>
        </article>
        <article>
          <h3>评分与权限边界</h3>
          <p>
            资源范围、解锁规则、尝试次数、评分与完成状态由服务端决定。前端呈现结果，不自行猜测学习状态或访问权限。
          </p>
        </article>
      </div>
    </section>

    <footer class="project-cta">
      <div>
        <p>从现有能力开始体验</p>
        <h2>进入少儿编程，开始自己的学习与创作</h2>
      </div>
      <RouterLink class="primary-action" to="/study"
        >开始学习 <AppIcon name="arrow-right"
      /></RouterLink>
    </footer>
  </main>
</template>

<style scoped>
.project-page {
  padding-top: 56px;
  padding-bottom: 84px;
}
.project-hero {
  display: grid;
  grid-template-columns: minmax(0, 0.83fr) minmax(460px, 1.17fr);
  align-items: center;
  gap: 62px;
  margin-bottom: 112px;
}
.project-label,
.section-intro > div > p,
.making-copy > p:first-child,
.management-copy > p:first-child,
.project-cta > div > p {
  color: var(--accent);
  font: 700 12px/1.5 var(--font-mono);
  margin: 0 0 14px;
}
.project-hero h1 {
  max-width: 8em;
  font: 800 clamp(44px, 5vw, 66px) / 1.17 var(--font-display);
  letter-spacing: -0.03em;
  margin: 0;
}
.project-lead {
  max-width: 31em;
  color: var(--muted);
  font-size: 17px;
  line-height: 1.9;
  margin: 26px 0 0;
}
.project-hero-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 24px;
  margin-top: 32px;
}
.text-action {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  gap: 8px;
  color: var(--accent);
  font-size: 14px;
  font-weight: 800;
}
.text-action:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}
.hero-screen,
.making-screen {
  margin: 0;
}
.hero-screen {
  position: relative;
  padding: 12px 12px 0;
  border-radius: 28px 8px 28px 8px;
  background: var(--kids-sky);
}
.hero-screen img,
.making-screen img,
.management-screen img,
.showcase-stage img {
  display: block;
  width: 100%;
  height: auto;
}
.hero-screen img {
  border-radius: 17px 4px 0 0;
  box-shadow: 0 14px 26px rgba(34, 43, 40, 0.13);
}
figcaption {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}
.hero-screen figcaption {
  padding: 13px 12px 15px;
}
.project-purpose {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.88fr);
  gap: 72px;
  align-items: start;
  padding: 56px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.project-purpose h2,
.section-intro h2,
.making-copy h2,
.management-copy h2,
.project-cta h2 {
  font: 800 clamp(30px, 3.4vw, 46px) / 1.3 var(--font-display);
  letter-spacing: -0.025em;
  margin: 0;
}
.project-purpose p {
  max-width: 43em;
  color: var(--muted);
  font-size: 16px;
  line-height: 1.9;
  margin: 19px 0 0;
}
.project-purpose ul {
  display: grid;
  gap: 0;
  list-style: none;
  padding: 0;
  margin: 0;
  border-top: 1px solid var(--line);
}
.project-purpose li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 24px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
}
.project-purpose span {
  color: var(--accent);
  font: 700 12px/1.5 var(--font-mono);
}
.project-purpose b {
  font-size: 15px;
}
.project-section {
  margin-top: 120px;
}
.section-intro {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(290px, 0.55fr);
  align-items: end;
  gap: 48px;
  margin-bottom: 36px;
}
.section-intro > p {
  color: var(--muted);
  font-size: 15px;
  line-height: 1.9;
  margin: 0;
}
.learning-showcase {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  overflow: hidden;
  border-radius: 8px 28px 8px 28px;
  background: var(--cream);
}
.stage-tabs {
  display: grid;
  align-content: stretch;
  background: var(--mint);
}
.stage-tab {
  display: grid;
  align-content: center;
  gap: 7px;
  min-height: 128px;
  padding: 24px 26px;
  border: 0;
  border-bottom: 1px solid rgba(34, 43, 40, 0.14);
  background: transparent;
  color: var(--ink);
  text-align: left;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    padding 0.2s ease;
}
.stage-tab:last-child {
  border-bottom: 0;
}
.stage-tab:hover,
.stage-tab.active {
  padding-left: 31px;
  background: var(--accent);
  color: white;
}
.stage-tab span,
.showcase-copy > span {
  font: 700 12px/1.5 var(--font-mono);
}
.stage-tab span {
  color: var(--accent);
}
.stage-tab.active span,
.stage-tab:hover span {
  color: inherit;
}
.stage-tab b {
  font-size: 16px;
}
.showcase-stage {
  display: grid;
  grid-template-columns: minmax(250px, 0.7fr) minmax(0, 1.3fr);
  min-height: 432px;
  background: var(--kids-sky);
}
.showcase-copy {
  align-self: center;
  padding: 42px 30px 42px 38px;
}
.showcase-copy > span {
  color: var(--accent);
}
.showcase-copy h3,
.implementation-grid h3 {
  font: 800 23px/1.35 var(--font-display);
  letter-spacing: -0.02em;
  margin: 12px 0 9px;
}
.showcase-copy p,
.implementation-grid p {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.85;
  margin: 0;
}
.showcase-stage figure {
  display: flex;
  align-self: stretch;
  flex-direction: column;
  justify-content: end;
  min-width: 0;
  margin: 0;
  padding: 26px 26px 0 0;
}
.showcase-stage img {
  flex: 1 1 auto;
  min-height: 0;
  object-fit: cover;
  object-position: left top;
  border-radius: 14px 4px 0 0;
  box-shadow: 0 14px 28px rgba(34, 43, 40, 0.14);
}
.showcase-stage figcaption {
  min-height: 48px;
  padding: 11px 0;
}
.stage-swap-enter-active,
.stage-swap-leave-active {
  transition:
    opacity 0.22s ease,
    transform 0.22s ease;
}
.stage-swap-enter-from {
  opacity: 0;
  transform: translateX(16px);
}
.stage-swap-leave-to {
  opacity: 0;
  transform: translateX(-16px);
}
.making-section,
.management-section {
  display: grid;
  grid-template-columns: minmax(0, 0.78fr) minmax(0, 1.22fr);
  gap: 76px;
  align-items: center;
}
.making-copy > p:not(:first-child),
.management-copy > p:not(:first-child) {
  color: var(--muted);
  font-size: 16px;
  line-height: 1.9;
  margin: 20px 0 18px;
}
.making-screen {
  padding: 12px;
  border-radius: 8px 28px 8px 28px;
  background: var(--mint);
}
.making-screen img {
  border-radius: 4px 18px 0 0;
  box-shadow: 0 14px 28px rgba(34, 43, 40, 0.13);
}
.making-screen figcaption {
  padding: 12px 7px 3px;
}
.management-section {
  grid-template-columns: minmax(0, 1.14fr) minmax(0, 0.86fr);
}
.management-screen {
  padding: 11px;
  border-radius: 28px 8px 28px 8px;
  background: color-mix(in srgb, var(--kids-sky) 66%, var(--paper));
}
.management-screen img {
  border-radius: 17px 4px 17px 4px;
  box-shadow: 0 14px 28px rgba(34, 43, 40, 0.12);
}
.management-copy dl {
  display: grid;
  gap: 0;
  margin: 28px 0 0;
  border-top: 1px solid var(--line);
}
.management-copy dl > div {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr);
  gap: 14px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}
.management-copy dt {
  color: var(--accent);
  font: 700 12px/1.6 var(--font-mono);
}
.management-copy dd {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}
.implementation-section {
  padding: 58px 60px;
  border-radius: 30px 8px 30px 8px;
  background: var(--mint);
}
.implementation-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  border-top: 1px solid rgba(34, 43, 40, 0.14);
}
.implementation-grid article {
  min-height: 190px;
  padding: 22px 28px 0;
}
.implementation-grid article:first-child {
  padding-left: 0;
}
.implementation-grid article + article {
  border-left: 1px solid rgba(34, 43, 40, 0.14);
}
.project-cta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 36px;
  margin-top: 120px;
  padding: 52px 0 0;
  border-top: 1px solid var(--line);
  background: none;
  border-radius: 0;
}
.project-cta > div > p {
  margin-bottom: 10px;
}
.project-cta .primary-action {
  flex-shrink: 0;
}
@media (max-width: 980px) {
  .project-hero {
    grid-template-columns: minmax(0, 0.85fr) minmax(350px, 1.15fr);
    gap: 36px;
  }
  .project-hero h1 {
    font-size: 48px;
  }
  .project-purpose,
  .section-intro,
  .making-section,
  .management-section {
    gap: 42px;
  }
  .project-purpose {
    grid-template-columns: minmax(0, 1fr) minmax(290px, 0.78fr);
  }
  .implementation-section {
    padding: 44px 40px;
  }
}
@media (max-width: 760px) {
  .project-page {
    padding-top: 36px;
    padding-bottom: 52px;
  }
  .project-hero,
  .project-purpose,
  .section-intro,
  .making-section,
  .management-section {
    grid-template-columns: minmax(0, 1fr);
  }
  .project-hero {
    gap: 34px;
    margin-bottom: 80px;
  }
  .project-hero h1 {
    max-width: 9em;
    font-size: clamp(40px, 10vw, 56px);
  }
  .project-lead {
    font-size: 16px;
  }
  .hero-screen {
    max-width: 620px;
  }
  .project-purpose {
    gap: 32px;
    padding: 42px 0;
  }
  .project-section {
    margin-top: 80px;
  }
  .section-intro {
    gap: 16px;
    margin-bottom: 28px;
  }
  .learning-showcase {
    grid-template-columns: minmax(0, 1fr);
  }
  .stage-tabs {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .stage-tab {
    min-height: 90px;
    padding: 17px 20px;
    border-right: 1px solid rgba(34, 43, 40, 0.14);
    border-bottom: 0;
  }
  .stage-tab:last-child {
    border-right: 0;
  }
  .stage-tab:hover,
  .stage-tab.active {
    padding-left: 20px;
  }
  .showcase-stage {
    grid-template-columns: minmax(0, 0.68fr) minmax(0, 1.32fr);
    min-height: 350px;
  }
  .showcase-copy {
    padding: 32px 26px;
  }
  .showcase-stage figure {
    padding-top: 20px;
  }
  .making-section,
  .management-section {
    gap: 34px;
  }
  .management-screen {
    order: 2;
  }
  .implementation-section {
    padding: 38px 30px;
  }
  .implementation-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .implementation-grid article,
  .implementation-grid article:first-child {
    min-height: auto;
    padding: 22px 0;
  }
  .implementation-grid article + article {
    border-top: 1px solid rgba(34, 43, 40, 0.14);
    border-left: 0;
  }
  .project-cta {
    align-items: flex-start;
    flex-direction: column;
    gap: 24px;
    margin-top: 80px;
    padding-top: 42px;
  }
}
@media (max-width: 500px) {
  .project-hero h1 {
    font-size: 39px;
  }
  .project-hero-actions {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
  .hero-screen {
    padding: 7px 7px 0;
    border-radius: 20px 5px 20px 5px;
  }
  .hero-screen figcaption {
    padding: 10px 7px 11px;
  }
  .project-purpose li {
    align-items: flex-start;
    flex-direction: column;
    gap: 3px;
  }
  .project-purpose h2,
  .section-intro h2,
  .making-copy h2,
  .management-copy h2,
  .project-cta h2 {
    font-size: 30px;
  }
  .stage-tab {
    min-height: 78px;
    padding: 14px 13px;
  }
  .stage-tab:hover,
  .stage-tab.active {
    padding-left: 13px;
  }
  .stage-tab b {
    font-size: 14px;
  }
  .showcase-stage {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto 220px;
    min-height: 0;
  }
  .showcase-copy {
    padding: 28px 24px 20px;
  }
  .showcase-stage figure {
    padding: 0 16px 0 0;
  }
  .showcase-stage figcaption {
    display: none;
  }
  .showcase-stage img {
    min-height: 220px;
  }
  .making-screen,
  .management-screen {
    padding: 7px;
  }
  .implementation-section {
    padding: 34px 24px;
    border-radius: 20px 5px 20px 5px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .text-action:hover {
    text-decoration: none;
  }
}
</style>
