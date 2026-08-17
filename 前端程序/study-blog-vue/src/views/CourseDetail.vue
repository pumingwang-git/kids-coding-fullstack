<script setup>
// 课包详情：简介 + 章节课时目录。
//
// 目录**不带正文**（后端 GET /api/courses/{id} 只回标题/时长/试看标记/unlocked），
// 正文与播放各走 /api/lessons/{id} 与 /api/lessons/{id}/play，各自判定权限。
// 所以这一页锁着的课时只能显示标题——这是设计，不是数据没取全。
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import { request } from "../services/auth";
import { prefetchLesson } from "../services/prefetch";
import { renderMarkdown } from "../services/markdown";

const route = useRoute();
const router = useRouter();
const courseId = computed(() => Number(route.params.courseId));

const course = ref(null);
const sections = ref([]);
const enrolled = ref(false);
const loading = ref(true);
const error = ref("");
const collapsed = ref(new Set());
const page = ref(1);
const pageSize = 8;
const totalSections = ref(0);

const DIFFICULTY = { beginner: "入门", intermediate: "进阶", advanced: "高阶" };
const KIND_ICON = { video: "▶", url: "🔗", article: "📄", mixed: "🧩", empty: "…" };

const totalLessons = computed(() =>
  sections.value.reduce((sum, section) => sum + section.lessons.length, 0),
);
const totalMinutes = computed(() => course.value?.total_minutes || 0);
const pageCount = computed(() => Math.max(1, Math.ceil(totalSections.value / pageSize)));

// 课时能否点进学习页：整节开放（试看/已开通）自然可以；「试看前 N 块」的课时
// 即使未开通也能进——前 N 块内容可学，其余块页内逐块锁定。
function canOpen(lesson) {
  return lesson.unlocked || lesson.open_policy === "first_n";
}

function trialChip(lesson) {
  if (lesson.open_policy === "whole") return "试看";
  if (lesson.open_policy === "first_n") return `前 ${lesson.trial_block_count || 0} 块试看`;
  return "";
}

function toggle(sectionId) {
  const next = new Set(collapsed.value);
  if (next.has(sectionId)) next.delete(sectionId);
  else next.add(sectionId);
  collapsed.value = next;
}

async function load(nextPage = page.value) {
  loading.value = true;
  error.value = "";
  try {
    const query = new URLSearchParams({ page: String(nextPage), page_size: String(pageSize) });
    const data = await request(`/api/courses/${courseId.value}?${query}`);
    course.value = data.course;
    if (route.params.areaKey !== data.course.area_key) {
      await router.replace({
        name: "course-detail",
        params: { courseId: courseId.value },
        query: { ...route.query, area: data.course.area_key },
      });
    }
    sections.value = data.sections || [];
    totalSections.value = data.total_sections || sections.value.length;
    page.value = data.page || nextPage;
    enrolled.value = Boolean(data.enrolled);
  } catch (err) {
    error.value = err?.message || "课包加载失败。";
  } finally {
    loading.value = false;
  }
}

// hover 预取（交接文档 17 §5 S2-5）：学生在目录里犹豫的那一两秒，把课时详情先取回来，
// 真点下去时数据已经在手上——「点了就开」主要就来自这一条。
//
// 200ms 防抖：鼠标从上往下扫过一整章课时，不该沿路打出十几个请求。
// focus（键盘）和 touchstart（移动端）意图明确得多，不防抖，直接取。
// saveData / 2g 的护栏在 services/prefetch 里，这里不重复判。
let hoverTimer = null;

function onLessonHover(lesson) {
  if (!canOpen(lesson)) return;
  clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => prefetchLesson(lesson.id), 200);
}

function onLessonLeave() {
  clearTimeout(hoverTimer);
}

function onLessonIntent(lesson) {
  if (!canOpen(lesson)) return;
  clearTimeout(hoverTimer);
  prefetchLesson(lesson.id);
}

onMounted(load);
onBeforeUnmount(() => clearTimeout(hoverTimer));
watch(courseId, () => load(1));
</script>

