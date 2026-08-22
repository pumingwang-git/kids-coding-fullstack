import { describe, expect, it } from "vitest";
import { modulePath } from "../src/stores/learningCatalog";
import {
  areaNavigationModules,
  learningModuleForRoute,
  questionBankNavigation,
} from "../src/stores/studentNavigation";

// 题库和工具箱现在由后端种子下发（原先是前端硬编码兜底），fixture 与
// /api/learning-areas 的真实返回保持一致。
const AREA = {
  key: "kids",
  modules: [
    { module_key: "overview", label: "学习首页", status: "available" },
    { module_key: "courses", label: "课程", status: "available" },
    { module_key: "tasks", label: "学习任务", status: "available" },
    { module_key: "explore", label: "探索创作", status: "available" },
    { module_key: "question-bank", label: "题库", status: "available" },
    { module_key: "toolbox", label: "工具箱", status: "available" },
  ],
};

describe("学生端导航目标", () => {
  it("题库入口统一进入真实错题页，不再进入通用占位页", () => {
    expect(modulePath("kids", "question-bank")).toBe("/areas/kids/tasks/mistakes");
    expect(
      areaNavigationModules(AREA).find((item) => item.module_key === "question-bank")?.to,
    ).toBe("/areas/kids/tasks/mistakes");
  });

  it("桌面侧栏补充项也出现在移动端更多菜单的数据源中", () => {
    const nav = areaNavigationModules(AREA);
    expect(nav.map((item) => item.module_key)).toEqual([
      "overview",
      "courses",
      "tasks",
      "explore",
      "question-bank",
      "toolbox",
    ]);
    expect(nav.slice(3).map((item) => item.module_key)).toEqual([
      "explore",
      "question-bank",
      "toolbox",
    ]);
  });

  it("后台隐藏的模块不出现在导航里，前端不会自己加回来", () => {
    const area = {
      ...AREA,
      modules: AREA.modules.map((item) =>
        item.module_key === "question-bank" ? { ...item, status: "hidden" } : item,
      ),
    };
    expect(areaNavigationModules(area).some((item) => item.module_key === "question-bank")).toBe(
      false,
    );
    // 工具箱同样只来自后端配置：没配就没有，不存在硬编码兜底
    const withoutToolbox = {
      ...AREA,
      modules: AREA.modules.filter((item) => item.module_key !== "toolbox"),
    };
    expect(areaNavigationModules(withoutToolbox).some((item) => item.module_key === "toolbox")).toBe(
      false,
    );
  });

  it("题库二级导航包含错题列表、复习任务和复习统计", () => {
    expect(questionBankNavigation("kids")).toEqual([
      {
        label: "我的错题",
        to: "/areas/kids/tasks/mistakes",
        routeName: "area-mistakes",
      },
      {
        label: "复习任务",
        to: "/areas/kids/tasks/mistakes/review",
        routeName: "area-mistake-review",
      },
      {
        label: "复习统计",
        to: "/areas/kids/tasks/mistakes/stats",
        routeName: "area-mistake-stats",
      },
    ]);
  });
});

describe("学生端路由的侧栏归属", () => {
  const cases = [
    ["area-overview", "overview"],
    ["area-courses", "courses"],
    ["course-detail", "courses"],
    ["lesson-player", "courses"],
    ["lesson-homework", "courses"],
    ["area-tasks", "tasks"],
    ["area-practice", "tasks"],
    ["area-homework", "tasks"],
    ["area-exams", "tasks"],
    ["exam", "tasks"],
    ["area-explore", "explore"],
    ["area-projects", "explore"],
    ["area-create", "explore"],
    ["area-activities", "explore"],
    ["area-competitions", "explore"],
    ["area-live", "explore"],
    ["area-toolbox", "toolbox"],
    ["area-mistakes", "question-bank"],
    ["area-mistake-detail", "question-bank"],
    ["area-mistake-review", "question-bank"],
    ["area-mistake-stats", "question-bank"],
  ];

  it.each(cases)("%s 激活 %s 模块", (name, moduleKey) => {
    expect(learningModuleForRoute({ name, params: {}, meta: {} })).toBe(moduleKey);
  });

  it("个人资料和设置页不错误高亮学习首页", () => {
    expect(learningModuleForRoute({ name: "profile", params: {}, meta: {} })).toBeNull();
    expect(learningModuleForRoute({ name: "settings", params: {}, meta: {} })).toBeNull();
  });

  it("通用专区模块按 moduleKey 激活对应侧栏项", () => {
    expect(
      learningModuleForRoute({
        name: "area-module",
        params: { moduleKey: "paths" },
        meta: {},
      }),
    ).toBe("paths");
  });
});
