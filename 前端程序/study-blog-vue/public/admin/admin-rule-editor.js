// 录题端两个声明式编辑器的 DOM 实现：判定规则列表、教师量规表。
// Scratch 挑战与 Python 作品题共用同一份。
//
// **为什么从 questions.html 搬出来**：它俩原本内联在那个四千行的页面里，因而没有
// 任何测试能碰到——而两种题型现在都靠它们渲染，改坏一处会同时打断两条录题链路。
// 搬成模块之后 vitest 可以在 jsdom 里真的建一遍 DOM、点一遍按钮。
//
// 纯 DOM，不发请求：题型专属的部分（Scratch 的「从其它挑战导入量规」、Python 的
// 「使用推荐量规」）留在各自的渲染器里，通过返回的 render() 触发重绘。

import { escapeHtml } from "./admin-ui.js";
import { rubricPayload } from "./admin-authoring-core.js";

// 量规编辑器：准则 × 档位 × 分值。Scratch 挑战与 Python 作品题共用同一份。
//
// 抽出来的理由与 admin-authoring-core.js 的 rubricPayload 一样：两处各写一份，
// 「加档位时新 value 取多少」「满分怎么显示」任何一处改动都要记得改两遍。
// 题型专属的部分（推荐模板、清空、从别处导入）留在各自的渲染器里，
// 通过返回的 render() 触发重绘。
//
// get/set 而不是直接传对象：量规可以整个被替换成 null（= 不用量规），
// 传对象的话调用方那边的引用就断了。
export function mountRubricEditor(area, { get, set }) {
  const render = () => {
    const rubric = get();
    if (!rubric || !Array.isArray(rubric.criteria) || !rubric.criteria.length) {
      area.innerHTML = '<p class="muted">未配置量规：批改台将只做「通过 / 不通过」。</p>';
      return;
    }
    const total = rubricPayload(rubric).max_score;
    area.innerHTML = `<div class="muted" style="margin-bottom:8px">满分 = 各准则最高档分值之和：<strong>${total} 分</strong></div>${
      rubric.criteria.map((c, ci) => `<div class="scratch-rubric-criterion" style="border:1px solid var(--line);border-radius:8px;padding:10px;margin-bottom:10px">
        <div style="display:flex;gap:8px;margin-bottom:6px">
          <input data-rubric-cid="${ci}" value="${escapeHtml(c.id)}" placeholder="准则 id（英文/数字/下划线）" style="width:150px" />
          <input data-rubric-clabel="${ci}" value="${escapeHtml(c.label)}" placeholder="准则名，如：程序逻辑" style="flex:1" />
          <button class="btn-text link danger" type="button" data-rubric-cdel="${ci}">删除</button>
        </div>
        <input data-rubric-cdesc="${ci}" value="${escapeHtml(c.desc || "")}" placeholder="准则说明（可选）" style="width:100%;box-sizing:border-box;margin-bottom:6px" />
        ${(c.levels || []).map((lvl, li) => `<div style="display:flex;gap:6px;margin-bottom:4px">
          <input data-rubric-llabel="${ci}:${li}" value="${escapeHtml(lvl.label)}" placeholder="档位名，如：完全达成" style="flex:1" />
          <input data-rubric-lpoints="${ci}:${li}" type="number" min="0" value="${lvl.points}" placeholder="分值" style="width:90px" />
          <button class="btn-text link danger" type="button" data-rubric-ldel="${ci}:${li}">删档</button>
        </div>`).join("")}
        <button class="btn-text link" type="button" data-rubric-ladd="${ci}">＋ 加一个档位</button>
      </div>`).join("")
    }<button class="btn" data-rubric-cadd type="button">＋ 加一项准则</button>`;
  };
  area.addEventListener("click", (event) => {
    const rubric = get();
    const cadd = event.target.closest("[data-rubric-cadd]");
    if (cadd) {
      const next = rubric || { criteria: [] };
      next.criteria.push({ id: `c_${next.criteria.length + 1}`, label: "", desc: "", levels: [
        { value: 1, label: "达成", points: 1 }, { value: 0, label: "未达成", points: 0 },
      ] });
      set(next); render(); return;
    }
    const del = event.target.closest("[data-rubric-cdel]");
    if (del) { rubric?.criteria.splice(Number(del.dataset.rubricCdel), 1); render(); return; }
    const ladd = event.target.closest("[data-rubric-ladd]");
    if (ladd) {
      const c = rubric?.criteria[Number(ladd.dataset.rubricLadd)];
      if (c) {
        // 新档位的 value 取现有最大值 +1：value 是批改时查表的键，组内必须唯一
        // （后端 app/rubric.py 会拒重复），按数组下标取会在删档后撞车。
        const next = Math.max(-1, ...(c.levels || []).map((l) => l.value)) + 1;
        c.levels.push({ value: next, label: "", points: 0 });
        render();
      }
      return;
    }
    const ldel = event.target.closest("[data-rubric-ldel]");
    if (ldel) {
      const [ci, li] = ldel.dataset.rubricLdel.split(":").map(Number);
      rubric?.criteria[ci]?.levels.splice(li, 1);
      render();
    }
  });
  area.addEventListener("input", (event) => {
    const rubric = get();
    const input = event.target;
    if (!rubric) return;
    if (input.dataset.rubricCid != null) { rubric.criteria[Number(input.dataset.rubricCid)].id = input.value; return; }
    if (input.dataset.rubricClabel != null) { rubric.criteria[Number(input.dataset.rubricClabel)].label = input.value; return; }
    if (input.dataset.rubricCdesc != null) { rubric.criteria[Number(input.dataset.rubricCdesc)].desc = input.value; return; }
    if (input.dataset.rubricLlabel != null) {
      const [ci, li] = input.dataset.rubricLlabel.split(":").map(Number);
      rubric.criteria[ci].levels[li].label = input.value; return;
    }
    if (input.dataset.rubricLpoints != null) {
      const [ci, li] = input.dataset.rubricLpoints.split(":").map(Number);
      rubric.criteria[ci].levels[li].points = Number(input.value) || 0;
    }
  });
  return { render };
}

