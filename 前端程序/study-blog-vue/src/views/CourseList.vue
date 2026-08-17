<script setup>
// 课包列表：GET /api/courses 的真实数据（后台「课包管理」发布的课包）。
// 原先这里是三张硬编码的水獭卡片——插画与版式保留，只把数据源换掉：
// 没配封面的课包按 id 轮换回落到这三张图，作品集的视觉资产不该因为接了真数据就丢掉。
//
// 分类筛选：分类 chips 来自 GET /api/course-categories（只含已发布课包关联的分类），
// 选中项写入 URL query `?category=<id>`——刷新/分享链接后选择保持。
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { request } from "../services/auth";

const route = useRoute();
const router = useRouter();
const OTTERS = [
  "/assets/otter-writing.png",
  "/assets/otter-thinking-720.webp",
  "/assets/otter-coding-720.webp",
];
const DIFFICULTY = { beginner: "入门", intermediate: "进阶", advanced: "高阶" };

const courses = ref([]);
const categories = ref([]);
const page = ref(1);
const pageSize = 24;
const total = ref(0);
const loading = ref(true);
const error = ref("");

// 初始值从 URL 读；数字非法/不存在的分类 id 视为「全部」。
const selectedCategory = ref(
  route.query.category && /^\d+$/.test(String(route.query.category))
    ? Number(route.query.category)
    : null,
);

const isEmpty = computed(() => !loading.value && !error.value && courses.value.length === 0);
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const useCategorySelect = computed(() => categories.value.length > 8);
const selectedCategoryName = computed(
  () => categories.value.find((c) => c.id === selectedCategory.value)?.name || "",
);

const cover = (course, index) => course.cover_url || OTTERS[index % OTTERS.length];

function subtitleOf(course) {
  if (course.subtitle) return course.subtitle;
  const parts = [];
  if (course.lesson_count) parts.push(`${course.lesson_count} 课时`);
  if (course.total_minutes) parts.push(`约 ${course.total_minutes} 分钟`);
  return parts.join(" · ") || "课程内容准备中";
}

async function loadCategories() {
  const data = await request("/api/course-categories");
  categories.value = data.items || [];
  // URL 里的分类已不存在（被删除/无已发布课包）→ 回落到「全部」
  if (selectedCategory.value && !categories.value.some((c) => c.id === selectedCategory.value)) {
    selectedCategory.value = null;
  }
}

