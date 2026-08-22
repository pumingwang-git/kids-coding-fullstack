"""打字星球后端最小回归（2026-08-15，见《开发文档/27》）。

只覆盖核心路径 + 本次改动的最小回归：
- 端点注册（bootstrap / profile / sessions / audio）
- bootstrap 空态
- profile 保存 + 后写覆盖 + CSRF 必填
- sessions 批量幂等（client_uuid 全局查重口径，同 uuid 重复只插一条）
- sessions 批次上限 50
- audio 参数校验 + 游客可访问（不鉴权）
"""
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_exam import build_app, scsrf, student_login

TYPING_ROUTES = [
    "/api/typing/bootstrap",
    "/api/typing/profile",
    "/api/typing/sessions",
    "/api/typing/audio",
]


def _setup():
    app = build_app(Path(tempfile.mkdtemp()))
    client = student_login(app, username="typinglearner")
    return client


def _session(client_uuid: str, **kw) -> dict:
    base = {
        "client_uuid": client_uuid,
        "dict_id": "cet4",
        "chapter": 1,
        "duration_sec": 120,
        "count_input": 40,
        "count_correct": 38,
        "count_typo": 2,
        "mode_dictation": False,
    }
    base.update(kw)
    return base


def test_routes_registered():
    """4 个端点都注册（防止 include_router 漏挂）。"""
    from app.main import app

    schema = app.openapi()
    for route in TYPING_ROUTES:
        assert route in schema["paths"], f"缺少 {route}"


def test_bootstrap_empty_state():
    client = _setup()
    r = client.get("/api/typing/bootstrap")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile"] is None
    assert body["stats"] == {"today_sections": 0, "total_sections": 0}


def test_profile_save_and_overwrite():
    client = _setup()
    r = client.post("/api/typing/profile", headers=scsrf(client),
                    json={"age_group": "3-6", "settings": {"dict": "kids"}})
    assert r.status_code == 200, r.text
    body = client.get("/api/typing/bootstrap").json()
    assert body["profile"]["age_group"] == "3-6"
    assert body["profile"]["settings"] == {"dict": "kids"}
    # 后写覆盖（服务端不做业务判定，只校验取值合法）
    r = client.post("/api/typing/profile", headers=scsrf(client),
                    json={"age_group": "7-12", "settings": {}})
    assert r.status_code == 200, r.text
    body = client.get("/api/typing/bootstrap").json()
    assert body["profile"]["age_group"] == "7-12"
    # 非法年龄段 → 422
    assert client.post("/api/typing/profile", headers=scsrf(client),
                       json={"age_group": "99-99"}).status_code == 422


def test_profile_requires_csrf():
    client = _setup()
    assert client.post("/api/typing/profile", json={"age_group": "3-6"}).status_code == 403


def test_sessions_idempotent_global_uuid():
    client = _setup()
    item = _session("uuid-typing-1")
    r = client.post("/api/typing/sessions", headers=scsrf(client), json=[item, item])
    assert r.status_code == 200, r.text
    assert r.json() == {"inserted": 1, "skipped": 1}
    # 断网补送：同一 uuid 再发一次 → 全跳过
    r = client.post("/api/typing/sessions", headers=scsrf(client), json=[item])
    assert r.json() == {"inserted": 0, "skipped": 1}
    body = client.get("/api/typing/bootstrap").json()
    assert body["stats"]["total_sections"] == 1


def test_sessions_batch_limit():
    client = _setup()
    items = [_session(f"uuid-batch-{i}") for i in range(51)]
    assert client.post("/api/typing/sessions", headers=scsrf(client), json=items).status_code == 422


def test_audio_validates_word():
    client = _setup()
    # 缺 word / 超长 → 422（不触网）
    assert client.get("/api/typing/audio").status_code == 422
    assert client.get("/api/typing/audio", params={"word": "a" * 100}).status_code == 422


