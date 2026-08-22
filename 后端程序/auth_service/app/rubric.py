"""量规（rubric）的解析与写入校验——**全平台唯一一份**。

原本只长在 `routers/admin_scratch.py` 里（`_parse_rubric` / `_validate_rubric`）。
Python 作品题要用同一套量规结构，把它复制一份就等于承认「Scratch 的量规」和
「Python 的量规」是两个东西：之后 max_score 的口径、id 的字符集、档位下限任何一处
改动都要记得改两遍，而漏掉的那一遍不会报错，只会让某一类题静默走上另一套规矩。

结构（整存整取的 JSON，不做 SQL 内查询）：

    {"max_score": 100,
     "criteria": [{"id": "c_logic", "label": "程序逻辑", "desc": "...",
                   "levels": [{"value": 3, "label": "完全达成", "points": 40, "desc": ""},
                              ...]}]}

`{}` 或缺 criteria = 这道题不用量规，批改只给通过/不通过。这是合法取值，不是错误。

**本模块抛 `ValueError`，不抛 `HTTPException`。** 校验规则属于领域逻辑，不该把
FastAPI 的异常类型焊进来——调用方（各 router）自己决定翻成 400 还是别的什么。
"""
from __future__ import annotations

import json
import re

# 准则 id 的字符集：小写字母/数字/下划线，1-32 位。
# 它会进 `rubric_scores_json` 当键、也会出现在批改接口的请求体里，
# 放开大小写或中文会让「同一准则」出现两种写法而查表落空。
CRITERION_ID_RE = re.compile(r"[a-z0-9_]{1,32}")


def parse_rubric(rubric_json: str) -> dict:
    """把 `rubric_json` 解析成字典。脏数据一律当 `{}`（= 不用量规），不抛异常。

    判定/批改路径上抛异常会让学生或老师看到 500。量规是教研填的，坏了该由写入校验
    和人工兜底，不该由使用方承担（同 `scratch_rules.parse_rules` 的口径）。
    """
    try:
        parsed = json.loads(rubric_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def validate_rubric(rubric: dict) -> dict:
    """量规写入即校验，返回洗干净的副本。`{}` 或缺 criteria = 不用量规，合法。

    理由与规则写入校验同：拼错字段名不该静默生效。具体闸：
    - `max_score` 必须等于各准则**最高档** points 之和——不一致直接拒，**不自动纠正**
      （自动纠正意味着教研以为自己设了 100 分的量规，系统悄悄改成 85，谁也不会发现）。
    - 每项准则：`id` 满足 CRITERION_ID_RE 且组内唯一、`label` 非空、至少两个档位。
    - 每个档位：`value` 组内唯一整数、`label` 非空、`points` 非负整数。
    """
    if not rubric or not rubric.get("criteria"):
        return {}
    criteria = rubric.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return {}
    max_score = rubric.get("max_score")
    if not isinstance(max_score, int) or isinstance(max_score, bool):
        raise ValueError("量规满分 max_score 必须是整数。")
    seen_ids: set[str] = set()
    total_max = 0
    cleaned_criteria: list[dict] = []
    for ci, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            raise ValueError(f"第 {ci + 1} 项量规准则格式不正确。")
        cid = criterion.get("id")
        if not isinstance(cid, str) or not CRITERION_ID_RE.fullmatch(cid):
            raise ValueError(f"第 {ci + 1} 项量规准则的 id 无效（须为 1-32 位小写字母/数字/下划线）。")
        if cid in seen_ids:
            raise ValueError(f"量规准则 id 重复：{cid}。")
        seen_ids.add(cid)
        label = criterion.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"第 {ci + 1} 项量规准则缺少名称。")
        levels = criterion.get("levels")
        if not isinstance(levels, list) or len(levels) < 2:
            raise ValueError(f"量规准则「{label}」至少需要两个档位。")
        seen_values: set[int] = set()
        cleaned_levels: list[dict] = []
        for li, level in enumerate(levels):
            if not isinstance(level, dict):
                raise ValueError(f"量规准则「{label}」的第 {li + 1} 个档位格式不正确。")
            value = level.get("value")
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"量规准则「{label}」的档位 value 必须是整数。")
            if value in seen_values:
                raise ValueError(f"量规准则「{label}」的档位 value 重复：{value}。")
            seen_values.add(value)
            level_label = level.get("label")
            if not isinstance(level_label, str) or not level_label.strip():
                raise ValueError(f"量规准则「{label}」的第 {li + 1} 个档位缺少名称。")
            points = level.get("points")
            if not isinstance(points, int) or isinstance(points, bool) or points < 0:
                raise ValueError(f"量规准则「{label}」的档位分值必须是非负整数。")
            cleaned_levels.append({
                "value": value, "label": level_label.strip(),
                "points": points, "desc": str(level.get("desc") or ""),
            })
        cleaned_criteria.append({
            "id": cid, "label": label.strip(),
            "desc": str(criterion.get("desc") or ""),
            "levels": cleaned_levels,
        })
        total_max += max(lvl["points"] for lvl in cleaned_levels)
    if max_score != total_max:
        raise ValueError(
            f"量规满分 max_score 应等于各准则最高档分值之和（{total_max}），"
            f"当前为 {max_score}。请核对后重试。")
    return {"max_score": max_score, "criteria": cleaned_criteria}
