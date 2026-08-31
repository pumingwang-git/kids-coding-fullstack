<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import AppIcon from "./components/AppIcon.vue";
import HelpWidget from "./components/help/HelpWidget.vue";
import { getCsrf, logout, request } from "./services/auth";
import { unreadNotificationCount } from "./services/notifications";
import { ensureSession, session } from "./stores/session";
import { activeHelpContext, helpEnabled } from "./stores/helpContext";
import { areaByKey, ensureLearningAreas } from "./stores/learningCatalog";
import {
  areaNavigationModules,
  learningModuleForRoute,
  questionBankNavigation,
} from "./stores/studentNavigation";
import { useSessionKeepalive } from "./composables/useSessionKeepalive";

const router = useRouter();
const route = useRoute();
const menuOpen = ref(false);
const dark = ref(localStorage.getItem("study-theme") === "dark");
const unreadNotifications = ref(0);
const helpContext = computed(() => {
  if (activeHelpContext.value) return activeHelpContext.value;
  if (route.name === "lesson-homework" && route.params.blockId) {
    return { context_type: "block", context_id: Number(route.params.blockId) };
  }
  return { context_type: "general" };
});

const shell = computed(() => {
  if (["exam", "lesson-homework", "lesson-player"].includes(String(route.name))) return "immersive";
  return route.meta.shell || "portal";
});
const isPortal = computed(() => shell.value === "portal");
const isLearning = computed(() => shell.value === "learning");
const displayName = computed(() => session.user?.username || "同学");
const activeArea = computed(() =>
  areaByKey(String(route.params.areaKey || route.query.area || route.meta.areaKey || "kids")),
);

const learningNav = computed(() => areaNavigationModules(activeArea.value));

const primaryMobileNav = computed(() =>
  learningNav.value.slice(0, learningNav.value.length > 4 ? 3 : 4),
);
const hasMoreNav = computed(() => learningNav.value.length > 4);
const settingsTarget = computed(() =>
  activeArea.value ? { path: "/settings", query: { area: activeArea.value.key } } : "/settings",
);

// 课程类型二级目录：跟随当前学习专区加载，渲染在侧边栏「课程」项下
const courseKinds = ref([]);
watch(
  () => activeArea.value?.key,
  async (key) => {
    courseKinds.value = [];
    if (!key) return;
    const hasCourses = (activeArea.value?.modules || []).some(
      (item) => item.module_key === "courses" && item.status !== "hidden",
    );
    if (!hasCourses) return;
    try {
      const data = await request(`/api/course-types?area_key=${encodeURIComponent(key)}`);
      courseKinds.value = data.items || [];
    } catch {
      courseKinds.value = [];
    }
  },
  { immediate: true },
);

function courseKindActive(kind, index) {
  if (String(route.name) !== "area-courses") return false;
  const current = String(route.query.kind || "");
  if (!current) return index === 0;
  return current === kind.key;
}

function courseKindTarget(kind, index) {
  return {
    name: "area-courses",
    params: { areaKey: activeArea.value?.key || "kids" },
    query: index === 0 ? {} : { kind: kind.key },
  };
}

const activeLearningModule = computed(() => learningModuleForRoute(route));
const moreNavActive = computed(() => {
  if (route.params.moduleKey === "more") return true;
  if (!activeLearningModule.value) return false;
  const isKnownModule = learningNav.value.some(
    (item) => item.module_key === activeLearningModule.value,
  );
  const isPrimaryModule = primaryMobileNav.value.some(
    (item) => item.module_key === activeLearningModule.value,
  );
  return isKnownModule && !isPrimaryModule;
});

function learningNavActive(item) {
  return activeLearningModule.value === item.module_key;
}

// 哪些模块支持手风琴二级展开
const accordionModules = new Set(["courses", "explore", "tasks", "question-bank"]);

// 二级导航折叠状态（手风琴模式：同时只展开一个）
const expanded = ref(new Set());
function openOnly(key) {
  expanded.value = new Set([key]);
}
function toggleExpand(key) {
  expanded.value = expanded.value.has(key) ? new Set() : new Set([key]);
}
function isExpanded(key) {
  return expanded.value.has(key);
}

