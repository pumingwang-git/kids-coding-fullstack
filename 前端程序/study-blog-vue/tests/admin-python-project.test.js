// Python 作品题录题端的纯逻辑：规则表与后端的契约对齐、表单态 → 载荷、自查清单。
//
// 最要紧的是第一组「契约」：规则类型的 key 分散在前端 PY_RULE_TYPES 与后端
// app/python_rules.py 两处，靠 key 对齐。拼错一个字母的后果不是报错，而是老师配的
// 规则被后端写入校验拒掉（或更糟：判定期静静挂起全班等人工）。这条测试就是那道闸。
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import {
  TAXONOMY_DEFAULTS,
  taxonomyIsPristine,
  taxonomySummaryText,
} from "../public/admin/admin-authoring-core.js";
import {
  DEFAULT_PROJECT_RUBRIC,
  PY_MODULE_OPTIONS,
  PY_RULE_TYPES,
  projectAssetsPayload,
  projectSubmitChecks,
  pyRuleTypeHelp,
  pyRuleTypeLabel,
  ruleToForm,
} from "../public/admin/admin-python-core.js";

const here = dirname(fileURLToPath(import.meta.url));
const RULES_PY = readFileSync(
  resolve(here, "../../../后端程序/auth_service/app/python_rules.py"),
  "utf8",
);

/** 从 python_rules.py 里抠出一个 frozenset({...}) 里的字符串字面量。 */
function pySet(name) {
  const block = RULES_PY.split(`${name} = frozenset({`)[1];
  expect(block, `python_rules.py 里找不到 ${name}`).toBeTruthy();
  return new Set([...block.split("})")[0].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]));
}

describe("规则表与后端的契约", () => {
  it("PY_RULE_TYPES 的 key 与后端 SUPPORTED_TYPES 完全一致", () => {
    const frontend = PY_RULE_TYPES.map((t) => t.key).sort();
    expect(frontend).toEqual([...pySet("SUPPORTED_TYPES")].sort());
  });

  it("不把「跑起来才知道」的类型放进选择器", () => {
    // 判定引擎读不出 canvas_matches 这类规则，出现在下拉里只会让老师配上一条
    // 必然挂人工的规则，而界面上没有任何提示说明为什么。
    const offered = new Set(PY_RULE_TYPES.map((t) => t.key));
    for (const key of pySet("UNSUPPORTED")) {
      expect(offered.has(key), `${key} 不该出现在录题下拉里`).toBe(false);
    }
  });

  it("每种规则都有中文名、说明、示例和字段定义", () => {
    for (const type of PY_RULE_TYPES) {
      expect(type.label, `${type.key} 缺中文名`).toBeTruthy();
      expect(type.desc, `${type.key} 缺说明`).toBeTruthy();
      expect(Object.keys(type.example).length, `${type.key} 缺示例参数`).toBeGreaterThan(0);
      expect(type.fields.length, `${type.key} 缺字段定义`).toBeGreaterThan(0);
      for (const field of type.fields) {
        expect(field.label, `${type.key}.${field.key} 缺字段名`).toBeTruthy();
        expect(field.hint, `${type.key}.${field.key} 缺填写说明`).toBeTruthy();
      }
      // 示例参数的键必须都在字段表里，否则「添加规则」填进去的值在界面上看不见，
      // 却会跟着载荷发到后端。
      for (const key of Object.keys(type.example)) {
        expect(type.fields.some((f) => f.key === key), `${type.key} 的示例键 ${key} 没有对应字段`).toBe(true);
      }
    }
  });
});

