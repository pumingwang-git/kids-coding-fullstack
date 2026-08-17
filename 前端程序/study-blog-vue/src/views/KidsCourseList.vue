<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { request } from "../services/auth";

const route = useRoute();
const router = useRouter();
const areaKey = computed(() => String(route.params.areaKey || "kids"));
const otters = [
  "/assets/otter-writing.png",
  "/assets/otter-thinking-720.webp",
  "/assets/otter-coding-720.webp",
];
const difficulty = { beginner: "入门", intermediate: "进阶", advanced: "高阶" };
const kinds = ref([]);
const taxonomy = ref([]);
const tags = ref([]);
const area = ref(null);
const selectedKind = ref(String(route.query.kind || ""));
const selectedCategory = ref(
  route.query.category && /^\d+$/.test(String(route.query.category))
    ? Number(route.query.category)
    : null,
);
const selectedTag = ref(
  route.query.tag && /^\d+$/.test(String(route.query.tag)) ? Number(route.query.tag) : null,
);
const courses = ref([]);
const categories = ref([]);
const page = ref(1);
const total = ref(0);
const loading = ref(true);
const error = ref("");
const pageSize = 24;
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const isEmpty = computed(() => !loading.value && !error.value && courses.value.length === 0);
const selectedCategoryName = computed(
  () => flattenTaxonomy(taxonomy.value).find((item) => item.id === selectedCategory.value)?.name || "",
);
const selectedDirection = computed(() => {
  if (!selectedCategory.value) return null;
  const direct = taxonomy.value.find((item) => item.id === selectedCategory.value);
  if (direct) return direct;
  return taxonomy.value.find((item) =>
    (item.children || []).some((child) => child.id === selectedCategory.value),
  ) || null;
});

function flattenTaxonomy(items) {
  return items.flatMap((item) => [item, ...flattenTaxonomy(item.children || [])]);
}

function cover(course, index) {
  return course.cover_url || otters[index % otters.length];
}
function subtitleOf(course) {
  if (course.subtitle) return course.subtitle;
  const parts = [];
  if (course.lesson_count) parts.push(`${course.lesson_count} 课时`);
  if (course.total_minutes) parts.push(`约 ${course.total_minutes} 分钟`);
  return parts.join(" · ") || "课程内容准备中";
}

async function loadCategories() {
  const query = new URLSearchParams({ area_key: areaKey.value });
  const tagQuery = new URLSearchParams({
    area_key: areaKey.value,
  });
  if (selectedKind.value) tagQuery.set("course_kind", selectedKind.value);
  if (selectedCategory.value) tagQuery.set("category_id", String(selectedCategory.value));
  const [areaData, typeData, treeData, tagData] = await Promise.all([
    request(`/api/learning-areas/${areaKey.value}`),
    request(`/api/course-types?${query}`),
    request(`/api/course-taxonomy?${query}`),
    request(`/api/course-tags?${tagQuery}`),
  ]);
  area.value = areaData;
  kinds.value = typeData.items || [];
  taxonomy.value = treeData.items || [];
  tags.value = tagData.items || [];
  categories.value = taxonomy.value;
  if (!kinds.value.some((item) => item.key === selectedKind.value)) selectedKind.value = kinds.value[0]?.key || "";
  if (
    selectedCategory.value &&
    !flattenTaxonomy(taxonomy.value).some((item) => item.id === selectedCategory.value)
  )
    selectedCategory.value = null;
  if (selectedTag.value && !tags.value.some((item) => item.id === selectedTag.value))
    selectedTag.value = null;
}