async function load(nextPage = page.value) {
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({ page: String(nextPage), page_size: String(pageSize) });
    if (selectedCategory.value) params.set("category_id", String(selectedCategory.value));
    // 一次拉满后端允许的最大页容量（48），避免超过 12 门课后漏数据；
    // 正式分页/加载更多留到课包量级上来后再做。
    const data = await request(`/api/courses?${params.toString()}`);
    courses.value = data.items || [];
    total.value = data.total || 0;
    page.value = data.page || nextPage;
  } catch (err) {
    error.value = err?.message || "课程列表加载失败，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

function selectCategory(categoryId) {
  selectedCategory.value = categoryId;
  // 写入 URL query：刷新/分享后选择保持；null 时去掉参数回到「全部」
  router.replace({
    query: categoryId ? { ...route.query, category: String(categoryId) } : {},
  });
  load(1);
}

onMounted(async () => {
  try {
    await loadCategories();
  } catch {
    categories.value = []; // 分类拉不到不该挡住课包列表
  }
  await load();
});
</script>

<template>
  <main class="shell courses">
    <header class="page-heading">
      <div>
        <p class="eyebrow">COURSES / 03</p>
        <h1>从基础开始，<br />建立前端<span>直觉。</span></h1>
      </div>
      <p>每门课都是一段可以完成的小旅程。完成练习后，做题系统会给出即时反馈。</p>
    </header>

    <p v-if="loading" class="state">正在加载课程…</p>
    <p v-else-if="error" class="state error">{{ error }}</p>

    <template v-else>
      <!-- 分类筛选：选中项写入 URL query，刷新/分享后保持 -->
      <nav
        v-if="categories.length && !useCategorySelect"
        class="category-bar"
        aria-label="课程分类筛选"
      >
        <button
          type="button"
          class="chip"
          :class="{ active: selectedCategory === null }"
          @click="selectCategory(null)"
        >
          全部
        </button>
        <button
          v-for="cat in categories"
          :key="cat.id"
          type="button"
          class="chip"
          :class="{ active: selectedCategory === cat.id }"
          @click="selectCategory(cat.id)"
        >
          {{ cat.name }}<span class="count">{{ cat.course_count }}</span>
        </button>
      </nav>
      <label v-else-if="categories.length" class="category-select">
        <span>课程分类</span>
        <select
          :value="selectedCategory ?? ''"
          @change="selectCategory($event.target.value ? Number($event.target.value) : null)"
        >
          <option value="">全部课程</option>
          <option v-for="cat in categories" :key="cat.id" :value="cat.id">
            {{ cat.name }}（{{ cat.course_count }}）
          </option>
        </select>
      </label>

      <p v-if="isEmpty" class="state">
        {{
          selectedCategory
            ? `「${selectedCategoryName}」分类下还没有已发布的课程。`
            : "还没有已发布的课程，敬请期待。"
        }}
      </p>

      <section v-else class="course-grid">
        <RouterLink
          v-for="(course, index) in courses"
          :key="course.id"
          class="course-card"
          :to="{ name: 'course-detail', params: { courseId: course.id }, query: { area: route.params.areaKey || 'kids' } }"
        >
          <img :src="cover(course, index)" :alt="course.title" />
          <span
            >{{ String(index + 1).padStart(2, "0") }} / {{ course.category_name || "课程" }}</span
          >
          <h2>{{ course.title }}</h2>
          <p>{{ subtitleOf(course) }}</p>
          <div class="meta">
            <span class="chip">{{ DIFFICULTY[course.difficulty] || course.difficulty }}</span>
            <span class="chip ghost"
              >{{ course.section_count }} 章 · {{ course.lesson_count }} 节</span
            >
          </div>
        </RouterLink>
      </section>
      <nav v-if="pageCount > 1" class="course-pager" aria-label="课程列表分页">
        <button type="button" class="chip ghost" :disabled="page <= 1" @click="load(page - 1)">
          上一页
        </button>
        <span>第 {{ page }} / {{ pageCount }} 页 · 共 {{ total }} 门</span>
        <button
          type="button"
          class="chip ghost"
          :disabled="page >= pageCount"
          @click="load(page + 1)"
        >
          下一页
        </button>
      </nav>
    </template>
  </main>
</template>

<style scoped>
.state {
  padding: 28px 0;
  color: var(--muted, #6b7280);
}
.state.error {
  color: #c0392b;
}
.category-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
}
.category-bar .chip {
  border: 1px solid var(--border, #e4e7ec);
  background: transparent;
  cursor: pointer;
  font: inherit;
}
.category-bar .chip:hover {
  border-color: #2f806e;
  color: #2f806e;
}
.category-bar .chip.active {
  background: rgba(47, 128, 110, 0.14);
  border-color: rgba(47, 128, 110, 0.5);
  color: #2f806e;
}
.category-bar .count {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.7;
}
.category-select {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  color: var(--muted, #6b7280);
  font-size: 13px;
}
.category-select select {
  min-height: 38px;
  max-width: min(100%, 320px);
  border: 1px solid var(--border, #e4e7ec);
  border-radius: 8px;
  background: #fff;
  color: inherit;
  padding: 0 10px;
  font: inherit;
}
.course-card {
  display: block;
  color: inherit;
  text-decoration: none;
}
.meta {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.course-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 28px;
  color: var(--muted, #6b7280);
  font-size: 13px;
}
.course-pager button:disabled {
  opacity: 0.45;
  cursor: default;
}
.chip {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(47, 128, 110, 0.12);
  color: #2f806e;
}
.chip.ghost {
  background: rgba(34, 43, 40, 0.07);
  color: var(--muted, #6b7280);
}
</style>
