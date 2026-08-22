// 专区模块配置对**所有**学习路由生效的护栏。
//
// 改造前守卫只校验兜底的 area-module 占位路由，courses / tasks / explore / toolbox /
// 错题本都是独立命名路由，直接敲地址就绕过了配置——后台把「课程」设成隐藏，侧栏没了，
// /areas/kids/courses 照样打开真实列表页。这组用例就是那个洞的报警器。
import { describe, expect, it } from "vitest";
import { learningModuleForRoute } from "../src/stores/studentNavigation";

const AREA = {
  key: "kids",
  modules: [
    { module_key: "overview", label: "学习首页", status: "available" },
    { module_key: "courses", label: "课程", status: "available" },
    { module_key: "tasks", label: "学习任务", status: "planning" },
    { module_key: "question-bank", label: "题库", status: "available" },
  ],
};

// router/index.js 守卫中模块校验分支的等价实现。真实守卫还要处理登录态和专区存在性，
// 这里只隔离出模块判定这一段，避免为了测一个 if 去启动整个 router。
function resolve(area, route) {
  const isMoreHub = route.name === "area-module" && route.params?.moduleKey === "more";
  const moduleKey = isMoreHub ? null : learningModuleForRoute(route);
  if (!moduleKey || moduleKey === "overview") return "pass";
  const module = area.modules.find((item) => item.module_key === moduleKey);
  if (!module || module.status === "hidden") return `overview:${moduleKey}`;
  if (module.status === "planning" && route.name !== "area-module") return `placeholder:${moduleKey}`;
  return "pass";
}

describe("专区模块配置约束所有学习路由", () => {
  it("已开放的模块正常放行", () => {
    expect(resolve(AREA, { name: "area-courses", params: { areaKey: "kids" } })).toBe("pass");
    expect(resolve(AREA, { name: "area-mistakes", params: { areaKey: "kids" } })).toBe("pass");
  });

  it("未配置的模块直接访问会被挡回专区首页并带上原因", () => {
    // explore 不在配置里：/areas/kids/explore 以前能直接进 ExploreHome
    expect(resolve(AREA, { name: "area-explore", params: { areaKey: "kids" } })).toBe(
      "overview:explore",
    );
    // 工具箱同理
    expect(resolve(AREA, { name: "area-toolbox", params: { areaKey: "kids" } })).toBe(
      "overview:toolbox",
    );
  });

  it("隐藏的模块和未配置一样挡住", () => {
    const hidden = {
      ...AREA,
      modules: AREA.modules.map((item) =>
        item.module_key === "courses" ? { ...item, status: "hidden" } : item,
      ),
    };
    expect(resolve(hidden, { name: "area-courses", params: { areaKey: "kids" } })).toBe(
      "overview:courses",
    );
  });

  it("规划中的模块落到占位页，而不是真实页面", () => {
    // tasks 是 planning：TasksHome 不该被打开
    expect(resolve(AREA, { name: "area-tasks", params: { areaKey: "kids" } })).toBe(
      "placeholder:tasks",
    );
    // 已经在占位页上就不再重定向，否则自环
    expect(
      resolve(AREA, { name: "area-module", params: { areaKey: "kids", moduleKey: "tasks" } }),
    ).toBe("pass");
  });

  it("专区首页和「更多」聚合页不参与校验", () => {
    expect(resolve(AREA, { name: "area-overview", params: { areaKey: "kids" } })).toBe("pass");
    expect(
      resolve(AREA, { name: "area-module", params: { areaKey: "kids", moduleKey: "more" } }),
    ).toBe("pass");
  });

  it("课程详情和课时子路由跟随 courses 模块的开关", () => {
    const hidden = {
      ...AREA,
      modules: AREA.modules.map((item) =>
        item.module_key === "courses" ? { ...item, status: "hidden" } : item,
      ),
    };
    expect(resolve(hidden, { name: "course-detail", params: { areaKey: "kids" } })).toBe(
      "overview:courses",
    );
  });
});
