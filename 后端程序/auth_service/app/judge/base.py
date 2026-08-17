"""判题客户端的公共契约。

抽这一层的唯一理由：本地 Windows 起不了 Linux 沙箱。FakeJudgeClient 让接口、
判分折算与整个前端链路先跑通并被测试覆盖，服务器上 go-judge 就绪后换 GoJudgeClient，
契约不变。见《判题沙箱搭建手册》与《5、学员端考试作答模块》第九节。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple, Protocol

# 判题终态。前端按这些值出文案，新增值必须同步前端 exam.js 的映射表。
ACCEPTED = "accepted"
WRONG_ANSWER = "wrong_answer"
COMPILE_ERROR = "compile_error"
RUNTIME_ERROR = "runtime_error"
TIME_LIMIT = "time_limit"
MEMORY_LIMIT = "memory_limit"
JUDGE_FAILED = "judge_failed"


class JudgeCase(NamedTuple):
    """送去判的一个测试点。is_sample 决定学员能不能看到它的输入输出。"""
    input: str
    expected: str
    is_sample: bool = False
    weight: int = 1
    # 逐点限制：None = 用 judge() 传进来的题目级值（兜底）。放在末尾且有默认值，
    # 现有构造点（exam.py 自测分支只传 3 个位置参数）不用改。
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None


class CaseResult(NamedTuple):
    """单个测试点的判题结果。

    input/expected/actual 只在 is_sample 为真时填充——隐藏测试点的内容是判分资产，
    无论任何呈现配置都不下发。裁剪在这里做一次，路由层不必再记得这条。
    """
    index: int
    status: str
    passed: bool
    time_ms: int = 0
    memory_kb: int = 0
    is_sample: bool = False
    input: str | None = None
    expected: str | None = None
    actual: str | None = None


class JudgeResult(NamedTuple):
    status: str
    cases: list[CaseResult]
    compiled: bool = True
    compile_message: str = ""
    time_ms: int = 0
    memory_kb: int = 0


class JudgeClient(Protocol):
    def judge(
        self, *, language: str, code: str, cases: Sequence[JudgeCase],
        time_limit_ms: int, memory_limit_mb: int,
    ) -> JudgeResult: ...


def outputs_match(actual: str, expected: str) -> bool:
    """输出比对：逐行去行尾空白，再去掉末尾空行，然后整体比。

    不做浮点容差——题库里没有需要容差的题，真出现了再单独加。提前做等于给
    "1.0000001 算不算对" 这种问题埋一个没人记得的默认值。
    """
    def canonical(text: str) -> list[str]:
        lines = [line.rstrip() for line in (text or "").replace("\r\n", "\n").split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        return lines

    return canonical(actual) == canonical(expected)


def overall_status(cases: Sequence[CaseResult]) -> str:
    """整体状态取第一个非通过的测试点的状态——学员先看到的应该是最早出错的原因。"""
    for case in cases:
        if not case.passed:
            return case.status
    return ACCEPTED


def build_case_result(
    index: int, case: JudgeCase, status: str, actual: str, *, time_ms: int = 0, memory_kb: int = 0
) -> CaseResult:
    """统一出口，保证隐藏测试点的内容永远不进结果对象。"""
    passed = status == ACCEPTED
    return CaseResult(
        index=index, status=status, passed=passed, time_ms=time_ms, memory_kb=memory_kb,
        is_sample=case.is_sample,
        input=case.input if case.is_sample else None,
        expected=case.expected if case.is_sample else None,
        actual=actual if case.is_sample else None,
    )
