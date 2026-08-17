"""判分引擎：纯函数，不依赖数据库会话。

全项目最不该出错的地方，因此这里只接收已经取好的原始数据（选项的 label 与对错、
填空的标准答案、编程题的测试点结果），调用方负责从库里把它们查出来。这样每一条
判分规则都能用几行单测钉死，见 tests/test_scoring.py。

规则一律写死不做配置——判分口径可配等于"同一张卷两次考试分数不可比"。
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import NamedTuple


class QuestionScore(NamedTuple):
    """单题判分结果。

    is_correct 与 score 都要：前者给统计用（这道题的班级正确率），后者给成绩用。
    编程题过 6/10 个测试点时 score>0 而 is_correct=False，两者不能互相推导。
    """
    score: int
    is_correct: bool
    detail: dict


class CaseOutcome(NamedTuple):
    """编程题单个测试点的结果。weight 取 TestCase.score，为空时按等权处理。"""
    passed: bool
    weight: int = 1


def parse_answer(raw: str | None) -> dict:
    """答案 JSON 反序列化。库里的脏数据不能让整卷判分崩掉——坏了就当没作答。"""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_blank_alternatives(raw: str | None) -> list[str]:
    """FillAnswer.alternatives_json → 写法列表。与 parse_answer 同样的态度：
    脏数据当"没有别的写法"处理，绝不让一行坏 JSON 把整卷判分掀翻。"""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def normalize_blank(text: str) -> str:
    """填空比对前的规范化。顺序不能换。

    NFKC 要在引号替换之前：它会把全角引号归一成半角以外的形态，反过来做会漏。
    casefold() 比 lower() 更彻底（能处理 ß→ss 这类），虽然中文题库用不上，
    但填空题里出现英文关键字是常态，用更彻底的那个不吃亏。
    """
    text = (text or "").strip()
    text = unicodedata.normalize("NFKC", text)
    for source, target in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")):
        text = text.replace(source, target)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def blank_score_split(full: int, count: int) -> list[int]:
    """把题目分值平分到各空，余数给最后一空——保证各空之和恰好等于题目分值。"""
    if count <= 0:
        return []
    base = full // count
    scores = [base] * count
    scores[-1] += full - base * count
    return scores


def score_choice(picked: str | None, options: Sequence[tuple[str, bool]], full: int) -> QuestionScore:
    """单选 / 判断：选中项正确即满分。未作答 0 分。

    picked 是选项的原始 label（A/B/C/D），不是洗牌后的下标——存下标必错，
    因为学员看到的顺序和库里不同。
    """
    correct = {label for label, is_correct in options if is_correct}
    hit = bool(picked) and picked in correct
    return QuestionScore(full if hit else 0, hit, {"picked": picked, "correct": sorted(correct)})


def score_multi_choice(
    picked: Sequence[str] | None, options: Sequence[tuple[str, bool]], full: int, partial_credit: bool
) -> QuestionScore:
    """多选：全对满分；开了半分则「少选」给一半，「错选/多选」0 分。

    半分为什么是 floor(full/2) 而不是按比例：按比例会让"只勾最有把握的那个"
    成为最优策略，把多选题降级成单选题。半分制只奖励方向对但不全，不奖励保守。
    """
    chosen = {label for label in (picked or []) if label}
    correct = {label for label, is_correct in options if is_correct}
    detail = {"picked": sorted(chosen), "correct": sorted(correct)}
    if chosen == correct:
        return QuestionScore(full, True, detail)
    # 空作答落在 chosen < correct 的分支里，必须先挡掉，否则未作答也能拿半分。
    if partial_credit and chosen and chosen < correct:
        return QuestionScore(full // 2, False, {**detail, "partial": True})
    return QuestionScore(0, False, detail)


def accepted_blank_answers(expected: str | Sequence[str]) -> list[str]:
    """把一个空的可接受答案统一成列表。

    传单个字符串时**不能**直接当序列用——那会被拆成一个个字符，"print" 变成
    p/r/i/n/t 五个答案，学员填 "p" 就算对。这个坑值得一个显式的 isinstance。
    """
    if isinstance(expected, str):
        return [expected]
    return list(expected)


def score_fill(
    submitted: Mapping[str, str] | None,
    answers: Sequence[tuple[str, str | Sequence[str]]],
    full: int,
) -> QuestionScore:
    """填空：按 blank_key 逐空比对，每空均分题目分值。

    answers 是 [(blank_key, 可接受答案)]，顺序即 blank_index 顺序。第二项可以是
    单个字符串，也可以是一组写法（标准答案在前，FillAnswer.alternatives_json 在后）——
    一个空往往有多种写法（0.5 与 1/2、列表与 list），命中其中任意一条就算对。

    多写法之间是**平权**的：不因为学员写的是"次要写法"就扣分。判分明细里记下命中的是
    哪一条（matched），复盘时才说得清"他写的 1/2 为什么算对"。
    """
    if not answers:
        return QuestionScore(0, False, {"blanks": []})
    provided = submitted or {}
    splits = blank_score_split(full, len(answers))
    total, results = 0, []
    for (key, expected), portion in zip(answers, splits):
        got = normalize_blank(provided.get(key, ""))
        matched = next(
            (item for item in accepted_blank_answers(expected) if normalize_blank(item) == got),
            None,
        )
        # 空作答要挡掉：标准答案本身为空的脏数据会让"什么都不填"命中，白送分。
        hit = matched is not None and got != ""
        if hit:
            total += portion
        results.append({"blank_key": key, "correct": hit, **({"matched": matched} if hit else {})})
    all_hit = all(item["correct"] for item in results)
    return QuestionScore(total, all_hit, {"blanks": results})


def score_programming(
    cases: Sequence[CaseOutcome], full: int, score_mode: str, *, compile_only: bool = False,
    compiled: bool = True,
) -> QuestionScore:
    """编程题折算。Paper.score_mode 在这里第一次被真正读取。

    compile_only 对应题库的 pass_condition == "编译通过"：编译成功即满分，不看测试点。
    """
    if compile_only:
        return QuestionScore(full if compiled else 0, compiled, {"compile_only": True, "compiled": compiled})
    if not compiled:
        return QuestionScore(0, False, {"compiled": False})
    if not cases:
        return QuestionScore(0, False, {"cases": 0})
    passed = [case for case in cases if case.passed]
    all_passed = len(passed) == len(cases)
    detail = {"cases": len(cases), "passed": len(passed)}
    if score_mode == "all_or_nothing":
        return QuestionScore(full if all_passed else 0, all_passed, detail)
    # testcase 模式统一走加权比例：测试点没配分值时权重全为 1，退化成「通过数/总数 × 题目分」。
    # 不直接加总 TestCase.score——那样一道卷面 20 分的题可能判出 100 分，打穿 total_score。
    total_weight = sum(max(case.weight, 0) for case in cases)
    if total_weight <= 0:
        return QuestionScore(full if all_passed else 0, all_passed, detail)
    hit_weight = sum(max(case.weight, 0) for case in passed)
    return QuestionScore(math.floor(full * hit_weight / total_weight), all_passed, detail)


def strip_answer_keys(detail):
    """从判分明细里摘掉标准答案，供**学员端**下发。

    `score_choice` / `score_multi_choice` / `score_fill` 会把正确答案写进 detail，
    那是给后台答卷回看用的（老师要并排看"标准答案 vs 学员答案"，admin_results
    的 attempt_review 明确不做裁剪）。但 detail 同时被持久化进 attempt_answers /
    lesson_problem_attempts，学员端结果页与练习判定区又原样下发了它——于是配了
    show_analysis=never 的卷子，答案照样从 detail 里流出去。

    裁剪放在**读路径**而不是 score_* 里，有两个理由：
      1. 库里已经存着一批带答案的 detail_json，只改写入端救不了存量数据；
      2. 后台回看确实要这些字段，源头删掉等于让老师那边少一份信息。

    摘两处：
      - 顶层 `correct`：正确选项的 label 列表（choice / multi_choice / judge）；
      - `blanks[].matched`：填空命中的那条可接受写法原文（只在答对时写入，
        但那仍然是标准答案的原文）。

    **保留 `blanks[].correct`**——它是逐空的对错布尔值，是判定不是答案，
    学员端结果页靠它给每个空标对错（ExamResult.vue:135）。两个键同名不同义，
    按键名一刀切会把结果页的逐空标记一起删掉。
    """
    if detail is None or not isinstance(detail, Mapping):
        return detail
    out = {key: value for key, value in detail.items() if key != "correct"}
    blanks = out.get("blanks")
    if isinstance(blanks, list):
        out["blanks"] = [
            {key: value for key, value in blank.items() if key != "matched"}
            if isinstance(blank, Mapping) else blank
            for blank in blanks
        ]
    return out


class QuestionSpec(NamedTuple):
    """判一道题需要的全部题面事实，由调用方从库里查好后传入。"""
    type: str
    full: int
    options: Sequence[tuple[str, bool]] = ()
    # 每空是 (blank_key, 可接受答案)，第二项可以是单个字符串或一组写法，见 score_fill
    blanks: Sequence[tuple[str, str | Sequence[str]]] = ()
    cases: Sequence[CaseOutcome] = ()
    compile_only: bool = False
    compiled: bool = True


def score_question(answer: Mapping | None, spec: QuestionSpec, *, partial_credit_multi: bool,
                   score_mode: str) -> QuestionScore:
    """按题型分发。未知题型一律 0 分且标记 unsupported，绝不抛异常——
    一道题判不了不该让整张卷交不上去。"""
    answer = answer or {}
    if spec.type in {"choice", "judge"}:
        return score_choice(answer.get("picked"), spec.options, spec.full)
    if spec.type == "multi_choice":
        return score_multi_choice(answer.get("picked"), spec.options, spec.full, partial_credit_multi)
    if spec.type == "fill":
        return score_fill(answer.get("blanks"), spec.blanks, spec.full)
    if spec.type == "programming":
        return score_programming(
            spec.cases, spec.full, score_mode, compile_only=spec.compile_only, compiled=spec.compiled
        )
    return QuestionScore(0, False, {"unsupported": spec.type})
