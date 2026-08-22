// Python 作品题（shape="project"）的录题端纯逻辑：规则类型表、模块白名单、载荷构造。
// 与 DOM/网络无关，questions.html 用，vitest 直接测这里。
//
// 「作品题」是画线、画气球那一类：**没有标准输入输出**，所以整条 in/out 测试点链路
// 对它是空的。判分依据是这里的声明式规则（后端用 AST 静态读一遍学生代码）加上教师量规。
//
// 规则的 key 与后端 `app/python_rules.py` 的 SUPPORTED_TYPES 一一对应（11 种）。
// 后端 rules_json 是**扁平**结构（参数与 type 同级），不要用 params 嵌套——
// 表单态到扁平载荷的转换走 `admin-authoring-core.js` 的 flattenRules，与 Scratch 同一份。
//
// 后端还认三种「必须真的跑起来才知道结论」的类型（canvas_matches / final_position /
// stdout_contains），**故意不出现在这张表里**：判定引擎读不出它们，填了只会让全班提交
// 静静挂在人工点评队列里。等图像比对那条链落地再往这里加。

import { flattenRules, ruleHelpText, ruleToForm, rubricPayload } from "./admin-authoring-core.js";

export { ruleToForm };

// 允许 import 的模块白名单。空数组 = 不限制。
// 与 Scratch 的 EXTENSION_OPTIONS 同一角色：作品题要能说清「这节课只准用 turtle」。
// 后端只收顶层模块名（schemas.ProgrammingPayload.modules_are_identifiers 卡着）。
export const PY_MODULE_OPTIONS = [
  { key: "turtle", label: "turtle（海龟绘图）" },
  { key: "random", label: "random（随机数）" },
  { key: "math", label: "math（数学函数）" },
  { key: "time", label: "time（延时）" },
  { key: "string", label: "string（字符串常量）" },
];

// 声明式规则类型。label = 中文名称；desc = 给老师看的通俗说明（悬停显示）；
// example = 「添加规则」时自动填入的示例参数。Python 函数名、模块名保留原文不翻译。
export const PY_RULE_TYPES = [
  {
    key: "require_call", label: "必须调用指定函数",
    desc: "代码里必须调用某个函数，可要求至少调用几次。常用于保证学生用了本课教的重点函数。",
    example: { name: "forward", min_count: 1 },
    fields: [
      { key: "name", label: "函数名", hint: "只写函数名，不带模块前缀：写 forward，不写 turtle.forward", placeholder: "如 forward" },
      { key: "min_count", label: "至少调用几次", type: "number", hint: "填数字；不填默认为 1", placeholder: "默认 1" },
    ],
  },
  {
    key: "forbid_call", label: "禁止调用指定函数",
    desc: "不允许出现某个函数调用。常用于防止学生用 goto 一步到位跳过练习目标。",
    example: { name: "goto" },
    fields: [
      { key: "name", label: "函数名", hint: "要禁用的函数名，不带模块前缀", placeholder: "如 goto" },
    ],
  },
  {
    key: "require_import", label: "必须导入指定模块",
    desc: "代码里必须 import 某个模块。画图题一般要求 import turtle。",
    example: { module: "turtle" },
    fields: [
      { key: "module", label: "模块名", hint: "顶层模块名，如 turtle、random", placeholder: "如 turtle" },
    ],
  },
  {
    key: "forbid_import", label: "禁止导入指定模块",
    desc: "不允许 import 某个模块。用于把学生限制在本课教过的工具范围内。",
    example: { module: "os" },
    fields: [
      { key: "module", label: "模块名", hint: "要禁用的顶层模块名", placeholder: "如 os" },
    ],
  },
  {
    key: "require_loop", label: "必须使用循环",
    desc: "代码里必须出现循环。这是「画正多边形」这类题最核心的教学目标。",
    example: { kind: "for", min_count: 1 },
    fields: [
      { key: "kind", label: "循环种类", hint: "填 for、while，或 any（两种都算）；不填按 any", placeholder: "for / while / any" },
      { key: "min_count", label: "至少几个循环", type: "number", hint: "填数字；不填默认为 1", placeholder: "默认 1" },
    ],
  },
  {
    key: "require_call_in_loop", label: "指定调用必须写在循环里",
    desc: "某个函数调用必须出现在循环体内。**画正多边形的关键规则**：光要求「用了循环」和「调了 forward」，学生把六条边手写六遍再加个空循环也能过。",
    example: { name: "forward" },
    fields: [
      { key: "name", label: "函数名", hint: "必须写在循环体内的函数名", placeholder: "如 forward" },
    ],
  },
  {
    key: "require_function_def", label: "必须定义函数",
    desc: "学生必须自己定义一个函数，可要求形参个数。用于「把画一个气球封装成函数」这类题。",
    example: { name: "draw_balloon", arity: 1 },
    fields: [
      { key: "name", label: "函数名", hint: "要求学生定义的函数名", placeholder: "如 draw_balloon" },
      { key: "arity", label: "形参个数", type: "number", hint: "填数字；不填则不校验参数个数", placeholder: "留空 = 不校验" },
    ],
  },
  {
    key: "require_arg_value", label: "调用参数必须等于指定值",
    desc: "检查某个调用上填的参数是不是要求的值，比如「每条边 100 步」里的 forward(100)。",
    example: { name: "forward", index: 0, equals: "100" },
    fields: [
      { key: "name", label: "函数名", hint: "要检查的函数名", placeholder: "如 forward" },
      { key: "index", label: "第几个位置参数", type: "number", hint: "从 0 开始数；用关键字参数时改填下面的「关键字名」", placeholder: "如 0" },
      { key: "keyword", label: "关键字名", hint: "形如 circle(radius=50) 时填 radius；与位置参数二选一", placeholder: "留空 = 用位置参数" },
      { key: "equals", label: "要求的值", hint: "参数必须等于的值；数字按数值比较（100 和 100.0 算同一个）", placeholder: "如 100" },
    ],
  },
  {
    key: "require_variable", label: "必须定义变量",
    desc: "学生必须定义某个名字的变量。用于要求「把边长存成变量再用」这类题。",
    example: { name: "side" },
    fields: [
      { key: "name", label: "变量名", hint: "要求学生定义的变量名", placeholder: "如 side" },
    ],
  },
  {
    key: "require_branch", label: "必须使用 if 分支",
    desc: "代码里必须出现 if 判断，可要求至少几个。",
    example: { min_count: 1 },
    fields: [
      { key: "min_count", label: "至少几个分支", type: "number", hint: "填数字；不填默认为 1", placeholder: "默认 1" },
    ],
  },
  {
    key: "forbid_repeated_call", label: "同一调用不得超过 N 次",
    desc: "把复制粘贴堵死：要求 forward 最多出现 2 次，学生就只能用循环画完六条边，而不是抄六遍。与「必须使用循环」配合最有效。",
    example: { name: "forward", max_count: 2 },
    fields: [
      { key: "name", label: "函数名", hint: "要限制次数的函数名", placeholder: "如 forward" },
      { key: "max_count", label: "最多出现几次", type: "number", hint: "填数字，超过即判不通过", placeholder: "如 2" },
    ],
  },
];

