import { modulePath } from "./learningCatalog";

// 题库和工具箱曾经在这里硬编码兜底，后端 MODULE_KEYS 又不认这两个 key，
// 于是后台想配都配不了。两者现已收进后端能力注册表与专区种子，导航数据源
// 收敛到 /api/learning-areas 一处——前端不再自己往里加东西。
// 被守卫拦下的模块通常不在下发数据里（隐藏或未配置），拿不到 label，
// 这份表只用于提示文案兜底，key 与后端 MODULE_REGISTRY 保持一致。
const MODULE_LABELS = {
  overview: "学习首页",
  courses: "课程",
  tasks: "学习任务",
  explore: "探索创作",
  "question-bank": "题库",
  toolbox: "工具箱",
  paths: "学习路线",
  projects: "实战项目",
};

export function moduleLabel(moduleKey) {
  return MODULE_LABELS[moduleKey] || "";
}

const MODULE_ICONS = {
  overview: "home",
  courses: "book",
  tasks: "check",
  "question-bank": "exam",
  toolbox: "settings",
};

const ROUTE_MODULES = {
  "area-overview": "overview",
  "area-courses": "courses",
  "course-detail": "courses",
  "lesson-player": "courses",
  "lesson-homework": "courses",
  "area-tasks": "tasks",
  "area-practice": "tasks",
  "area-homework": "tasks",
  "area-exams": "tasks",
  exam: "tasks",
  "area-explore": "explore",
  "area-projects": "explore",
  "area-create": "explore",
  "area-activities": "explore",
  "area-competitions": "explore",
  "area-live": "explore",
  "area-toolbox": "toolbox",
  "area-mistakes": "question-bank",
  "area-mistake-detail": "question-bank",
  "area-mistake-review": "question-bank",
  "area-mistake-stats": "question-bank",
};

export function areaNavigationModules(area) {
  if (!area) return [];

  // 公开接口已经滤掉 hidden，这里再滤一次是防御：接口哪天改成下发全量也不会漏出隐藏项。
  const modules = (area.modules || []).filter((item) => item.status !== "hidden");

  return modules.map((item) => ({
    ...item,
    to: modulePath(area.key, item.module_key),
    icon: MODULE_ICONS[item.module_key] || "spark",
  }));
}

export function learningModuleForRoute(route) {
  const name = String(route.name || "");
  if (ROUTE_MODULES[name]) return ROUTE_MODULES[name];
  if (name === "area-module") return String(route.params?.moduleKey || "") || null;
  return route.meta?.learningModule ? String(route.meta.learningModule) : null;
}

export function questionBankNavigation(areaKey) {
  const base = `/areas/${areaKey}/tasks/mistakes`;
  return [
    { label: "我的错题", to: base, routeName: "area-mistakes" },
    { label: "复习任务", to: `${base}/review`, routeName: "area-mistake-review" },
    { label: "复习统计", to: `${base}/stats`, routeName: "area-mistake-stats" },
  ];
}
