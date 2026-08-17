"""GoJudgeClient 的连接口径。

这里只有一条护栏，但它值一个独立文件：判题客户端**绝不能走系统代理**。
2026-08-07 踩过一次——开发机开着 Clash，httpx 默认 trust_env=True 会读 Windows
注册表里的系统代理，而它只认 NO_PROXY 环境变量、不识别注册表 ProxyOverride 里的
127.* 绕过规则。于是发往回环 5050 的判题请求被塞进代理、转去远端节点，回 502，
学员端看到「判题服务暂时不可用」。整整 19 次提交全废，go-judge 日志里一条记录都没有
（请求根本没到），排查成本极高。

这条约束长得像"多余的参数"，很容易在某次清理里被顺手删掉，所以钉住它。
"""

from __future__ import annotations

import httpx

from app.judge.gojudge import GoJudgeClient

PROXY = "http://127.0.0.1:7897"


def test_judge_client_never_goes_through_a_system_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", PROXY)
    monkeypatch.setenv("HTTPS_PROXY", PROXY)
    monkeypatch.setenv("ALL_PROXY", PROXY)

    client = GoJudgeClient("http://127.0.0.1:5050", token="t")

    # 反证：同样的环境变量下，httpx 的默认行为确实会挂上代理。
    # 这一句保证本用例不会因为 httpx 换了语义而静默变成永真。
    assert httpx.Client(trust_env=True)._mounts, "httpx 不再从环境读代理了？这条用例需要重写"

    assert client._client.trust_env is False
    assert not client._client._mounts, "判题请求打的是回环地址，任何代理挂载都是错的"


def test_token_goes_into_the_client_headers():
    """token 挂在长连接的客户端上，而不是每次请求现拼——漏了就是 401。"""
    assert (
        GoJudgeClient("http://127.0.0.1:5050", token="abc")._client.headers["Authorization"]
        == "Bearer abc"
    )
    # 没配 token 时不许硬塞一个空的 Bearer，那会被 go-judge 判成非法凭据
    assert "Authorization" not in GoJudgeClient("http://127.0.0.1:5050")._client.headers


def test_run_case_uses_per_case_limits_with_problem_level_fallback(monkeypatch):
    """_run_case 逐点值优先，None 时兜底用题目级值（交接文档 §4.2）。"""
    from app.judge.base import JudgeCase
    from app.judge.gojudge import GoJudgeClient

    client = GoJudgeClient("http://127.0.0.1:5050", token="t")
    captured = {}

    def fake_post_run(self, cmd):
        captured["cmd"] = cmd
        return {"status": "Accepted", "files": {"stdout": "3\n"}}

    monkeypatch.setattr(GoJudgeClient, "_post_run", fake_post_run)
    spec = {"run": ["/bin/cat"], "source": "main.c", "artifact": "a.out"}

    inherited = JudgeCase(input="1 2", expected="3", is_sample=False, weight=1)
    client._run_case(spec, "code", "artifact-1", 0, inherited, time_limit_ms=2000, memory_limit_mb=256)
    assert captured["cmd"]["cpuLimit"] == 2000 * 1_000_000
    assert captured["cmd"]["clockLimit"] == 2000 * 1_000_000 * 2  # 墙钟 = 2× cpu
    assert captured["cmd"]["memoryLimit"] == 256 * 1024 * 1024

    overridden = JudgeCase(input="1 2", expected="3", is_sample=False, weight=1,
                           time_limit_ms=3000, memory_limit_mb=64)
    client._run_case(spec, "code", "artifact-1", 0, overridden, time_limit_ms=2000, memory_limit_mb=256)
    assert captured["cmd"]["cpuLimit"] == 3000 * 1_000_000
    assert captured["cmd"]["memoryLimit"] == 64 * 1024 * 1024