// 声明式规则编辑器：Scratch 挑战与 Python 作品题共用。
//
// 两边的规则表达完全同构（`{type, params}` 表单态 ↔ 扁平载荷），差别只在
// 类型表的内容。把类型表当参数传进来，列表渲染、示例参数填充、参数回显的
// 文本形态、删除与改值这几件就只有一份实现。
//
// 节点显式传入而不是靠约定的 id/选择器：两个渲染器的 DOM 布局不同，
// 强行统一 id 只会让「这个 id 是谁的」变成新的谜题。
export function mountRuleEditor({ list, typeSelect, addButton, help }, { get, ruleTypes, labelOf, helpOf, onChange = () => {} }) {
  // 数组/对象参数在输入框里按文本形态回显，与 flattenRules 的 list/json 解析互逆。
  const displayValue = (value) => {
    if (Array.isArray(value)) return value.join(", ");
    if (value && typeof value === "object") return JSON.stringify(value);
    return String(value ?? "");
  };
  const render = () => {
    const rules = get();
    list.innerHTML = rules.length ? rules.map((rule, index) => {
      const type = ruleTypes.find((item) => item.key === rule.type);
      const fields = (type?.fields || []).map((field) => `<label class="scratch-rule-field" title="${escapeHtml(field.hint || "")}">${escapeHtml(field.label)}<input data-rule-index="${index}" data-rule-param="${field.key}" ${field.type === "number" ? "type=number" : ""} value="${escapeHtml(displayValue(rule.params?.[field.key]))}" placeholder="${escapeHtml(field.placeholder || "")}" /></label>`).join("");
      const helpDot = type ? ` <span class="rule-help-dot" title="${escapeHtml(helpOf(rule.type) || "")}">?</span>` : "";
      return `<li class="scratch-rule-row"><strong>${escapeHtml(labelOf(rule.type))}${helpDot}</strong>${fields}<button class="btn-text link danger" type="button" data-rule-delete="${index}">删除</button></li>`;
    }).join("") : '<li class="muted">尚未添加规则。</li>';
  };
  // 类型下拉下面常驻一行中文说明（选中即换），比只靠悬停更容易被发现。
  const renderHelp = () => { if (help) help.textContent = helpOf(typeSelect.value) || ""; };
  addButton.addEventListener("click", () => {
    // 添加即填入该类型的示例参数：老师照着改比从零填参数快得多，
    // 示例值本身也是"这个字段长什么样"的活文档。
    const selected = typeSelect.value;
    const example = ruleTypes.find((t) => t.key === selected)?.example || {};
    get().push({ type: selected, params: { ...example } });
    render(); onChange();
  });
  typeSelect.addEventListener("change", renderHelp);
  list.addEventListener("click", (event) => {
    const button = event.target.closest("[data-rule-delete]");
    if (!button) return;
    get().splice(Number(button.dataset.ruleDelete), 1);
    render(); onChange();
  });
  list.addEventListener("input", (event) => {
    const input = event.target.closest("[data-rule-index]");
    if (!input) return;
    get()[Number(input.dataset.ruleIndex)].params[input.dataset.ruleParam] = input.value;
    onChange();
  });
  renderHelp();
  return { render };
}
