import { modulePath } from "./learningCatalog";

const FALLBACK_MODULES = [
  { module_key: "question-bank", label: "题库", status: "available" },
  { module_key: "toolbox", label: "工具箱", status: "available" },
];

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

  const allConfigured = area.modules || [];
  const configured = allConfigured.filter((item) => item.status !== "hidden");
  const modules = [...configured];
  for (const fallback of FALLBACK_MODULES) {
    if (!allConfigured.some((item) => item.module_key === fallback.module_key)) {
      modules.push({ ...fallback });
    }
  }

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