async function load(nextPage = 1) {
  loading.value = true;
  error.value = "";
  try {
    const params = new URLSearchParams({
      page: String(nextPage),
      page_size: String(pageSize),
      area_key: areaKey.value,
      course_kind: selectedKind.value,
    });
    if (selectedCategory.value) params.set("category_id", String(selectedCategory.value));
    if (selectedTag.value) params.set("tag_id", String(selectedTag.value));
    const data = await request(`/api/courses?${params}`);
    courses.value = data.items || [];
    total.value = data.total || 0;
    page.value = data.page || nextPage;
  } catch (err) {
    error.value = err?.message || "课程列表加载失败，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

async function selectKind(kind) {
  if (kind === selectedKind.value) return;
  selectedKind.value = kind;
  selectedCategory.value = null;
  selectedTag.value = null;
  await router.replace({ query: kind === kinds.value[0]?.key ? {} : { kind } });
  try {
    await loadCategories();
  } catch {
    categories.value = [];
  }
  await load(1);
}

function queryForCurrentSelection() {
  const query = {};
  if (selectedKind.value !== kinds.value[0]?.key) query.kind = selectedKind.value;
  if (selectedCategory.value) query.category = String(selectedCategory.value);
  if (selectedTag.value) query.tag = String(selectedTag.value);
  return query;
}

async function selectDirection(categoryId) {
  selectedCategory.value = categoryId;
  selectedTag.value = null;
  await router.replace({ query: queryForCurrentSelection() });
  await loadCategories();
  await load(1);
}

async function selectCategory(categoryId) {
  selectedCategory.value = categoryId;
  selectedTag.value = null;
  await router.replace({ query: queryForCurrentSelection() });
  await loadCategories();
  await load(1);
}

async function selectTag(tagId) {
  selectedTag.value = tagId;
  await router.replace({ query: queryForCurrentSelection() });
  await load(1);
}

async function initialize() {
  try {
    await loadCategories();
  } catch {
    categories.value = [];
  }
  await load();
}

onMounted(initialize);
watch(areaKey, initialize);

// 侧边栏二级目录切换课程类型时，同步页面内的选中类型
watch(
  () => route.query.kind,
  async (value) => {
    if (!kinds.value.length) return;
    const next = String(value || kinds.value[0]?.key || "");
    if (next === selectedKind.value) return;
    if (!kinds.value.some((item) => item.key === next)) return;
    selectedKind.value = next;
    selectedCategory.value = null;
    selectedTag.value = null;
    try {
      await loadCategories();
    } catch {
      categories.value = [];
    }
    await load(1);
  },
);
</script>

<template>
  <main class="kids-page courses-page">
    <header class="courses-heading">
      <div>
        <h1>{{ area?.name || "学习专区" }}课程</h1>
        <span>先选课程类型和学习方向，再按课程特色进一步筛选。</span>
      </div>
      <img :src="'/assets/otter-reading.png'" alt="水獭正在选择课程" />
    </header>

    <!-- 课程类型：桌面端在左侧目录二级导航切换，此处仅移动端显示 -->
    <nav class="course-kind-mobile" aria-label="课程类型">
      <button
        v-for="kind in kinds"
        :key="kind.key"
        type="button"
        :class="{ active: selectedKind === kind.key }"
        @click="selectKind(kind.key)"
      >
        {{ kind.name }}
      </button>
    </nav>

    <nav class="course-direction-bar" aria-label="学习方向筛选">
      <button
        type="button"
        class="dir-tab"
        :class="{ active: selectedCategory === null }"
        @click="selectDirection(null)"
      >
        全部方向
      </button>
      <button
        v-for="cat in taxonomy"
        :key="cat.id"
        type="button"
        class="dir-tab"
        :class="{ active: selectedDirection?.id === cat.id }"
        @click="selectDirection(cat.id)"
      >
        {{ cat.name }}<span>{{ cat.course_count }}</span>
      </button>
    </nav>

    <nav
      v-if="selectedDirection?.children?.length"
      class="category-bar topic-bar"
      aria-label="学习主题筛选"
    >
      <span class="filter-label">主题</span>
      <button
        type="button"
        class="chip"
        :class="{ active: selectedCategory === selectedDirection.id }"
        @click="selectCategory(selectedDirection.id)"
      >
        全部
      </button>
      <button
        v-for="topic in selectedDirection.children"
        :key="topic.id"
        type="button"
        class="chip"
        :class="{ active: selectedCategory === topic.id }"
        @click="selectCategory(topic.id)"
      >
        {{ topic.name }}<span>{{ topic.course_count }}</span>
      </button>
    </nav>

    <nav v-if="selectedDirection && tags.length" class="category-bar tag-bar" aria-label="课程特色筛选">
      <span class="filter-label">课程特色</span>
      <button type="button" class="chip" :class="{ active: selectedTag === null }" @click="selectTag(null)">全部</button>
      <button v-for="tag in tags" :key="tag.id" type="button" class="chip" :class="{ active: selectedTag === tag.id }" @click="selectTag(tag.id)">{{ tag.name }}<span>{{ tag.course_count }}</span></button>
    </nav>

    <div v-if="loading" class="course-state">
      <span class="state-pulse"></span>
      <p>正在加载课程…</p>
    </div>
    <div v-else-if="error" class="course-state error">
      <p>{{ error }}</p>
      <button type="button" @click="load(page)">重新加载</button>
    </div>
    <div v-else-if="isEmpty" class="course-state empty">
      <img :src="'/assets/otter-thinking-720.webp'" alt="暂时没有课程" />
      <div>
        <h2>
          {{
            selectedCategory
              ? `“${selectedCategoryName}”下还没有已发布课程`
              : "这里还没有已发布课程"
          }}
        </h2>
        <p>课程发布后会显示真实内容，目前不使用演示课程填充。</p>
      </div>
    </div>

    <section v-else class="kids-course-list">
      <RouterLink
        v-for="(course, index) in courses"
        :key="course.id"
        :to="{ name: 'course-detail', params: { courseId: course.id }, query: { area: areaKey } }"
        class="kids-course-card"
      >
        <div class="course-cover">
          <img :src="cover(course, index)" :alt="course.title" /><span>{{
            course.category_breadcrumb?.map((item) => item.name).join(" / ") || area?.name || "课程"
          }}</span>
        </div>
        <div class="course-copy">
          <div>
            <span>{{ kinds.find((item) => item.key === course.course_kind)?.name || course.course_kind }}</span
            ><span>{{ difficulty[course.difficulty] || course.difficulty }}</span>
          </div>
          <h2>{{ course.title }}</h2>
          <p>{{ subtitleOf(course) }}</p>
          <small>{{ course.section_count }} 章 · {{ course.lesson_count }} 节</small>
        </div>
        <span class="course-enter">开始学习 <AppIcon name="arrow-right" /></span>
      </RouterLink>
    </section>

    <nav v-if="pageCount > 1" class="course-pager" aria-label="课程列表分页">
      <button type="button" :disabled="page <= 1" @click="load(page - 1)">上一页</button
      ><span>第 {{ page }} / {{ pageCount }} 页 · 共 {{ total }} 门</span
      ><button type="button" :disabled="page >= pageCount" @click="load(page + 1)">下一页</button>
    </nav>
  </main>
</template>

<style scoped>
.courses-page {
  max-width: 1120px;
}
.courses-heading {
  position: relative;
  min-height: 210px;
  overflow: hidden;
  display: flex;
  align-items: center;
  padding: 36px 44px;
  border-radius: 30px 9px 30px 9px;
  background: #dcecff;
  color: #203c5b;
}
.courses-heading h1 {
  max-width: 720px;
  margin: 0;
  font: 900 clamp(31px, 4vw, 48px) / 1.2 var(--font-display);
  letter-spacing: -0.04em;
}
.courses-heading span {
  display: block;
  margin-top: 10px;
  color: #54708d;
}
.courses-heading img {
  position: absolute;
  right: 3%;
  bottom: -44px;
  width: 235px;
  height: 255px;
  object-fit: contain;
  opacity: 0.88;
}
/* 课程类型移动端切换条（桌面端由侧边栏二级目录承担） */
.course-kind-mobile {
  display: none;
}
/* 学习方向横向 Tab 栏 */
.course-direction-bar {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  margin: 20px 0 12px;
  padding: 4px 2px 10px;
  scrollbar-width: thin;
}
.course-direction-bar .dir-tab {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 10px 18px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 999px;
  background: var(--kids-panel, #fdfdf8);
  color: #65798e;
  font: inherit;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}
.course-direction-bar .dir-tab span {
  font-size: 11px;
  opacity: 0.6;
}
.course-direction-bar .dir-tab:hover {
  border-color: #4d82c2;
  color: #4d82c2;
}
.course-direction-bar .dir-tab.active {
  border-color: #4d82c2;
  background: #4d82c2;
  color: #fff;
}
.course-direction-bar .dir-tab.active span {
  opacity: 0.85;
}
.category-bar {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  margin: 0 0 20px;
  padding: 8px 2px 10px;
  scrollbar-width: thin;
}
.category-bar .chip {
  flex: 0 0 auto;
  padding: 9px 14px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 999px;
  background: transparent;
  color: #65798e;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}
.category-bar .chip.active {
  border-color: #4d82c2;
  background: #4d82c2;
  color: #fff;
}
.category-bar .chip span {
  margin-left: 6px;
  opacity: 0.72;
}
.topic-bar { margin-bottom: 10px; }
.tag-bar { margin-top: -2px; }
.filter-label { flex: 0 0 auto; align-self: center; color: #718397; font-size: 12px; font-weight: 900; }
.kids-course-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.kids-course-card {
  position: relative;
  overflow: hidden;
  min-height: 218px;
  display: grid;
  grid-template-columns: 42% 1fr;
  border: 1px solid rgba(55, 87, 123, 0.13);
  border-radius: 20px 7px 20px 7px;
  background: var(--kids-panel, #fdfdf8);
}
.course-cover {
  position: relative;
  min-height: 218px;
  background: #eef5fc;
}
.course-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.course-cover > span {
  position: absolute;
  left: 10px;
  top: 10px;
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #4d82c2;
  font-size: 11px;
  font-weight: 900;
}
.course-copy {
  min-width: 0;
  padding: 24px 22px 48px;
}
.course-copy > div {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.course-copy > div span {
  color: #ef6b4a;
  font-size: 11px;
  font-weight: 900;
}
.course-copy h2 {
  margin: 12px 0 8px;
  font-size: 20px;
  line-height: 1.45;
}
.course-copy p {
  margin: 0 0 13px;
  color: #6d8094;
  font-size: 13px;
  line-height: 1.65;
}
.course-copy small {
  color: #8292a3;
}
.course-enter {
  position: absolute;
  right: 20px;
  bottom: 18px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #4d82c2;
  font-size: 12px;
  font-weight: 900;
}
.course-state {
  min-height: 250px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: #718397;
}
.course-state.empty img {
  width: 150px;
  height: 140px;
  object-fit: contain;
}
.course-state h2 {
  margin: 0 0 8px;
  color: inherit;
  font-size: 19px;
}
.course-state p {
  margin: 0;
}
.course-state button,
.course-pager button {
  padding: 8px 13px;
  border: 1px solid rgba(55, 87, 123, 0.18);
  border-radius: 999px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.state-pulse {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #4d82c2;
  animation: pulse 1.2s ease-in-out infinite;
}
.course-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 28px;
  color: #718397;
  font-size: 13px;
}
.course-pager button:disabled {
  opacity: 0.4;
  cursor: default;
}
@keyframes pulse {
  50% {
    transform: scale(0.55);
    opacity: 0.45;
  }
}
@media (max-width: 900px) {
  .kids-course-list {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 800px) {
  /* 侧边栏隐藏后，课程类型切换兜底为横向 pill 条 */
  .course-kind-mobile {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    margin: 16px 0 0;
    padding: 4px 2px 8px;
    scrollbar-width: thin;
  }
  .course-kind-mobile button {
    flex: 0 0 auto;
    padding: 9px 18px;
    border: 1px solid rgba(55, 87, 123, 0.14);
    border-radius: 999px;
    background: var(--kids-panel, #fdfdf8);
    color: #65798e;
    font: inherit;
    font-size: 14px;
    font-weight: 800;
    cursor: pointer;
  }
  .course-kind-mobile button.active {
    border-color: #ef6b4a;
    background: #ef6b4a;
    color: #fff;
  }
}
@media (max-width: 600px) {
  .courses-heading {
    min-height: 220px;
    align-items: flex-start;
    padding: 28px 24px;
  }
  .courses-heading img {
    width: 170px;
    height: 180px;
    right: -24px;
    opacity: 0.3;
  }
  .kids-course-card {
    grid-template-columns: 116px 1fr;
    min-height: 190px;
  }
  .course-cover {
    min-height: 190px;
  }
  .course-copy {
    padding: 18px 16px 46px;
  }
  .course-copy h2 {
    font-size: 17px;
  }
  .course-state.empty {
    align-items: flex-start;
    flex-direction: column;
  }
}
@media (prefers-reduced-motion: reduce) {
  .state-pulse {
    animation: none;
  }
}
</style>
