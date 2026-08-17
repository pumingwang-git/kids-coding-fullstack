<template>
  <main class="shell study-home">
    <section class="study-hero">
      <div>
        <p class="eyebrow">FRONTEND PRACTICE</p>
        <h1>慢慢学，<br />把知识变成<span>作品。</span></h1>
        <p>
          课程、练习题与学习进度都在同一条清晰的路径里。先创建账号并完成邮箱验证，再从第一道题开始。
        </p>
        <div class="action-row">
          <RouterLink class="button button-primary" to="/courses"
            >开始学习 <span>→</span></RouterLink
          >
          <!-- <RouterLink class="text-link" to="/courses">查看课程 <span>→</span></RouterLink> -->
        </div>
      </div>
      <div class="study-art">
        <i class="ring ring-one" /><i class="ring ring-two" /><img
          src="/assets/otter-welcome.png"
          alt="欢迎学习的水獭"
        />
      </div>
    </section>
    <section class="path-section">
      <p class="eyebrow">LEARNING PATH</p>
      <div class="path-grid">
        <article>
          <b>01</b>
          <h2>注册并验证邮箱</h2>
          <p>用可验证的邮箱创建账户，安全地保存你的学习数据。</p>
        </article>
        <article>
          <b>02</b>
          <h2>跟着课程练习</h2>
          <p>每门课程拆成可完成的小节，让学习节奏保持轻盈。</p>
        </article>
        <article>
          <b>03</b>
          <h2>即时查看反馈</h2>
          <p>答题后马上了解原因，把薄弱知识点变成下一次进步。</p>
        </article>
      </div>
    </section>
  </main>
</template>