export function pyRuleTypeLabel(key) {
  return PY_RULE_TYPES.find((t) => t.key === key)?.label || key || "未知规则";
}

export function pyRuleTypeHelp(key) {
  return ruleHelpText(key, PY_RULE_TYPES);
}

// 作品题的推荐量规。三项与 Scratch 的 DEFAULT_RUBRIC 同构（老师配得动、批得动），
// 但准则说明换成画图作品的口径——「图形准确」而不是「绿旗后完成规定动作」。
export const DEFAULT_PROJECT_RUBRIC = {
  criteria: [
    { id: "c_result", label: "图形准确", desc: "画出来的图形与题目要求一致", levels: [
      { value: 3, label: "完全达成", points: 40, desc: "形状、大小、位置都对" },
      { value: 2, label: "基本达成", points: 25, desc: "形状对，尺寸或位置有偏差" },
      { value: 1, label: "部分达成", points: 10, desc: "能画出线条但不成形" },
      { value: 0, label: "未达成", points: 0, desc: "没有画出图形" },
    ] },
    { id: "c_structure", label: "代码结构", desc: "该用循环的地方用了循环，没有复制粘贴", levels: [
      { value: 2, label: "清晰", points: 30, desc: "" },
      { value: 1, label: "一般", points: 15, desc: "" },
      { value: 0, label: "混乱", points: 0, desc: "" },
    ] },
    { id: "c_creative", label: "创意表达", desc: "在完成要求之外有自己的想法（配色、装饰、变化）", levels: [
      { value: 2, label: "有亮点", points: 30, desc: "" },
      { value: 1, label: "按部就班", points: 15, desc: "" },
      { value: 0, label: "未体现", points: 0, desc: "" },
    ] },
  ],
};

/** 表单态 → 后端 ProgrammingPayload 的作品题四件套。
 *
 * 返回 `{ errors, payload }`：errors 非空时调用方不应提交。
 * 后端 `schemas.ProgrammingPayload.shape_fields_are_consistent` 会再校验一次，
 * 这里只是让老师在点保存之前就看到问题，不是唯一防线。
 */
export function projectAssetsPayload(project) {
  const { rules, errors } = flattenRules(project?.rules, PY_RULE_TYPES);
  const allowed = (project?.allowedModules || [])
    .map((key) => String(key).trim())
    .filter((key) => PY_MODULE_OPTIONS.some((o) => o.key === key));
  return {
    errors,
    payload: {
      starter_code: String(project?.starterCode || ""),
      allowed_modules: allowed,
      rules,
      rubric: rubricPayload(project?.rubric),
    },
  };
}

/** 提交审核前的自查清单（镜像后端口径；后端仍会再校验一次）。
 *
 * 作品题没有测试点可以兜底：既没有规则也没有量规，就等于交上来只能靠老师凭空打分。
 * 所以这两样至少要有一样——这条是「别拦过头」的分寸：不强制两样都配。
 */
export function projectSubmitChecks(project) {
  const missing = [];
  if (!String(project?.starterCode || "").trim()) missing.push("初始代码");
  const hasRules = (project?.rules || []).some((r) => r && r.type);
  const hasRubric = Boolean(project?.rubric?.criteria?.length);
  if (!hasRules && !hasRubric) missing.push("至少一条判定规则，或一套教师量规");
  return missing;
}