describe("表单态 → 载荷", () => {
  const form = (rules, extra = {}) => ({
    starterCode: "import turtle\n",
    allowedModules: ["turtle"],
    rules,
    rubric: null,
    ...extra,
  });

  it("规则扁平化：参数与 type 同级，不包 params", () => {
    const { payload, errors } = projectAssetsPayload(
      form([{ type: "require_call_in_loop", params: { name: "forward" } }]),
    );
    expect(errors).toEqual([]);
    expect(payload.rules).toEqual([{ type: "require_call_in_loop", name: "forward" }]);
  });

  it("number 字段留空不落进载荷（后端可选参数，落 null 要多一层兜底）", () => {
    const { payload } = projectAssetsPayload(
      form([{ type: "require_call", params: { name: "forward", min_count: "" } }]),
    );
    expect(payload.rules[0]).toEqual({ type: "require_call", name: "forward" });
  });

  it("number 字段填了就转成数字，不留字符串", () => {
    const { payload } = projectAssetsPayload(
      form([{ type: "forbid_repeated_call", params: { name: "forward", max_count: "2" } }]),
    );
    expect(payload.rules[0].max_count).toBe(2);
  });

  it("字段表里没有的参数不会混进载荷", () => {
    // 老师改过形态、规则类型换过一轮之后，params 上会残留上一种类型的键。
    // 后端 ProgrammingPayload 不认识它们，原样送上去只会换来一次 422。
    const { payload } = projectAssetsPayload(
      form([{ type: "require_import", params: { module: "turtle", opcode: "motion_movesteps" } }]),
    );
    expect(payload.rules[0]).toEqual({ type: "require_import", module: "turtle" });
  });

  it("白名单外的模块名被丢掉", () => {
    const { payload } = projectAssetsPayload(
      form([], { allowedModules: ["turtle", "os", "socket"] }),
    );
    expect(payload.allowed_modules).toEqual(["turtle"]);
  });

  it("不用量规时载荷是 {}，不是 null", () => {
    // 后端 ProgrammingPayload.rubric 是 dict，null 会 422。
    const { payload } = projectAssetsPayload(form([]));
    expect(payload.rubric).toEqual({});
  });

  it("量规满分由前端算出，不交给老师手填", () => {
    const { payload } = projectAssetsPayload(
      form([], { rubric: JSON.parse(JSON.stringify(DEFAULT_PROJECT_RUBRIC)) }),
    );
    // 40 + 30 + 30，与后端 app/rubric.py 的算法一致；不一致后端直接拒、不自动纠正。
    expect(payload.rubric.max_score).toBe(100);
  });

  it("回显 → 表单态 → 载荷 往返不丢参数", () => {
    const fromBackend = [
      { type: "require_call_in_loop", name: "forward", label: "用循环画出每一条边" },
      { type: "forbid_repeated_call", name: "forward", max_count: 2 },
    ];
    const { payload } = projectAssetsPayload(form(fromBackend.map(ruleToForm)));
    // label 是学生可见文案，不在字段表里编辑，因此往返后不保留——这是 ruleToForm
    // 的既定口径（与 Scratch 一致），不是丢数据。
    expect(payload.rules).toEqual([
      { type: "require_call_in_loop", name: "forward" },
      { type: "forbid_repeated_call", name: "forward", max_count: 2 },
    ]);
  });
});

describe("提交前自查", () => {
  it("没有初始代码时提示补充", () => {
    expect(projectSubmitChecks({ starterCode: "  ", rules: [], rubric: null })).toContain("初始代码");
  });

  it("既无规则也无量规时提示补充", () => {
    expect(projectSubmitChecks({ starterCode: "x", rules: [], rubric: null }))
      .toContain("至少一条判定规则，或一套教师量规");
  });

  it("只配规则就算齐（别拦过头）", () => {
    // 分寸在这里：作品题不强制两样都配。只有规则、或只有量规，都是成立的教法。
    expect(projectSubmitChecks({
      starterCode: "import turtle",
      rules: [{ type: "require_loop", params: {} }],
      rubric: null,
    })).toEqual([]);
  });

  it("只配量规也算齐", () => {
    expect(projectSubmitChecks({
      starterCode: "import turtle",
      rules: [],
      rubric: DEFAULT_PROJECT_RUBRIC,
    })).toEqual([]);
  });
});

describe("文案", () => {
  it("规则名回退到 key，不显示 undefined", () => {
    expect(pyRuleTypeLabel("require_call")).toBe("必须调用指定函数");
    expect(pyRuleTypeLabel("nope")).toBe("nope");
  });

  it("帮助文案带上每个参数怎么填", () => {
    const help = pyRuleTypeHelp("require_arg_value");
    expect(help).toContain("参数怎么填");
    expect(help).toContain("关键字名");
    expect(pyRuleTypeHelp("nope")).toBeNull();
  });

  it("模块白名单每项都有中文说明", () => {
    for (const option of PY_MODULE_OPTIONS) {
      expect(option.label).toMatch(/[（(]/);
    }
  });
});

describe("左栏「分类与标签」折叠区", () => {
  const pristine = () => ({ ...TAXONOMY_DEFAULTS, knowledge: [], stage: [], business: [] });

  it("全是默认值时可以安心收起", () => {
    expect(taxonomyIsPristine(pristine())).toBe(true);
  });

  it.each([
    ["difficulty", { difficulty: "普及-" }],
    ["source", { source: "洛谷" }],
    ["structure", { structure: "综合应用" }],
    ["stage", { stage: ["Python基础"] }],
    ["business", { business: ["内部练习"] }],
  ])("%s 一旦不是默认值就要自动展开", (_key, patch) => {
    // 打开一道已经打过标签的老题时，标签必须一眼看见，否则会被误以为
    // 「这题没打标签」而重复打一遍。
    expect(taxonomyIsPristine({ ...pristine(), ...patch })).toBe(false);
  });

  it("摘要按「难度 · 来源 · 结构 · 其余标签」拼出来", () => {
    expect(taxonomySummaryText({
      ...pristine(), difficulty: "普及-", stage: ["Python基础"], business: ["内部练习"],
    })).toBe("普及- · 第三方 · 单项知识点 · Python基础 · 内部练习");
  });

  it("摘要不会出现空段（收起时标题不能是「入门 ·  · 」这种）", () => {
    expect(taxonomySummaryText({ difficulty: "入门", source: "", structure: "单项知识点" }))
      .toBe("入门 · 单项知识点");
  });

  it("没有 common 时不炸（弹窗还没填好状态就渲染过一次）", () => {
    expect(taxonomyIsPristine(null)).toBe(true);
    expect(taxonomySummaryText(null)).toBe("");
  });
});
