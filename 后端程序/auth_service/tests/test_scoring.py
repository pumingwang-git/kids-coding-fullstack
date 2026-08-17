"""判分引擎单测：五种题型的每一条规则各钉一颗钉子。

这里跑得快、不碰数据库，判分改动先在这一层挡住回归。
"""

import pytest

from app.scoring import (
    CaseOutcome,
    QuestionSpec,
    blank_score_split,
    normalize_blank,
    parse_answer,
    score_choice,
    score_fill,
    score_multi_choice,
    score_programming,
    score_question,
)

OPTIONS = [("A", False), ("B", True), ("C", False), ("D", False)]
MULTI = [("A", True), ("B", False), ("C", True), ("D", False)]


# ---------- 单选 / 判断 ----------

def test_choice_hit_gets_full_and_miss_gets_zero():
    assert score_choice("B", OPTIONS, 5).score == 5
    assert score_choice("B", OPTIONS, 5).is_correct is True
    assert score_choice("A", OPTIONS, 5) == (0, False, {"picked": "A", "correct": ["B"]})


def test_choice_unanswered_is_zero_not_crash():
    assert score_choice(None, OPTIONS, 5).score == 0
    assert score_choice("", OPTIONS, 5).score == 0


def test_choice_matches_by_label_not_position():
    """洗牌后前端看到的顺序变了，但回传的仍是原始 label——这条错了多选全盘皆错。"""
    shuffled = [("C", False), ("B", True), ("D", False), ("A", False)]
    assert score_choice("B", shuffled, 5).score == 5


# ---------- 多选 ----------

def test_multi_all_correct_gets_full():
    assert score_multi_choice(["A", "C"], MULTI, 6, False).score == 6
    assert score_multi_choice(["C", "A"], MULTI, 6, False).score == 6  # 顺序无关


def test_multi_partial_off_gives_zero():
    assert score_multi_choice(["A"], MULTI, 6, False).score == 0


def test_multi_partial_on_gives_half_for_undershoot():
    result = score_multi_choice(["A"], MULTI, 6, True)
    assert result.score == 3 and result.is_correct is False and result.detail["partial"] is True


def test_multi_partial_on_still_zero_for_wrong_pick():
    """含任一错项就是 0，不管对了几个——半分只奖励方向对但不全。"""
    assert score_multi_choice(["A", "B"], MULTI, 6, True).score == 0
    assert score_multi_choice(["A", "C", "D"], MULTI, 6, True).score == 0


def test_multi_empty_answer_never_gets_half():
    """空集合是任何集合的子集，不先挡掉的话未作答也能拿半分。"""
    assert score_multi_choice([], MULTI, 6, True).score == 0
    assert score_multi_choice(None, MULTI, 6, True).score == 0


def test_multi_half_rounds_down():
    assert score_multi_choice(["A"], MULTI, 5, True).score == 2


# ---------- 填空 ----------

def test_fill_all_blanks_correct():
    answers = [("b1", "print"), ("b2", "42")]
    result = score_fill({"b1": "print", "b2": "42"}, answers, 10)
    assert result.score == 10 and result.is_correct is True


def test_fill_partial_credit_per_blank():
    answers = [("b1", "print"), ("b2", "42")]
    result = score_fill({"b1": "print", "b2": "43"}, answers, 10)
    assert result.score == 5 and result.is_correct is False


def test_fill_split_remainder_goes_to_last_blank():
    assert blank_score_split(10, 3) == [3, 3, 4]
    assert sum(blank_score_split(7, 2)) == 7
    answers = [("b1", "a"), ("b2", "b"), ("b3", "c")]
    assert score_fill({"b1": "a", "b2": "b", "b3": "c"}, answers, 10).score == 10


def test_fill_matches_by_key_not_order():
    """题干调整了空的先后顺序也不会错位——这是按 blank_key 存的理由。"""
    answers = [("b1", "print"), ("b2", "42")]
    assert score_fill({"b2": "42", "b1": "print"}, answers, 10).score == 10


@pytest.mark.parametrize(
    "submitted",
    ["  print  ", "PRINT", "Print", "ｐｒｉｎｔ"],  # 空白 / 大小写 / 全角
)
def test_fill_normalization_accepts_common_variants(submitted):
    assert score_fill({"b1": submitted}, [("b1", "print")], 4).score == 4


def test_fill_normalization_handles_smart_quotes_and_inner_spaces():
    assert score_fill({"b1": '“hello”'}, [("b1", '"hello"')], 4).score == 4
    assert score_fill({"b1": "int   a"}, [("b1", "int a")], 4).score == 4


def test_fill_missing_blank_is_wrong_not_crash():
    assert score_fill({}, [("b1", "print")], 4).score == 0
    assert score_fill(None, [("b1", "print")], 4).score == 0


# ---------- 填空：一个空多种写法 ----------

def test_fill_accepts_any_listed_spelling():
    """0.5 和 1/2 都算对，几条写法平权，不因为写的是"次要写法"就扣分。"""
    answers = [("b1", ["0.5", "1/2", "二分之一"])]
    for submitted in ("0.5", "1/2", "二分之一"):
        assert score_fill({"b1": submitted}, answers, 4).score == 4
    assert score_fill({"b1": "0.6"}, answers, 4).score == 0


