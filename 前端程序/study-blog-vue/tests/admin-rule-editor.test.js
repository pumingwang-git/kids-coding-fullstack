/**
 * @vitest-environment jsdom
 *
 * 判定规则编辑器与量规编辑器的 DOM 行为。
 *
 * 这两件原本内联在 questions.html 里，没有任何测试碰得到；现在 Scratch 挑战与
 * Python 作品题**都靠它们渲染**，改坏一处会同时打断两条录题链路。所以这里不测
 * 「函数返回了什么」，而是真的建一遍 DOM、点一遍按钮，看状态对象有没有被改对。
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  mountRubricEditor,
  mountRuleEditor,
} from "../public/admin/admin-rule-editor.js";

const RULE_TYPES = [
  {
    key: "require_call", label: "必须调用指定函数", desc: "说明",
    example: { name: "forward", min_count: 1 },
    fields: [
      { key: "name", label: "函数名", hint: "填函数名", placeholder: "如 forward" },
      { key: "min_count", label: "至少几次", type: "number", hint: "填数字" },
    ],
  },
  {
    key: "require_loop", label: "必须使用循环", desc: "说明",
    example: { kind: "for" },
    fields: [{ key: "kind", label: "循环种类", hint: "for/while" }],
  },
];

function mountRules(initial = []) {
  document.body.innerHTML = `
    <ol id="list"></ol>
    <select id="type">
      <option value="require_call">必须调用指定函数</option>
      <option value="require_loop">必须使用循环</option>
    </select>
    <button id="add"></button>
    <p id="help"></p>`;
  const state = { rules: initial };
  let changes = 0;
  const editor = mountRuleEditor({
    list: document.getElementById("list"),
    typeSelect: document.getElementById("type"),
    addButton: document.getElementById("add"),
    help: document.getElementById("help"),
  }, {
    get: () => state.rules,
    ruleTypes: RULE_TYPES,
    labelOf: (key) => RULE_TYPES.find((t) => t.key === key)?.label || key,
    helpOf: (key) => (RULE_TYPES.some((t) => t.key === key) ? `帮助:${key}` : null),
    onChange: () => { changes += 1; },
  });
  editor.render();
  return { state, editor, changed: () => changes };
}

describe("判定规则编辑器", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("空规则时给出提示，而不是留一片空白", () => {
    mountRules();
    expect(document.getElementById("list").textContent).toContain("尚未添加规则");
  });

  it("添加规则会填入该类型的示例参数", () => {
    // 示例值本身就是「这个字段长什么样」的活文档，老师照着改比从零填快得多。
    const { state } = mountRules();
    document.getElementById("add").click();
    expect(state.rules).toEqual([{ type: "require_call", params: { name: "forward", min_count: 1 } }]);
    expect(document.querySelectorAll("[data-rule-index]").length).toBe(2);
  });

  it("添加的是下拉当前选中的类型，不是永远第一种", () => {
    const { state } = mountRules();
    document.getElementById("type").value = "require_loop";
    document.getElementById("add").click();
    expect(state.rules[0].type).toBe("require_loop");
  });

  it("改输入框写回对应规则的对应参数", () => {
    const { state } = mountRules([{ type: "require_call", params: { name: "forward" } }]);
    const input = document.querySelector('[data-rule-index="0"][data-rule-param="name"]');
    input.value = "circle";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(state.rules[0].params.name).toBe("circle");
  });

  it("删除删的是被点那一条，不是最后一条", () => {
    // 索引取自 data-rule-delete 而不是数组末尾——写错的话删中间一条会删掉别的。
    const { state } = mountRules([
      { type: "require_call", params: { name: "a" } },
      { type: "require_call", params: { name: "b" } },
      { type: "require_call", params: { name: "c" } },
    ]);
    document.querySelector('[data-rule-delete="1"]').click();
    expect(state.rules.map((r) => r.params.name)).toEqual(["a", "c"]);
  });

  it("数组/对象参数按文本形态回显，与扁平化互逆", () => {
    mountRules([{ type: "require_call", params: { name: ["a", "b"] } }]);
    expect(document.querySelector('[data-rule-param="name"]').value).toBe("a, b");
  });

  it("下拉切换时帮助文案跟着换", () => {
    mountRules();
    expect(document.getElementById("help").textContent).toBe("帮助:require_call");
    const select = document.getElementById("type");
    select.value = "require_loop";
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
    expect(document.getElementById("help").textContent).toBe("帮助:require_loop");
  });

  it("增删改都会触发 onChange（就绪度要跟着刷新）", () => {
    const { changed } = mountRules([{ type: "require_call", params: {} }]);
    expect(changed()).toBe(0);
    document.getElementById("add").click();
    const input = document.querySelector('[data-rule-index="0"][data-rule-param="name"]');
    input.value = "x";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    document.querySelector('[data-rule-delete="0"]').click();
    expect(changed()).toBe(3);
  });
});

function mountRubric(initial) {
  document.body.innerHTML = '<div id="area"></div>';
  const state = { rubric: initial };
  const editor = mountRubricEditor(document.getElementById("area"), {
    get: () => state.rubric,
    set: (value) => { state.rubric = value; },
  });
  editor.render();
  return { state, editor };
}

const RUBRIC = {
  criteria: [
    { id: "c_logic", label: "程序逻辑", desc: "", levels: [
      { value: 1, label: "达成", points: 40 },
      { value: 0, label: "未达成", points: 0 },
    ] },
  ],
};

describe("量规编辑器", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("没配量规时说明批改台只做通过/不通过", () => {
    mountRubric(null);
    expect(document.getElementById("area").textContent).toContain("通过 / 不通过");
  });

  it("满分显示为各准则最高档之和，不要老师手填", () => {
    mountRubric({ criteria: [
      { id: "a", label: "甲", levels: [{ value: 1, label: "好", points: 40 }, { value: 0, label: "差", points: 0 }] },
      { id: "b", label: "乙", levels: [{ value: 1, label: "好", points: 25 }, { value: 0, label: "差", points: 5 }] },
    ] });
    expect(document.getElementById("area").textContent).toContain("65 分");
  });

  it("空态不出「加一项准则」按钮：进量规的唯一入口是推荐模板", () => {
    // 这是既有行为（Scratch 一直如此），在此如实钉住而不是顺手改掉：
    // `{criteria: []}` 与 null 一样都渲染成空态，所以从零开始配量规的老师必须先点
    // 「使用推荐量规」，再删掉不要的准则。要改成空态也能加，得连 Scratch 一起改。
    mountRubric({ criteria: [] });
    expect(document.querySelector("[data-rubric-cadd]")).toBeNull();
    expect(document.getElementById("area").textContent).toContain("通过 / 不通过");
  });

  it("有准则之后可以继续加，新准则带两个默认档位", () => {
    const { state } = mountRubric(JSON.parse(JSON.stringify(RUBRIC)));
    document.querySelector("[data-rubric-cadd]").click();
    expect(state.rubric.criteria.length).toBe(2);
    expect(state.rubric.criteria[1].levels.map((l) => l.value)).toEqual([1, 0]);
  });

  it("加档位时新 value 取现有最大值 +1，删档后也不撞车", () => {
    // value 是批改时查表的键，组内必须唯一（后端 app/rubric.py 会拒重复）。
    // 按数组长度取会在「删中间一档再加一档」时产生重复。
    const { state } = mountRubric(JSON.parse(JSON.stringify(RUBRIC)));
    document.querySelector('[data-rubric-ladd="0"]').click();
    expect(state.rubric.criteria[0].levels.map((l) => l.value)).toEqual([1, 0, 2]);
    document.querySelector('[data-rubric-ldel="0:1"]').click();
    document.querySelector('[data-rubric-ladd="0"]').click();
    const values = state.rubric.criteria[0].levels.map((l) => l.value);
    expect(new Set(values).size).toBe(values.length);
  });

  it("改准则名与档位分值写回状态", () => {
    const { state } = mountRubric(JSON.parse(JSON.stringify(RUBRIC)));
    const label = document.querySelector('[data-rubric-clabel="0"]');
    label.value = "图形准确";
    label.dispatchEvent(new window.Event("input", { bubbles: true }));
    const points = document.querySelector('[data-rubric-lpoints="0:0"]');
    points.value = "50";
    points.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(state.rubric.criteria[0].label).toBe("图形准确");
    expect(state.rubric.criteria[0].levels[0].points).toBe(50);
  });

  it("删除准则删的是被点那一条", () => {
    const { state } = mountRubric({ criteria: [
      { id: "a", label: "甲", levels: [{ value: 1, label: "好", points: 1 }, { value: 0, label: "差", points: 0 }] },
      { id: "b", label: "乙", levels: [{ value: 1, label: "好", points: 1 }, { value: 0, label: "差", points: 0 }] },
    ] });
    document.querySelector('[data-rubric-cdel="1"]').click();
    expect(state.rubric.criteria.map((c) => c.id)).toEqual(["a"]);
  });

  it("量规被清成 null 之后改输入不炸", () => {
    const { state, editor } = mountRubric(JSON.parse(JSON.stringify(RUBRIC)));
    const label = document.querySelector('[data-rubric-clabel="0"]');
    state.rubric = null;
    expect(() => label.dispatchEvent(new window.Event("input", { bubbles: true }))).not.toThrow();
    expect(() => editor.render()).not.toThrow();
  });
});