function questionBankSubNav(areaKey) {
  return questionBankNavigation(areaKey);
}

function questionBankSubActive(item) {
  if (String(route.name) === "area-mistake-detail") return item.routeName === "area-mistakes";
  return String(route.name) === item.routeName;
}

watch(
  activeLearningModule,
  (moduleKey) => {
    expanded.value = accordionModules.has(moduleKey) ? new Set([moduleKey]) : new Set();
  },
  { immediate: true },
);

// 探索创作二级导航（只保留已实现的页面）
function exploreSubNav(areaKey) {
  return [
    { label: "作品广场", to: `/areas/${areaKey}/explore` },
    { label: "我的作品", to: `/areas/${areaKey}/explore/projects` },
    { label: "创作中心", to: `/areas/${areaKey}/create` },
  ];
}

function exploreSubActive(item) {
  const name = String(route.name);
  if (item.to.endsWith("/explore")) return name === "area-explore";
  if (item.to.endsWith("/projects")) return name === "area-projects";
  if (item.to.endsWith("/create")) return name === "area-create";
  return false;
}

// 任务二级导航（只保留已实现的页面）
function tasksSubNav(areaKey) {
  return [
    { label: "任务总览", to: `/areas/${areaKey}/tasks` },
    { label: "练一练", to: `/areas/${areaKey}/tasks/practice` },
    { label: "我的作业", to: `/areas/${areaKey}/tasks/homework` },
    { label: "我的考试", to: `/areas/${areaKey}/tasks/exams` },
  ];
}

function tasksSubActive(item) {
  const name = String(route.name);
  if (item.to.endsWith("/tasks")) return name === "area-tasks";
  if (item.to.endsWith("/practice")) return name === "area-practice";
  if (item.to.endsWith("/homework")) return name === "area-homework";
  if (item.to.endsWith("/exams")) return name === "area-exams";
  return false;
}
function applyTheme() {
  document.documentElement.classList.toggle("dark", dark.value);
}

function toggleTheme() {
  dark.value = !dark.value;
  localStorage.setItem("study-theme", dark.value ? "dark" : "light");
  applyTheme();
}

async function signOut() {
  await logout();
  session.user = null;
  session.loaded = false;
  await getCsrf();
  router.push({ name: "home" });
}

function onSessionExpired() {
  session.user = null;
  session.loaded = false;
  if (route.meta.requiresAuth && route.path !== "/auth") {
    router.replace({ path: "/auth", query: { next: route.fullPath } });
  }
}

watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false;
  },
);
useSessionKeepalive();
onMounted(() => window.addEventListener("session:expired", onSessionExpired));
onBeforeUnmount(() => window.removeEventListener("session:expired", onSessionExpired));

onMounted(async () => {
  applyTheme();
  await Promise.all([
    getCsrf().catch(() => {}),
    ensureSession(),
    ensureLearningAreas().catch(() => []),
  ]);
  if (session.user) {
    unreadNotificationCount()
      .then((data) => {
        unreadNotifications.value = Number(data.count || 0);
      })
      .catch(() => {});
  }
});
</script>

