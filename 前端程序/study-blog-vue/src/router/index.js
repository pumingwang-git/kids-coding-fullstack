import { createRouter, createWebHistory } from "vue-router";
import PortalHome from "../views/PortalHome.vue";
import LearningAreas from "../views/LearningAreas.vue";
import ProjectHome from "../views/ProjectHome.vue";
import BlogHome from "../views/BlogPlanning.vue";
import TasksHome from "../views/TasksHome.vue";
import ExploreHome from "../views/ExploreHome.vue";
import PlanningPage from "../views/PlanningPage.vue";
import AuthView from "../views/AuthView.vue";
import VerifyEmail from "../views/VerifyEmail.vue";
import CourseList from "../views/KidsCourseList.vue";
import SecurityView from "../views/SecurityView.vue";
import ForgotPasswordView from "../views/ForgotPasswordView.vue";
import LearningAreaIntro from "../views/LearningAreaIntro.vue";
import AreaOverview from "../views/AreaOverview.vue";
import AreaModulePage from "../views/AreaModulePage.vue";
import MyWorks from "../views/MyWorks.vue";
import CreateHub from "../views/CreateHub.vue";
import ToolboxHome from "../views/ToolboxHome.vue";
import MistakeBook from "../views/MistakeBook.vue";
import MistakeDetail from "../views/MistakeDetail.vue";
import MistakeReview from "../views/MistakeReview.vue";
import MistakeStats from "../views/MistakeStats.vue";
import { ensureSession, session } from "../stores/session";
import { areaByKey, ensureLearningAreas } from "../stores/learningCatalog";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: PortalHome, meta: { shell: "portal" } },
    { path: "/learning", name: "learning", component: LearningAreas, meta: { shell: "portal" } },
    {
      path: "/learning/:areaKey",
      name: "learning-area-intro",
      component: LearningAreaIntro,
      meta: { shell: "portal" },
    },
    { path: "/project", name: "project", component: ProjectHome, meta: { shell: "portal" } },
    { path: "/blog", name: "blog", component: BlogHome, meta: { shell: "portal" } },
    {
      path: "/study",
      redirect: "/areas/kids",
    },
    { path: "/auth", name: "auth", component: AuthView, meta: { guestOnly: true } },
    { path: "/forgot-password", name: "forgot-password", component: ForgotPasswordView },
    {
      path: "/security",
      name: "security",
      component: SecurityView,
      meta: { requiresAuth: true, shell: "learning", areaKey: "kids" },
    },
    // 学生个人资料（文档 28 P2）：由页面顶部头像进入，不进专区导航。
    // 懒加载——头像上传/学习概览不是博客首页该背的包。
    {
      path: "/profile",
      name: "profile",
      component: () => import("../views/StudentProfile.vue"),
      meta: { requiresAuth: true, shell: "learning" },
    },
    // 学生设置页（文档 28 §2.1/§6.4）：首版只承载「账号与安全」入口，跳既有 /security。
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/SettingsView.vue"),
      meta: { requiresAuth: true, shell: "learning" },
    },
    { path: "/verify-email", name: "verify-email", component: VerifyEmail },
    {
      path: "/areas/:areaKey",
      name: "area-overview",
      component: AreaOverview,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/courses",
      name: "area-courses",
      component: CourseList,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/tasks",
      name: "area-tasks",
      component: TasksHome,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/tasks/mistakes",
      name: "area-mistakes",
      component: MistakeBook,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/tasks/mistakes/review",
      name: "area-mistake-review",
      component: MistakeReview,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/tasks/mistakes/stats",
      name: "area-mistake-stats",
      component: MistakeStats,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/tasks/mistakes/:mistakeId",
      name: "area-mistake-detail",
      component: MistakeDetail,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/explore",
      name: "area-explore",
      component: ExploreHome,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/:moduleKey",
      name: "area-module",
      component: AreaModulePage,
      meta: { requiresAuth: true, shell: "learning" },
    },
    ...[
      ["practice", "练一练", "从课程内容出发完成即时练习，巩固刚学会的知识。", "tasks"],
      ["homework", "我的作业", "集中查看老师布置的作业、提交状态与反馈。", "tasks"],
      ["exams", "我的考试", "普通考试与课程测验会在这里统一管理。", "tasks"],
      ["activities", "活动", "主题活动与创作挑战将在准备完成后开放。", "explore"],
      ["competitions", "竞赛", "竞赛报名、作品提交与结果查询将归在这里。", "explore"],
      ["live", "直播", "直播课程尚在规划中，目前不会展示虚构场次。", "explore"],
    ].map(([key, title, description, parent]) => ({
      path: `/areas/:areaKey/${parent}/${key}`,
      name: `area-${key}`,
      component: PlanningPage,
      props: (route) => ({ title, description, parent, areaKey: route.params.areaKey }),
      meta: { requiresAuth: true, shell: "learning" },
    })),
    // 「我的作品」是真实功能页，不走 PlanningPage 占位：学生自由创作的 Scratch
    // 作品在这里管理（新建 / 编辑 / 公开切换 / 删除），公开作品进广场展出。
    {
      path: "/areas/:areaKey/explore/projects",
      name: "area-projects",
      component: MyWorks,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/areas/:areaKey/create",
      name: "area-create",
      component: CreateHub,
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/courses",
      redirect: "/areas/kids/courses",
    },
    {
      path: "/tasks",
      redirect: "/areas/kids/tasks",
    },
    {
      path: "/explore",
      redirect: "/areas/kids/explore",
    },
    {
      path: "/practice",
      name: "practice",
      component: PlanningPage,
      props: {
        title: "练一练",
        description: "从课程内容出发完成即时练习，巩固刚学会的知识。",
        parent: "tasks",
      },
      meta: { requiresAuth: true, shell: "learning" },
    },
    {
      path: "/homework",
      name: "homework",
      component: PlanningPage,
      props: {
        title: "我的作业",
        description: "集中查看老师布置的作业、提交状态与反馈。",
        parent: "tasks",
      },
      meta: { requiresAuth: true, shell: "kids" },
    },
    {
      path: "/exams",
      name: "exams",
      component: PlanningPage,
      props: {
        title: "我的考试",
        description: "普通考试与课程测验会在这里统一管理。",
        parent: "tasks",
      },
      meta: { requiresAuth: true, shell: "kids" },
    },
    {
      path: "/projects",
      name: "projects",
      component: MyWorks,
      meta: { requiresAuth: true, shell: "kids" },
    },
    {
      path: "/activities",
      name: "activities",
      component: PlanningPage,
      props: {
        title: "活动",
        description: "主题活动与创作挑战将在准备完成后开放。",
        parent: "explore",
      },
      meta: { requiresAuth: true, shell: "kids" },
    },
    {
      path: "/competitions",
      name: "competitions",
      component: PlanningPage,
      props: {
        title: "竞赛",
        description: "竞赛报名、作品提交与结果查询将归在这里。",
        parent: "explore",
      },
      meta: { requiresAuth: true, shell: "kids" },
    },
    {
      path: "/live",
      name: "live",
      component: PlanningPage,
      props: {
        title: "直播",
        description: "直播课程尚在规划中，目前不会展示虚构场次。",
        parent: "explore",
      },
      meta: { requiresAuth: true, shell: "kids" },
    },
    // 课包详情（章节课时目录）。/courses/:id 里的 id 是**课包**——早期这个位置被课时
    // 播放页占用（/courses/:lessonId），课程模块后端化后必须让给课包，播放页移到 /learn。
    {
      path: "/courses/:courseId(\\d+)",
      name: "course-detail",
      component: () => import("../views/CourseDetail.vue"),
      meta: { requiresAuth: true, shell: "learning", learningModule: "courses" },
    },
    // 课时学习页：从课包目录点进来。懒加载——它拖着 Video.js，博客首页不该为它买单。
    {
      path: "/learn/:lessonId(\\d+)",
      name: "lesson-player",
      component: () => import("../views/LessonPlayer.vue"),
      meta: { requiresAuth: true, shell: "immersive" },
    },
    {
      path: "/learn/:lessonId(\\d+)/homework/:blockId(\\d+)",
      name: "lesson-homework",
      component: () => import("../views/ExamView.vue"),
      meta: { requiresAuth: true, shell: "immersive" },
    },
    // 考试链接：管理员复制的地址就是这个路径。requiresAuth 让守卫自动跳
    // /auth?next=/exam/xxx——成绩要记在学员名下，链接不绕过登录。
    // 懒加载：考试页拖着 CodeMirror / marked / DOMPurify，博客首页不该为它买单。
    {
      path: "/exam/:token",
      name: "exam",
      component: () => import("../views/ExamView.vue"),
      meta: { requiresAuth: true, shell: "immersive" },
    },
    {
      path: "/areas/:areaKey/toolbox",
      name: "area-toolbox",
      component: ToolboxHome,
      meta: { requiresAuth: true, shell: "learning" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

const LEGACY_AREA_PATHS = {
  "/study": "/areas/kids",
  "/courses": "/areas/kids/courses",
  "/tasks": "/areas/kids/tasks",
  "/explore": "/areas/kids/explore",
  "/practice": "/areas/kids/tasks/practice",
  "/homework": "/areas/kids/tasks/homework",
  "/exams": "/areas/kids/tasks/exams",
  "/projects": "/areas/kids/explore/projects",
  "/activities": "/areas/kids/explore/activities",
  "/competitions": "/areas/kids/explore/competitions",
  "/live": "/areas/kids/explore/live",
  "/toolbox": "/areas/kids/toolbox",
};

function getSafeNextPath(next) {
  return typeof next === "string" && next.startsWith("/") && !next.startsWith("//")
    ? next
    : "/areas/kids";
}

router.beforeEach(async (to) => {
  if (LEGACY_AREA_PATHS[to.path]) {
    return { path: LEGACY_AREA_PATHS[to.path], query: to.query, hash: to.hash };
  }
  if (to.meta.requiresAuth || to.meta.guestOnly) {
    // 身份加载收口在 stores/session：和 App.vue 启动共用同一次 /me（P1-3）
    await ensureSession();
  }

  if (to.meta.shell === "learning" && to.params.areaKey) {
    try {
      await ensureLearningAreas();
    } catch {
      return { name: "learning" };
    }
    const area = areaByKey(String(to.params.areaKey));
    if (!area) return { name: "learning" };
    if (
      to.name === "area-module" &&
      to.params.moduleKey !== "more" &&
      !area.modules.some((item) => item.module_key === to.params.moduleKey)
    ) {
      return { name: "area-overview", params: { areaKey: area.key } };
    }
  }

  if (to.meta.guestOnly && session.user) {
    return getSafeNextPath(to.query.next);
  }

  if (to.meta.requiresAuth && !session.user) {
    return { name: "auth", query: { next: to.fullPath } };
  }

  return true;
});

export default router;
