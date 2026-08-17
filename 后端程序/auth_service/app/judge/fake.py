"""假判题器：不执行任何代码，按代码内容的固定规则给结果。

用途只有两个：本地 Windows 开发、CI。**绝不能在生产启用**——它不看正确性，
只看代码里有没有出现某些字符串。create_app() 会在 environment == "production"
且 judge_backend == "fake" 时直接拒绝启动。

规则（写死，测试依赖它们）：
  空代码            → compile_error
  含 __TLE__        → 第 1 个测试点起 time_limit
  含 __WA__         → 第 2 个测试点起 wrong_answer（第 1 个仍通过，便于测「部分分」）
  含 print / cout   → 全部通过
  其余              → 全部 wrong_answer
"""

from __future__ import annotations

from collections.abc import Sequence

from .base import (
    ACCEPTED,
    COMPILE_ERROR,
    TIME_LIMIT,
    WRONG_ANSWER,
    JudgeCase,
    JudgeResult,
    build_case_result,
    overall_status,
)


class FakeJudgeClient:
    """无沙箱的确定性判题器。同样的代码永远得到同样的结果。"""

    def judge(
        self, *, language: str, code: str, cases: Sequence[JudgeCase],
        time_limit_ms: int, memory_limit_mb: int,
    ) -> JudgeResult:
        source = code or ""
        if not source.strip():
            return JudgeResult(
                status=COMPILE_ERROR, cases=[], compiled=False,
                compile_message="error: 代码为空（FakeJudgeClient）",
            )

        results = []
        for index, case in enumerate(cases):
            status, actual = self._verdict(source, index, case)
            results.append(build_case_result(index, case, status, actual, time_ms=1, memory_kb=1024))
        return JudgeResult(
            status=overall_status(results), cases=results, compiled=True,
            compile_message="", time_ms=1 if results else 0, memory_kb=1024 if results else 0,
        )

    @staticmethod
    def _verdict(source: str, index: int, case: JudgeCase) -> tuple[str, str]:
        if "__TLE__" in source:
            return TIME_LIMIT, ""
        if "__WA__" in source and index >= 1:
            return WRONG_ANSWER, "__fake_wrong_output__"
        if "print" in source or "cout" in source:
            return ACCEPTED, case.expected
        return WRONG_ANSWER, "__fake_wrong_output__"