<template>
  <template v-if="isPortal">
    <header class="app-header">
      <RouterLink class="brand" to="/" aria-label="返回网站首页">
        <img :src="'/assets/otter-avatar-128.webp'" alt="" width="44" height="44" />
        <span>汪蒲明学习平台</span>
      </RouterLink>
      <button
        class="portal-menu-button"
        type="button"
        :aria-expanded="menuOpen"
        aria-controls="portal-navigation"
        :aria-label="menuOpen ? '关闭主导航' : '打开主导航'"
        @click="menuOpen = !menuOpen"
      >
        <AppIcon :name="menuOpen ? 'close' : 'menu'" />
      </button>
      <nav id="portal-navigation" :class="{ open: menuOpen }" aria-label="全站导航">
        <RouterLink to="/">首页</RouterLink>
        <RouterLink to="/learning">学习专区</RouterLink>
        <RouterLink to="/project">项目介绍</RouterLink>
        <RouterLink to="/blog">博客</RouterLink>
      </nav>
      <div class="header-actions" :class="{ open: menuOpen }">
        <a class="user-menu" href="/admin/login.html">后台管理</a>
        <RouterLink v-if="!session.user" class="login-link" to="/auth">登录</RouterLink>
        <RouterLink v-else class="login-link" to="/study">进入学习</RouterLink>
        <button
          class="theme-toggle"
          type="button"
          :aria-label="dark ? '切换浅色主题' : '切换深色主题'"
          @click="toggleTheme"
        >
          <AppIcon :name="dark ? 'sun' : 'moon'" />
        </button>
      </div>
    </header>
    <RouterView />
    <footer class="site-record" aria-label="网站备案信息">
      <a href="https://beian.miit.gov.cn/" target="_blank" rel="noreferrer">
        <span>晋ICP备2026010787号-1</span>
      </a>
      <a
        href="https://beian.mps.gov.cn/#/query/webSearch?code=14102402000497"
        target="_blank"
        rel="noreferrer"
      >
        <img src="/assets/beian-icon.png" alt="" width="16" height="16" />
        <span>晋公网安备14102402000497号</span>
      </a>
    </footer>
  </template>

  <div
    v-else-if="isLearning"
    class="kids-shell"
    :data-area-theme="activeArea?.theme_key || 'default'"
  >
    <aside class="kids-sidebar" :aria-label="`${activeArea?.name || '学习'}专区导航`">
      <RouterLink class="kids-brand" :to="activeArea ? `/areas/${activeArea.key}` : '/learning'">
        <img :src="'/assets/otter-avatar-128.webp'" alt="" width="44" height="44" />
        <span
          ><b>{{ activeArea?.name || "学习专区" }}</b
          ><small>学习空间</small></span
        >
      </RouterLink>
      <nav>
        <template v-for="item in learningNav" :key="item.to">
          <div class="nav-row">
            <RouterLink
              :to="item.to"
              active-class="nav-route-match"
              exact-active-class="nav-route-exact"
              :class="{
                'nav-current': learningNavActive(item),
                'nav-inactive': !learningNavActive(item),
              }"
              :aria-current="learningNavActive(item) ? 'page' : undefined"
              @click="accordionModules.has(item.module_key) ? openOnly(item.module_key) : null"
            >
              <AppIcon :name="item.icon" />
              <span>{{ item.label }}</span>
            </RouterLink>
            <button
              v-if="accordionModules.has(item.module_key)"
              type="button"
              class="collapse-toggle"
              :aria-label="isExpanded(item.module_key) ? '收起' : '展开'"
              @click.prevent="toggleExpand(item.module_key)"
            >
              <AppIcon :name="isExpanded(item.module_key) ? 'chevron-up' : 'chevron-down'" />
            </button>
          </div>
          <div
            v-if="item.module_key === 'courses' && isExpanded('courses') && courseKinds.length"
            class="kids-subnav"
            aria-label="课程类型"
          >
            <RouterLink
              v-for="(kind, index) in courseKinds"
              :key="kind.key"
              :to="courseKindTarget(kind, index)"
              :class="{ 'subnav-current': courseKindActive(kind, index) }"
              :aria-current="courseKindActive(kind, index) ? 'page' : undefined"
            >
              <span class="subnav-dot" aria-hidden="true"></span>{{ kind.name }}
            </RouterLink>
          </div>
          <div
            v-if="item.module_key === 'explore' && isExpanded('explore')"
            class="kids-subnav"
            aria-label="探索创作"
          >
            <RouterLink
              v-for="sub in exploreSubNav(activeArea?.key || 'kids')"
              :key="sub.to"
              :to="sub.to"
              :class="{ 'subnav-current': exploreSubActive(sub) }"
              :aria-current="exploreSubActive(sub) ? 'page' : undefined"
            >
              <span class="subnav-dot" aria-hidden="true"></span>{{ sub.label }}
            </RouterLink>
          </div>
          <div
            v-if="item.module_key === 'tasks' && isExpanded('tasks')"
            class="kids-subnav"
            aria-label="任务中心"
          >
            <RouterLink
              v-for="sub in tasksSubNav(activeArea?.key || 'kids')"
              :key="sub.to"
              :to="sub.to"
              :class="{ 'subnav-current': tasksSubActive(sub) }"
              :aria-current="tasksSubActive(sub) ? 'page' : undefined"
            >
              <span class="subnav-dot" aria-hidden="true"></span>{{ sub.label }}
            </RouterLink>
          </div>
          <div
            v-if="item.module_key === 'question-bank' && isExpanded('question-bank')"
            class="kids-subnav"
            aria-label="题库"
          >
            <RouterLink
              v-for="sub in questionBankSubNav(activeArea?.key || 'kids')"
              :key="sub.to"
              :to="sub.to"
              :class="{ 'subnav-current': questionBankSubActive(sub) }"
              :aria-current="questionBankSubActive(sub) ? 'page' : undefined"
            >
              <span class="subnav-dot" aria-hidden="true"></span>{{ sub.label }}
            </RouterLink>
          </div>
        </template>
      </nav>
      <div class="kids-sidebar-foot">
        <RouterLink to="/" class="quiet-link"
          ><AppIcon name="arrow-left" /> 返回网站首页</RouterLink
        >
        <RouterLink :to="settingsTarget" class="quiet-link"
          ><AppIcon name="settings" /> 设置</RouterLink
        >
      </div>
    </aside>

    <section class="kids-stage">
      <header class="kids-topbar">
        <div>
          <span class="kids-area-dot" aria-hidden="true"></span>
          <span>{{ activeArea?.name || "学习专区" }}学习空间</span>
        </div>
        <div class="kids-user-actions">
          <RouterLink to="/notifications" class="kids-notifications" aria-label="通知中心">
            <AppIcon name="bell" /><span>通知</span
            ><b v-if="unreadNotifications" class="notification-badge">{{
              unreadNotifications > 99 ? "99+" : unreadNotifications
            }}</b>
          </RouterLink>
          <!-- 顶部头像进个人资料（文档 28 §2.1），带当前专区让「错题本/工具箱」落对地方 -->
          <RouterLink
            :to="activeArea ? { path: '/profile', query: { area: activeArea.key } } : '/profile'"
            class="kids-user"
          >
            <img
              :src="session.user?.avatar_url || '/assets/otter-avatar-128.webp'"
              alt=""
              width="32"
              height="32"
            />{{ displayName }}</RouterLink
          >
          <button type="button" @click="signOut">退出</button>
        </div>
      </header>
      <RouterView />
    </section>

    <nav class="kids-bottom-nav" :aria-label="`${activeArea?.name || '学习'}移动导航`">
      <RouterLink
        v-for="item in primaryMobileNav"
        :key="item.to"
        :to="item.to"
        active-class="nav-route-match"
        exact-active-class="nav-route-exact"
        :class="{
          'nav-current': learningNavActive(item),
          'nav-inactive': !learningNavActive(item),
        }"
        :aria-current="learningNavActive(item) ? 'page' : undefined"
      >
        <AppIcon :name="item.icon" />
        <span>{{ item.label.replace("学习", "") || item.label }}</span>
      </RouterLink>
      <RouterLink
        v-if="hasMoreNav"
        :to="`/areas/${activeArea.key}/more`"
        :class="{ 'nav-current': moreNavActive }"
        :aria-current="moreNavActive ? 'page' : undefined"
      >
        <AppIcon name="menu" /><span>更多</span>
      </RouterLink>
    </nav>
  </div>

  <RouterView v-else />
  <HelpWidget
    v-if="session.user && helpEnabled"
    :context="helpContext"
    :initial-line-id="route.query.help_line || null"
  />
</template>
