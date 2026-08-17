<template>
  <main>
    <section class="blog-hero shell">
      <div class="hero-copy">
        <p class="eyebrow">PERSONAL BLOG · FRONTEND LEARNER</p>
        <h1>从好奇开始，<br />让想法<span>发光。</span></h1>
        <p>
          你好，我是汪蒲明。一名正在学习现代 Web
          开发的前端开发者，也在把每一次练习沉淀成能亲手使用的作品。
        </p>
        <div class="action-row">
          <RouterLink class="button button-primary" to="/study">
            进入做题系统 <span>→</span></RouterLink
          >
          <!-- <a class="text-link" href="#articles">阅读博客 <span>→</span></a> -->
        </div>
      </div>
      <div class="hero-art">
        <i class="ring ring-one" /><i class="ring ring-two" /><img
          src="/assets/otter-hero.png"
          alt="在书桌前学习的水獭"
        /><small>LEARN · BUILD · SHARE</small>
      </div>
    </section>
    <section id="articles" class="blog-section shell">
      <p class="eyebrow">LATEST NOTES</p>
      <div class="section-heading">
        <h2>把学习过程，<br />写成可以回看的<span>笔记。</span></h2>
        <p>
          这里记录前端学习中的概念、练习和项目复盘。完成账号注册后，还可以进入学习系统做题并保存进度。
        </p>
      </div>
      <div class="article-grid">
        <article>
          <span>01 / HTML</span>
          <h3>网页结构从语义开始</h3>
          <p>用清晰的标签让内容更容易理解，也让后续的样式和交互更可靠。</p>
        </article>
        <article>
          <span>02 / CSS</span>
          <h3>布局不是堆样式</h3>
          <p>从 Flexbox、Grid 到响应式设计，建立能适应不同屏幕的页面直觉。</p>
        </article>
        <article>
          <span>03 / JAVASCRIPT</span>
          <h3>让页面自然地回应用户</h3>
          <p>用事件、状态和反馈，让静态页面成为真正可使用的界面。</p>
        </article>
      </div>
    </section>
    <section class="blog-cta shell">
      <div>
        <p class="eyebrow">PRACTICE SYSTEM</p>
        <h2>不只看笔记，<br />也用题目检验收获。</h2>
      </div>
      <RouterLink class="button button-light" to="/study">去做一题 <span>→</span></RouterLink>
    </section>
  </main>
</template>
