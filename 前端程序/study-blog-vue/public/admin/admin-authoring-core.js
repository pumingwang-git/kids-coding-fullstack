// 录题端题型无关的公共件：声明式规则的表单 ↔ 载荷互转、量规归一化。
//
// 这里的三个函数原本只长在 admin-scratch-core.js 里。Python 作品题要用同一套
// 「规则类型表 + 扁平载荷」的表达，把它们复制一份就等于承认 Scratch 的规则和
// Python 的规则是两种东西：之后 number 参数怎么转、空值要不要落进载荷、量规满分
// 怎么算，任何一处改动都要记得改两遍，而漏掉的那一遍不会报错。
//
// 与 DOM/网络无关，vitest 直接测这里。

/** 后端冻结的规则原文（扁平）→ 表单状态（{type, params}）。
 *
 * type/label 之外的键都是参数；label 是学生可见文案，不进参数表（表单里不编辑 label）。
 */
export function ruleToForm(rule) {
  const params = { ...(rule || {}) };
  delete params.type;
  delete params.label;
  return { type: rule?.type || "", params };
}

/** 表单状态（{type, params}）→ 后端 rules_json 的**扁平**结构（参数与 type 同级）。
 *
 * `ruleTypes` 是该题型的规则类型表（Scratch 用 RULE_TYPES，Python 用 PY_RULE_TYPES），
 * 每项形如 `{ key, label, fields: [{ key, label, type? }] }`。字段的 `type` 决定转换：
 *   number  空值不落进载荷（后端字段可选，落 null 反而要在判定端多写一层兜底）
 *   list    逗号/顿号/换行分隔的多值
 *   json    结构描述类参数；坏 JSON **在保存前就拦下**，存进库会让全班提交判不出来
 *   其它    去空白的字符串，空串不落
 *
 * 返回 `{ rules, errors }`：errors 非空时调用方不应提交。
 */
export function flattenRules(formRules, ruleTypes) {
  const errors = [];
  const rules = [];
  for (const rule of formRules || []) {
    if (!rule || !rule.type) continue;
    const type = (ruleTypes || []).find((t) => t.key === rule.type);
    const flat = { type: rule.type };
    for (const field of type?.fields || []) {
      const raw = rule.params?.[field.key];
      if (field.type === "number") {
        if (raw !== "" && raw != null) flat[field.key] = Number(raw);
      } else if (field.type === "list") {
        const items = String(raw ?? "").split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean);
        if (items.length) flat[field.key] = items;
      } else if (field.type === "json") {
        const text = String(raw ?? "").trim();
        if (text) {
          try {
            flat[field.key] = JSON.parse(text);
          } catch {
            errors.push(`规则「${type?.label || rule.type}」的「${field.label}」不是合法 JSON，请检查格式。`);
          }
        }
      } else if (raw != null && String(raw).trim() !== "") {
        flat[field.key] = String(raw).trim();
      }
    }
    rules.push(flat);
  }
  return { rules, errors };
}

/** 归一化为后端的 rubric 形状；空/无准则 → `{}`（= 不用量规）。
 *
 * `max_score` 由前端算出（各准则最高档之和），不交给老师手填——手填错到学生看到
 * 分数才发现的概率极高（文档 23 §附录 A）。后端 `app/rubric.py` 会再校验一次，
 * 两边算得不一样就直接拒，不自动纠正。
 */
export function rubricPayload(rubric) {
  if (!rubric || !Array.isArray(rubric.criteria) || !rubric.criteria.length) return {};
  const criteria = rubric.criteria.map((c) => ({
    id: c.id,
    label: String(c.label || "").trim(),
    desc: String(c.desc || ""),
    levels: (c.levels || []).map((lvl) => ({
      value: lvl.value,
      label: String(lvl.label || "").trim(),
      points: Number(lvl.points) || 0,
      desc: String(lvl.desc || ""),
    })),
  }));
  const max_score = criteria.reduce(
    (sum, c) => sum + Math.max(...c.levels.map((l) => l.points || 0), 0),
    0,
  );
  return { max_score, criteria };
}

/** 悬停/帮助区用的一句话说明。规则类型表的通用渲染件。 */
export function ruleHelpText(key, ruleTypes) {
  const type = (ruleTypes || []).find((t) => t.key === key);
  if (!type) return null;
  const hints = type.fields.map((f) => `· ${f.label}：${f.hint}`).join("\n");
  return `${type.desc}\n\n参数怎么填：\n${hints}\n\n示例：${JSON.stringify(type.example, null, 0)}`;
}

// ---- 录题端左栏「分类与标签」折叠区 ----
//
// 这几项都有默认值，多数题不用动，所以折叠区默认收起。但**打开一道已经打过标签的
// 老题时必须自动展开**，否则那些标签看不见，会被误以为「这题没打标签」而重复打一遍。
// 判据就是下面这个「是不是全都还是默认值」。

export const TAXONOMY_DEFAULTS = {
  difficulty: "入门",
  source: "第三方",
  structure: "单项知识点",
};

/** 分类与标签是否原封未动（= 可以安心收起）。 */
export function taxonomyIsPristine(common) {
  if (!common) return true;
  const sameAsDefault = Object.entries(TAXONOMY_DEFAULTS)
    .every(([key, value]) => common[key] === value);
  return sameAsDefault && !(common.stage || []).length && !(common.business || []).length;
}

/** 折叠标题上常驻的取值摘要。
 *
 * 收起不等于藏起来：看不见现在选的是什么，老师就会每次都点开确认，折叠等于白做。
 */
export function taxonomySummaryText(common) {
  if (!common) return "";
  return [
    common.difficulty,
    common.source,
    common.structure,
    ...(common.stage || []),
    ...(common.business || []),
  ].filter(Boolean).join(" · ");
}
