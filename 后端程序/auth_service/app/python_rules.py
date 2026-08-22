"""Python 作品题的声明式判定规则表——**本期只有规则表与写入校验，没有判定引擎**。

## 这个模块为什么现在就要存在

作品题（画线、画气球那一类）没有标准输入输出，`test_cases` 那条链对它是空的。
判定要靠「代码里有没有按要求写」——用了循环没有、调没调 `forward`、是不是把六条边
硬写了六遍。这些都能从 AST 静态读出来，形状与 `scratch_rules` 一模一样：教研在管理端
填一组声明式规则，判定时逐条出结论。

本期落地的是**录题侧**：规则能填、能存、能回显，写入时就校验类型拼写。
判定引擎（对应 `scratch_rules._EVALUATORS`）尚未落地，因此在它落地之前，
作品题的提交**一律 `needs_review` 挂人工**——与 `scratch_rules` 的 fail-closed 同一条
纪律：判不了就不能算过。`KNOWN_TYPES` 里的每一种都是静态可判的，引擎落地时
直接往 `_EVALUATORS` 里填实现，规则表、录题界面、已存的题一个字都不用改。

## 为什么规则文案不在这里

与 `scratch_rules` 同例：类型的中文名、参数说明、示例值住在管理端的
`public/admin/admin-python-core.js`（`PY_RULE_TYPES`），后端只持有 `KNOWN_TYPES`
做写入校验。两边靠 key 对齐，加一种规则要同时改两处——这是 Scratch 那条链已经
立下的取舍，不在这里另起一套。

## 规则表达

`rules_json` 是一个 JSON 数组，每项**扁平**（参数与 type 同级，不用 params 嵌套）：

    {"type": "require_call_in_loop", "name": "forward",
     "label": "用循环画出每一条边"}

`label` 可选，是给学生看的任务清单文案。**规则参数不下发给学生**，只下发 label——
参数里带着期望值（要画几条边、半径多少），下发等于把答案印在题面上。
"""
from __future__ import annotations

import json

# 静态可判的规则类型：AST 读一遍就能出结论，不需要运行学生代码。
#
# | type | 参数 | 判定 |
# | --- | --- | --- |
# | require_call         | name, min_count?      | 至少调用了 N 次该函数 |
# | forbid_call          | name                  | 不允许调用该函数 |
# | require_import       | module                | 必须导入该模块 |
# | forbid_import        | module                | 不允许导入该模块 |
# | require_loop         | kind?(for/while/any), min_count? | 用了循环 |
# | require_call_in_loop | name                  | 该调用写在循环体内（**画正多边形的核心规则**） |
# | require_function_def | name, arity?          | 定义了该函数（可校验形参个数） |
# | require_arg_value    | name, index?/keyword?, equals | 该调用的某个实参等于字面值 |
# | require_variable     | name                  | 定义了该变量 |
# | require_branch       | min_count?            | 用了 if 分支 |
# | forbid_repeated_call | name, max_count       | 同一调用不得超过 N 次（逼学生用循环，而不是复制粘贴） |
SUPPORTED_TYPES = frozenset({
    "require_call",
    "forbid_call",
    "require_import",
    "forbid_import",
    "require_loop",
    "require_call_in_loop",
    "require_function_def",
    "require_arg_value",
    "require_variable",
    "require_branch",
    "forbid_repeated_call",
})

# 声明得出、但**必须真的把程序跑起来**才知道结论的规则。静态 AST 永远读不出它们，
# 所以即使判定引擎落地，这几种仍然走人工（或等图像比对那条链）。
# 与 `scratch_rules.UNSUPPORTED` 同一角色：命中即挂起，绝不自动通过。
UNSUPPORTED = frozenset({
    "canvas_matches",   # 画出来的图与基准图相符（需要图像比对）
    "final_position",   # 画笔最终坐标
    "stdout_contains",  # 运行输出包含指定文本
})

KNOWN_TYPES = SUPPORTED_TYPES | UNSUPPORTED


def parse_rules(rules_json: str) -> list[dict]:
    """把 `rules_json` 解析成规则列表。脏数据一律当空规则，不抛异常。

    口径与 `scratch_rules.parse_rules` 逐字相同：判定路径上抛异常 = 学生交作品时
    看到 500。规则是教研填的，坏了该由写入校验和人工点评兜底。
    """
    try:
        parsed = json.loads(rules_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [r for r in parsed if isinstance(r, dict) and isinstance(r.get("type"), str)]


def validate_rules(rules: list[dict]) -> list[dict]:
    """规则写入时就校验类型，不留到判定时才发现。抛 `ValueError`，由调用方翻成 400。

    未知 type 在判定期会走 needs_review（fail closed，学生不会被误放行），但那是
    **兜底**不是设计：教研把 `require_call` 拼成 `require_calls`，整个班级的提交会
    静静地全部挂起等人工，而没人知道是打错了字。所以写入即拒。
    """
    cleaned: list[dict] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"第 {index + 1} 条规则格式不正确。")
        kind = rule.get("type")
        if not isinstance(kind, str) or kind not in KNOWN_TYPES:
            raise ValueError(
                f"第 {index + 1} 条规则的类型无效：{kind}。"
                f"可用类型：{'、'.join(sorted(KNOWN_TYPES))}。")
        cleaned.append(rule)
    return cleaned