<template>
  <main class="shell course-detail">
    <p v-if="loading" class="state">正在加载课包…</p>
    <p v-else-if="error" class="state error">{{ error }}</p>

    <template v-else-if="course">
      <header class="page-heading">
        <div>
          <p class="eyebrow">
            <RouterLink :to="`/areas/${course.area_key}/courses`">课程</RouterLink>
            / {{ course.category_breadcrumb?.map((item) => item.name).join(" / ") || "未分类" }}
          </p>
          <h1>{{ course.title }}</h1>
          <p v-if="course.subtitle" class="subtitle">{{ course.subtitle }}</p>
        </div>
        <div class="facts">
          <span class="chip">{{ DIFFICULTY[course.difficulty] || course.difficulty }}</span>
          <span class="chip ghost">{{ sections.length }} 章 · {{ totalLessons }} 节</span>
          <span v-if="totalMinutes" class="chip ghost">约 {{ totalMinutes }} 分钟</span>
          <span class="chip" :class="enrolled ? 'ok' : 'ghost'">{{
            enrolled ? "已开通" : "未开通"
          }}</span>
        </div>
      </header>

      <img v-if="course.cover_url" class="cover" :src="course.cover_url" alt="课包头图" />

      <section v-if="course.description" class="intro markdown-body">
        <!-- 简介字段存的是 Markdown，走统一安全渲染管线（marked + DOMPurify），
             与课时正文同一套实现，不要退化成按换行拆 <p>。 -->
        <div v-html="renderMarkdown(course.description)"></div>
      </section>

      <section class="catalog">
        <h2>课程目录</h2>
        <p v-if="!sections.length" class="state">目录还在准备中。</p>

        <div v-for="section in sections" :key="section.id" class="section-block">
          <button class="section-head" type="button" @click="toggle(section.id)">
            <span class="arrow">{{ collapsed.has(section.id) ? "▸" : "▾" }}</span>
            <span class="section-title">{{ section.title }}</span>
            <span class="count">{{ section.lessons.length }} 节</span>
          </button>

          <ul v-show="!collapsed.has(section.id)" class="lesson-list">
            <li v-for="lesson in section.lessons" :key="lesson.id" class="lesson-row">
              <component
                :is="canOpen(lesson) ? 'RouterLink' : 'div'"
                v-bind="
                  canOpen(lesson)
                    ? { to: { name: 'lesson-player', params: { lessonId: lesson.id } } }
                    : {}
                "
                class="lesson-link"
                :class="{ locked: !canOpen(lesson) }"
                @mouseenter="onLessonHover(lesson)"
                @mouseleave="onLessonLeave"
                @focus="onLessonIntent(lesson)"
                @touchstart.passive="onLessonIntent(lesson)"
              >
                <span class="kind">{{ KIND_ICON[lesson.content_kind] || "·" }}</span>
                <span class="title">{{ lesson.title }}</span>
                <span v-if="trialChip(lesson)" class="chip trial">{{ trialChip(lesson) }}</span>
                <span v-if="lesson.duration_minutes" class="dur"
                  >{{ lesson.duration_minutes }} 分钟</span
                >
                <span v-if="!canOpen(lesson)" class="lock" title="该课包尚未对你开放">🔒</span>
              </component>
              <p v-if="lesson.summary" class="summary">{{ lesson.summary }}</p>
            </li>
          </ul>
        </div>
        <nav v-if="pageCount > 1" class="catalog-pager" aria-label="课程目录分页">
          <button type="button" :disabled="page <= 1" @click="load(page - 1)">上一页</button>
          <span>第 {{ page }} / {{ pageCount }} 页 · 共 {{ totalSections }} 个章节</span>
          <button type="button" :disabled="page >= pageCount" @click="load(page + 1)">
            下一页
          </button>
        </nav>
      </section>
    </template>
  </main>
</template>

<style scoped>
.course-detail {
  max-width: 900px;
}
.state {
  padding: 28px 0;
  color: var(--muted, #6b7280);
}
.state.error {
  color: #c0392b;
}
.subtitle {
  color: var(--muted, #6b7280);
  margin-top: 6px;
}
.facts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: flex-start;
}
.chip {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(47, 128, 110, 0.12);
  color: #2f806e;
  white-space: nowrap;
}
.chip.ghost {
  background: rgba(34, 43, 40, 0.07);
  color: var(--muted, #6b7280);
}
.chip.ok {
  background: rgba(47, 128, 110, 0.2);
}
.chip.trial {
  background: rgba(47, 110, 128, 0.14);
  color: #2f6e80;
}
.intro {
  margin: 20px 0 28px;
  line-height: 1.8;
}
.cover {
  width: 100%;
  max-height: 320px;
  object-fit: cover;
  border-radius: 12px;
  margin-top: 16px;
  border: 1px solid var(--border, #e4e7ec);
}
/* v-html 渲染的 Markdown 简介样式（scoped 下必须 :deep 才能命中子节点） */
.intro :deep(h1),
.intro :deep(h2),
.intro :deep(h3) {
  margin: 1.2em 0 0.5em;
  line-height: 1.35;
}
.intro :deep(p) {
  margin: 0.7em 0;
}
.intro :deep(ul),
.intro :deep(ol) {
  padding-left: 1.6em;
  margin: 0.7em 0;
}
.intro :deep(pre) {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
  overflow-x: auto;
}
.intro :deep(code) {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.9em;
}
.intro :deep(p code) {
  background: rgba(15, 23, 42, 0.08);
  border-radius: 4px;
  padding: 1px 5px;
}
.intro :deep(blockquote) {
  margin: 0.7em 0;
  padding: 0.2em 1em;
  border-left: 1px solid var(--border, #e4e7ec);
  color: var(--muted, #6b7280);
}
.intro :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}
.intro :deep(a) {
  color: #2f6e80;
}
.catalog h2 {
  font-size: 18px;
  margin-bottom: 12px;
}
.catalog-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 20px;
  color: var(--muted, #6b7280);
  font-size: 13px;
}
.catalog-pager button {
  border: 1px solid var(--border, #e4e7ec);
  border-radius: 999px;
  padding: 6px 12px;
  background: transparent;
  color: inherit;
}
.catalog-pager button:disabled {
  opacity: 0.45;
}
.section-block {
  border: 1px solid var(--border, #e4e7ec);
  border-radius: 10px;
  margin-bottom: 12px;
  overflow: hidden;
}
.section-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(47, 128, 110, 0.06);
  border: 0;
  cursor: pointer;
  font: inherit;
  text-align: left;
}
.section-title {
  font-weight: 600;
  flex: 1;
}
.count {
  color: var(--muted, #6b7280);
  font-size: 13px;
}
.lesson-list {
  list-style: none;
  margin: 0;
  padding: 6px;
}
.lesson-row {
  padding: 2px 0;
}
.lesson-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
}
.lesson-link:not(.locked):hover {
  background: rgba(47, 128, 110, 0.08);
}
.lesson-link.locked {
  color: var(--muted, #9ca3af);
  cursor: not-allowed;
}
.lesson-link .title {
  flex: 1;
}
.dur {
  font-size: 12px;
  color: var(--muted, #6b7280);
}
.summary {
  margin: 0 12px 6px 34px;
  font-size: 13px;
  color: var(--muted, #6b7280);
}
</style>
