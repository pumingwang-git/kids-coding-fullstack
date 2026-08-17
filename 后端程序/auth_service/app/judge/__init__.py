"""判题客户端：按配置选实现，其余代码只认 JudgeClient 协议。"""

from __future__ import annotations

from .base import (
    ACCEPTED,
    COMPILE_ERROR,
    JUDGE_FAILED,
    MEMORY_LIMIT,
    RUNTIME_ERROR,
    TIME_LIMIT,
    WRONG_ANSWER,
    CaseResult,
    JudgeCase,
    JudgeClient,
    JudgeResult,
    outputs_match,
)
from .fake import FakeJudgeClient
from .gojudge import GoJudgeClient, JudgeUnavailable

__all__ = [
    "ACCEPTED", "COMPILE_ERROR", "JUDGE_FAILED", "MEMORY_LIMIT", "RUNTIME_ERROR",
    "TIME_LIMIT", "WRONG_ANSWER", "CaseResult", "JudgeCase", "JudgeClient",
    "JudgeResult", "JudgeUnavailable", "FakeJudgeClient", "GoJudgeClient",
    "build_judge_client", "outputs_match",
]


def build_judge_client(settings) -> JudgeClient:
    """判题后端的唯一构造入口。默认 fake——本地开发不该因为没有沙箱就跑不起来。"""
    if settings.judge_backend == "go-judge":
        return GoJudgeClient(settings.judge_url, settings.judge_token, settings.judge_timeout_seconds)
    return FakeJudgeClient()