def test_audio_guest_accessible(monkeypatch):
    """游客（未登录）也能发音：audio 不鉴权，且 502/200 都算"端点活着"。"""
    import httpx
    from fastapi.testclient import TestClient

    class FakeResp:
        status_code = 200
        headers = {"content-length": "8"}

        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def iter_bytes(self): yield b"fake-mp3"

    monkeypatch.setattr(httpx.Client, "stream", lambda *_args, **_kwargs: FakeResp())
    root = Path(tempfile.mkdtemp())
    app = build_app(root)
    app.state.settings.typing_audio_cache_root = str(root / "audio")
    guest = TestClient(app)
    r = guest.get("/api/typing/audio", params={"word": "apple"})
    assert r.status_code == 200
    assert r.content == b"fake-mp3"


def test_audio_limits_upstream_size_and_removes_partial_file(monkeypatch, tmp_path):
    import httpx
    from fastapi.testclient import TestClient

    class LargeResp:
        status_code = 200
        headers = {}

        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def iter_bytes(self):
            yield b"12345678"
            yield b"overflow"

    monkeypatch.setattr(httpx.Client, "stream", lambda *_args, **_kwargs: LargeResp())
    app = build_app(tmp_path)
    cache = tmp_path / "audio"
    app.state.settings.typing_audio_cache_root = str(cache)
    app.state.settings.typing_audio_response_max_bytes = 16 * 1024
    # 绕过 Settings 的配置下限，直接用大于 16 KiB 的假响应验证实际流式上限。
    LargeResp.iter_bytes = lambda self: iter((b"a" * 12_000, b"b" * 12_000))
    r = TestClient(app).get("/api/typing/audio", params={"word": "oversized"})
    assert r.status_code == 502
    assert list(cache.glob("*")) == []


def test_audio_rate_limits_by_ip(monkeypatch, tmp_path):
    import httpx
    from fastapi.testclient import TestClient

    class FakeResp:
        status_code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def iter_bytes(self): yield b"mp3"

    monkeypatch.setattr(httpx.Client, "stream", lambda *_args, **_kwargs: FakeResp())
    app = build_app(tmp_path)
    app.state.settings.typing_audio_cache_root = str(tmp_path / "audio")
    app.state.settings.typing_audio_rate_limit_per_minute = 2
    guest = TestClient(app)
    assert guest.get("/api/typing/audio", params={"word": "one"}).status_code == 200
    assert guest.get("/api/typing/audio", params={"word": "one"}).status_code == 200
    assert guest.get("/api/typing/audio", params={"word": "one"}).status_code == 429


def test_audio_concurrent_same_word_fetches_once(monkeypatch, tmp_path):
    import httpx
    from fastapi.testclient import TestClient

    calls = 0
    calls_lock = threading.Lock()

    class SlowResp:
        status_code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def iter_bytes(self):
            time.sleep(0.05)
            yield b"same-mp3"

    def fake_stream(*_args, **_kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        return SlowResp()

    monkeypatch.setattr(httpx.Client, "stream", fake_stream)
    app = build_app(tmp_path)
    app.state.settings.typing_audio_cache_root = str(tmp_path / "audio")
    guest = TestClient(app)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(
            lambda _: guest.get("/api/typing/audio", params={"word": "concurrent"}),
            range(4),
        ))
    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert calls == 1


def test_audio_cache_prunes_oldest_files_for_quota(tmp_path):
    from app.routers.typing import _prune_audio_cache

    cache = tmp_path / "audio"
    cache.mkdir()
    oldest = cache / "oldest.mp3"
    middle = cache / "middle.mp3"
    newest = cache / "newest.mp3"
    for index, path in enumerate((oldest, middle, newest), start=1):
        path.write_bytes(b"x" * 10)
        os.utime(path, (index, index))

    _prune_audio_cache(cache, max_bytes=25, max_files=3, incoming_bytes=10)

    assert not oldest.exists()
    assert not middle.exists()
    assert newest.exists()
