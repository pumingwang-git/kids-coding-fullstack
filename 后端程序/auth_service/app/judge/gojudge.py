"""go-judge 判题客户端。

部署见《判题沙箱搭建手册》。go-judge 只监听回环，因此后端进程必须与它同机——
这是设计如此：它执行任意代码，暴露到网络上等于把服务器送人。

一次判题 = 编译一次（Python 跳过）+ 逐测试点运行 + 清理缓存文件。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from .base import (
    ACCEPTED,
    COMPILE_ERROR,
    JUDGE_FAILED,
    MEMORY_LIMIT,
    RUNTIME_ERROR,
    TIME_LIMIT,
    WRONG_ANSWER,
    JudgeCase,
    JudgeResult,
    build_case_result,
    outputs_match,
    overall_status,
)

logger = logging.getLogger(__name__)

ENV = ["PATH=/usr/bin:/bin", "HOME=/tmp", "LANG=C.UTF-8"]
OUTPUT_MAX = 64 * 1024  # 单个测试点回收的 stdout 上限，超出按输出超限处理
COMPILE_MESSAGE_MAX = 4 * 1024

# 编译比运行吃内存多得多，单独给一份宽松限制，别用题目的 memory_limit。
COMPILE_MEMORY_BYTES = 512 * 1024 * 1024
COMPILE_CPU_NS = 15 * 1_000_000_000

LANGUAGES = {
    "cpp": {
        "source": "a.cc",
        "compile": ["/usr/bin/g++", "-O2", "-std=c++17", "-o", "a", "a.cc"],
        "artifact": "a",
        "run": ["a"],
    },
    "python": {
        "source": "a.py",
        "compile": None,
        "artifact": None,
        "run": ["/usr/bin/python3", "a.py"],
    },
}

# go-judge 的 status → 我们的终态。未列出的一律当运行时错误。
STATUS_MAP = {
    "Accepted": ACCEPTED,
    "Time Limit Exceeded": TIME_LIMIT,
    "Memory Limit Exceeded": MEMORY_LIMIT,
    "Output Limit Exceeded": RUNTIME_ERROR,
    "Nonzero Exit Status": RUNTIME_ERROR,
    "Signalled": RUNTIME_ERROR,
    "File Error": JUDGE_FAILED,
    "Internal Error": JUDGE_FAILED,
}


class JudgeUnavailable(RuntimeError):
    """沙箱连不上或返回了无法解析的东西。调用方据此落 judge_failed，不算学员 0 分。"""


class GoJudgeClient:
    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        # trust_env=False 是必须的：judge_url 永远是回环地址，绝不能过系统代理。
        # Windows 上 httpx 会读注册表里的系统代理，且只认 NO_PROXY 环境变量、
        # 不识别注册表 ProxyOverride 的 127.* 绕过规则——开着 Clash 这类代理时，
        # 请求会被送进代理再转去远端节点，回一个 502 Bad Gateway（2026-08-07 实测踩中）。
        self._client = httpx.Client(
            trust_env=False,
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=timeout,
        )

    # ---------- 对外 ----------

    def judge(
        self, *, language: str, code: str, cases: Sequence[JudgeCase],
        time_limit_ms: int, memory_limit_mb: int,
    ) -> JudgeResult:
        spec = LANGUAGES.get(language)
        if spec is None:
            raise JudgeUnavailable(f"不支持的语言：{language}")

        artifact_id = None
        try:
            if spec["compile"]:
                artifact_id, message = self._compile(spec, code)
                if artifact_id is None:
                    return JudgeResult(
                        status=COMPILE_ERROR, cases=[], compiled=False,
                        compile_message=message[:COMPILE_MESSAGE_MAX],
                    )
            results = [
                self._run_case(spec, code, artifact_id, index, case, time_limit_ms, memory_limit_mb)
                for index, case in enumerate(cases)
            ]
            return JudgeResult(
                status=overall_status(results), cases=results, compiled=True,
                time_ms=max((item.time_ms for item in results), default=0),
                memory_kb=max((item.memory_kb for item in results), default=0),
            )
        finally:
            if artifact_id:
                self._delete_file(artifact_id)

    # ---------- 内部 ----------

    def _post_run(self, cmd: dict) -> dict:
        try:
            response = self._client.post(f"{self._base_url}/run", json={"cmd": [cmd]})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JudgeUnavailable(str(exc)) from exc
        if not isinstance(payload, list) or not payload:
            raise JudgeUnavailable("判题机返回了空结果。")
        return payload[0]

    def _compile(self, spec: dict, code: str) -> tuple[str | None, str]:
        """返回 (可执行文件的 fileId, 编译输出)。编译失败时 fileId 为 None。"""
        result = self._post_run({
            "args": spec["compile"],
            "env": ENV,
            "files": [
                {"content": ""},
                {"name": "stdout", "max": COMPILE_MESSAGE_MAX},
                {"name": "stderr", "max": COMPILE_MESSAGE_MAX},
            ],
            "cpuLimit": COMPILE_CPU_NS,
            "clockLimit": COMPILE_CPU_NS * 2,
            "memoryLimit": COMPILE_MEMORY_BYTES,
            "procLimit": 50,
            "copyIn": {spec["source"]: {"content": code}},
            "copyOutCached": [spec["artifact"]],
        })
        files = result.get("files") or {}
        message = (files.get("stderr") or "") + (files.get("stdout") or "")
        if result.get("status") != "Accepted":
            return None, message or "编译失败。"
        file_id = (result.get("fileIds") or {}).get(spec["artifact"])
        if not file_id:
            raise JudgeUnavailable("编译成功但没有拿到可执行文件。")
        return file_id, message

    def _run_case(
        self, spec: dict, code: str, artifact_id: str | None, index: int,
        case: JudgeCase, time_limit_ms: int, memory_limit_mb: int,
    ):
        copy_in = (
            {spec["artifact"]: {"fileId": artifact_id}} if artifact_id
            else {spec["source"]: {"content": code}}
        )
        # 逐点值优先，题目级值是兜底。case 的两个字段为 None 时用 judge() 传进来的值。
        effective_ms = case.time_limit_ms or time_limit_ms
        effective_mb = case.memory_limit_mb or memory_limit_mb
        cpu_ns = max(effective_ms, 1) * 1_000_000
        result = self._post_run({
            "args": spec["run"],
            "env": ENV,
            "files": [
                {"content": case.input},
                {"name": "stdout", "max": OUTPUT_MAX},
                {"name": "stderr", "max": OUTPUT_MAX},
            ],
            "cpuLimit": cpu_ns,
            # 墙钟给两倍：CPU 时间正常但卡在 sleep/IO 的程序也要收掉。
            "clockLimit": cpu_ns * 2,
            "memoryLimit": max(effective_mb, 1) * 1024 * 1024,
            "procLimit": 50,
            "copyIn": copy_in,
        })
        raw_status = result.get("status", "Internal Error")
        actual = (result.get("files") or {}).get("stdout", "")
        status = STATUS_MAP.get(raw_status, RUNTIME_ERROR)
        if status == ACCEPTED and not outputs_match(actual, case.expected):
            status = WRONG_ANSWER
        return build_case_result(
            index, case, status, actual,
            time_ms=int(result.get("time", 0) / 1_000_000),
            memory_kb=int(result.get("memory", 0) / 1024),
        )

    def _delete_file(self, file_id: str) -> None:
        """清理编译产物。漏掉会让 /dev/shm 越涨越满，最后判题机整个不可用。"""
        try:
            self._client.delete(f"{self._base_url}/file/{file_id}")
        except httpx.HTTPError:
            logger.warning("判题机文件清理失败：%s", file_id)