def test_fill_alternatives_go_through_normalization_too():
    """规范化对每一条写法都生效，不是只对标准答案生效。"""
    answers = [("b1", ["列表", "list"])]
    assert score_fill({"b1": " LIST "}, answers, 4).score == 4
    assert score_fill({"b1": "ｌｉｓｔ"}, answers, 4).score == 4


def test_fill_detail_records_which_spelling_matched():
    """判分明细要记下命中的是哪一条，复盘时才说得清"他写的 1/2 为什么算对"。"""
    detail = score_fill({"b1": "1/2"}, [("b1", ["0.5", "1/2"])], 4).detail
    assert detail["blanks"][0]["matched"] == "1/2"
    # 没命中就不写这个键，免得前端把 null 渲染成一个空的"正确答案"
    assert "matched" not in score_fill({"b1": "x"}, [("b1", ["0.5"])], 4).detail["blanks"][0]


def test_fill_single_string_answer_is_not_iterated_into_chars():
    """第二项传单个字符串时不能被当序列拆成字符——那样填 'p' 就能命中 'print'。"""
    assert score_fill({"b1": "p"}, [("b1", "print")], 4).score == 0
    assert score_fill({"b1": "print"}, [("b1", "print")], 4).score == 4


def test_fill_empty_answer_never_scores():
    """标准答案是脏数据（空串）时，什么都不填也不许得分。"""
    assert score_fill({"b1": ""}, [("b1", [""])], 4).score == 0
    assert score_fill({"b1": "   "}, [("b1", ["", "x"])], 4).score == 0


def test_fill_without_standard_answers_is_zero():
    assert score_fill({"b1": "x"}, [], 4).score == 0


def test_normalize_blank_is_idempotent():
    once = normalize_blank(" Int  A ")
    assert normalize_blank(once) == once


# ---------- 编程题 ----------

def test_programming_testcase_mode_is_proportional():
    cases = [CaseOutcome(True), CaseOutcome(True), CaseOutcome(False), CaseOutcome(False)]
    assert score_programming(cases, 20, "testcase").score == 10


def test_programming_testcase_mode_rounds_down():
    cases = [CaseOutcome(True), CaseOutcome(False), CaseOutcome(False)]
    assert score_programming(cases, 20, "testcase").score == 6


def test_programming_testcase_mode_respects_weights():
    """测试点配了分值就按相对权重折算，但总分仍受卷面题目分值约束。"""
    cases = [CaseOutcome(True, 30), CaseOutcome(False, 70)]
    assert score_programming(cases, 20, "testcase").score == 6


def test_programming_all_or_nothing():
    partial = [CaseOutcome(True), CaseOutcome(False)]
    full = [CaseOutcome(True), CaseOutcome(True)]
    assert score_programming(partial, 20, "all_or_nothing").score == 0
    assert score_programming(full, 20, "all_or_nothing").score == 20


def test_programming_all_passed_sets_is_correct():
    cases = [CaseOutcome(True), CaseOutcome(True)]
    assert score_programming(cases, 20, "testcase") == (20, True, {"cases": 2, "passed": 2})


def test_programming_partial_score_is_not_correct():
    """拿部分分但没全过：score>0 而 is_correct=False，两者不能互相推导。"""
    result = score_programming([CaseOutcome(True), CaseOutcome(False)], 20, "testcase")
    assert result.score == 10 and result.is_correct is False


def test_programming_compile_failure_is_zero():
    cases = [CaseOutcome(True), CaseOutcome(True)]
    assert score_programming(cases, 20, "testcase", compiled=False).score == 0


def test_programming_compile_only_ignores_cases():
    assert score_programming([], 20, "testcase", compile_only=True, compiled=True).score == 20
    assert score_programming([], 20, "testcase", compile_only=True, compiled=False).score == 0


def test_programming_without_cases_is_zero():
    assert score_programming([], 20, "testcase").score == 0


# ---------- 分发与解析 ----------

def test_score_question_dispatches_each_type():
    assert score_question({"picked": "B"}, QuestionSpec("choice", 5, options=OPTIONS),
                          partial_credit_multi=False, score_mode="testcase").score == 5
    assert score_question({"picked": ["A", "C"]}, QuestionSpec("multi_choice", 6, options=MULTI),
                          partial_credit_multi=False, score_mode="testcase").score == 6
    assert score_question({"blanks": {"b1": "x"}}, QuestionSpec("fill", 4, blanks=[("b1", "x")]),
                          partial_credit_multi=False, score_mode="testcase").score == 4
    assert score_question({}, QuestionSpec("programming", 20, cases=[CaseOutcome(True)]),
                          partial_credit_multi=False, score_mode="testcase").score == 20


def test_score_question_unknown_type_is_zero_not_exception():
    result = score_question({}, QuestionSpec("essay", 10), partial_credit_multi=False, score_mode="testcase")
    assert result.score == 0 and result.detail == {"unsupported": "essay"}


def test_score_question_missing_answer_is_zero():
    assert score_question(None, QuestionSpec("choice", 5, options=OPTIONS),
                          partial_credit_multi=False, score_mode="testcase").score == 0


@pytest.mark.parametrize("raw", ["", None, "not json", "[1,2]", "null"])
def test_parse_answer_tolerates_garbage(raw):
    assert parse_answer(raw) == {}


def test_parse_answer_reads_object():
    assert parse_answer('{"type":"choice","picked":"B"}') == {"type": "choice", "picked": "B"}
