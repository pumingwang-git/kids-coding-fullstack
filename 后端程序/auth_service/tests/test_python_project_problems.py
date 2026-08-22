"""Python 作品题（shape="project"）：迁移往返 + 形态互斥闸门 + 接口往返。

作品题是「画线、画气球」那一类：没有 stdin/stdout，判分靠 AST 声明式规则与教师量规。
它与算法题共用 `programming_details` 一张表，靠 `shape` 分家，因此这里最要紧的不是
"能存进去"，而是**两套判分依据不会并存**——一道题从作品改回算法之后，库里若还留着
上一版的规则和量规，"到底按哪套判"就没有任何一处代码能回答。
"""
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.models import Base
from test_admin_questions import admin_client, login, match, programming_payload

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "0059_exam_assignments"
SHAPE_REVISION = "0060_python_project_shape"
NEW_COLUMNS = ("shape", "starter_code", "allowed_modules", "rules_json", "rubric_json")


# ==================== 载荷构造 ====================


def project_payload(**overrides) -> dict:
    """一道最小可用的 Python 作品题：用循环画正六边形。"""
    programming = {
        "title": "画正六边形",
        "shape": "project",
        "pass_condition": "规则全通过",
        "hints": "想想 360 除以 6 是多少",
        "samples": [],
        "manual_test_cases": [],
        "ref_code": {
            "cpp": "",
            "python": "import turtle\nfor _ in range(6):\n    turtle.forward(100)\n    turtle.left(60)\n",
        },
        "starter_code": "import turtle\n\n# 在这里画出正六边形\n",
        "allowed_modules": ["turtle"],
        "rules": [
            {"type": "require_import", "module": "turtle"},
            {"type": "require_call_in_loop", "name": "forward", "label": "用循环画出每一条边"},
            {"type": "forbid_repeated_call", "name": "forward", "max_count": 2},
        ],
        "rubric": {},
    }
    programming.update(overrides)
    return {
        "type": "programming",
        "sub_type": "python",
        "common": {"difficulty": "入门", "source": "原创", "structure": "单项知识点",
                   "knowledge": ["模拟"], "stage": [], "business": []},
        "stem": "用 turtle 画一个正六边形，每条边 100 步。",
        "analysis": "",
        "options": [],
        "blanks": [],
        "programming": programming,
    }


def create(client: TestClient, headers: dict, payload: dict):
    return client.post("/api/admin/problems", headers=headers, json=payload)


# ==================== 迁移往返 ====================


@pytest.fixture
def migration_env(tmp_path, monkeypatch):
    """预置到 0059 的库形状：建完整表后把 0060 的五列摘掉，再 stamp 0059。

    两处坑照抄 `test_class_migration.py` 的注释：必须走 DATABASE_URL 环境变量并清
    `get_settings` 的 lru_cache（`alembic/env.py` 会覆盖 sqlalchemy.url）；整条迁移链
    在 SQLite 上跑不通，所以用 models 建库 + stamp，**只跑待测的这一条**（《40》§6）。
    """
    url = f"sqlite:///{tmp_path / 'shape.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    engine = sa.create_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for column in NEW_COLUMNS:
            conn.execute(sa.text(f"ALTER TABLE programming_details DROP COLUMN {column}"))
        # 一道存量算法题：迁移必须让它拿到取值，而不是留 NULL。
        conn.execute(sa.text(
            "INSERT INTO problems (id, type, sub_type, title, stem, analysis, difficulty,"
            " source, structure, status, version_no, revision)"
            " VALUES (1, 'programming', 'cpp', 'A+B', '', '', '入门', '洛谷', '单项知识点',"
            " 'approved', 1, 1)"))
        conn.execute(sa.text(
            "INSERT INTO programming_details (problem_id, input_format, output_format, hints,"
            " pass_condition, time_limit_ms, memory_limit_mb)"
            " VALUES (1, 'a b', 'a+b', '无', '全测试点通过', 1000, 256)"))
    engine.dispose()

    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    command.stamp(config, PREVIOUS_HEAD)
    try:
        yield config, url
    finally:
        get_settings.cache_clear()


def columns_of(url: str) -> dict:
    engine = sa.create_engine(url)
    try:
        return {c["name"]: c for c in sa.inspect(engine).get_columns("programming_details")}
    finally:
        engine.dispose()


def row_one(url: str) -> dict:
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            return dict(conn.execute(sa.text(
                "SELECT * FROM programming_details WHERE problem_id = 1")).mappings().one())
    finally:
        engine.dispose()


def test_upgrade_backfills_existing_rows_instead_of_leaving_null(migration_env):
    """存量行必须在同一条 ALTER 里拿到取值——否则回显路径得在每个出口写兜底。"""
    config, url = migration_env
    command.upgrade(config, SHAPE_REVISION)

    columns = columns_of(url)
    assert set(NEW_COLUMNS) <= set(columns)
    row = row_one(url)
    assert row["shape"] == "algorithm", "存量题必须落到算法题形态"
    assert row["starter_code"] == ""
    assert row["allowed_modules"] == "[]"
    assert row["rules_json"] == "[]"
    assert row["rubric_json"] == "{}"
    assert all(columns[name]["nullable"] is False for name in NEW_COLUMNS)


def test_downgrade_removes_columns_and_upgrade_stays_repeatable(migration_env):
    config, url = migration_env
    command.upgrade(config, SHAPE_REVISION)

    command.downgrade(config, PREVIOUS_HEAD)
    assert not (set(NEW_COLUMNS) & set(columns_of(url)))

    command.upgrade(config, SHAPE_REVISION)
    assert set(NEW_COLUMNS) <= set(columns_of(url))


# ==================== 接口往返 ====================


def test_project_problem_round_trips(tmp_path):
    client = admin_client(tmp_path)
    with client:
        headers = login(client)
        created = create(client, headers, project_payload())
        assert created.status_code == 201, created.text

        detail = client.get(
            f"/api/admin/problems/{created.json()['id']}", headers=headers
        ).json()["programming"]
        assert detail["shape"] == "project"
        assert detail["pass_condition"] == "规则全通过"
        assert detail["allowed_modules"] == ["turtle"]
        assert detail["starter_code"].startswith("import turtle")
        assert [r["type"] for r in detail["rules"]] == [
            "require_import", "require_call_in_loop", "forbid_repeated_call"]
        # label 是学生可见文案，随规则原样存回；参数不丢。
        assert detail["rules"][1]["label"] == "用循环画出每一条边"
        assert detail["rules"][2]["max_count"] == 2
        # 作品题不该凭空长出测试点。
        assert detail["samples"] == []
        assert detail["manual_test_cases"] == []


def test_shape_defaults_to_algorithm_when_omitted(tmp_path):
    """存量管理端不传 shape 时行为不变——这条迁移不能改既有录题链路的默认。"""
    client = admin_client(tmp_path)
    with client:
        headers = login(client)
        created = create(client, headers, programming_payload("cpp"))
        assert created.status_code == 201, created.text
        detail = client.get(
            f"/api/admin/problems/{created.json()['id']}", headers=headers
        ).json()["programming"]
        assert detail["shape"] == "algorithm"


def test_switching_back_to_algorithm_clears_project_assets(tmp_path):
    """形态改回算法题，规则/量规/初始代码必须一起清空。

    **这是本模块最要紧的一条**：两套判分依据并存时，没有任何一处代码能回答
    "到底按哪套判"。落库处那五列是无条件整体赋值，就是为了守住这里。
    """
    client = admin_client(tmp_path)
    with client:
        headers = login(client)
        created = create(client, headers, project_payload()).json()

        back = programming_payload("python", "全测试点通过")
        updated = client.put(f"/api/admin/problems/{created['id']}",
                             headers=match(headers, created["revision"]), json=back)
        assert updated.status_code == 200, updated.text

        detail = client.get(
            f"/api/admin/problems/{created['id']}", headers=headers
        ).json()["programming"]
        assert detail["shape"] == "algorithm"
        assert detail["rules"] == []
        assert detail["rubric"] == {}
        assert detail["starter_code"] == ""
        assert detail["allowed_modules"] == []


# ==================== 形态互斥闸门 ====================


@pytest.mark.parametrize("overrides, because", [
    ({"samples": [{"input": "1", "output": "1"}]}, "作品题没有 stdin/stdout，不该收样例"),
    ({"manual_test_cases": [{"input": "1", "output": "1"}]}, "同上，隐藏测试点也不收"),
    ({"input_format": "两个整数"}, "输入格式属于算法题"),
    ({"pass_condition": "全测试点通过"}, "跨形态的通过条件"),
    ({"rules": [{"type": "require_callz", "name": "forward"}]}, "规则类型拼错要写入即拒"),
    ({"allowed_modules": ["turtle.forward"]}, "白名单只收顶层模块名"),
], ids=["samples", "manual_cases", "input_format", "cross_pass_condition", "typo_rule", "bad_module"])
def test_project_rejects_algorithm_shaped_fields(tmp_path, overrides, because):
    client = admin_client(tmp_path)
    with client:
        headers = login(client)
        assert create(client, headers, project_payload(**overrides)).status_code == 422, because


def test_algorithm_rejects_project_fields(tmp_path):
    client = admin_client(tmp_path)
    with client:
        headers = login(client)
        payload = programming_payload("python")
        payload["programming"]["starter_code"] = "import turtle"
        assert create(client, headers, payload).status_code == 422


def test_project_shape_is_python_only(tmp_path):
    """C++ 没有对应的规则表，放开等于让题存进来却永远判不了。"""
    client = admin_client(tmp_path)
    with client:
        headers = login(client)
        payload = project_payload()
        payload["sub_type"] = "cpp"
        payload["programming"]["ref_code"] = {"cpp": "int main(){}", "python": ""}
        assert create(client, headers, payload).status_code == 422


def test_rubric_max_score_must_match_levels(tmp_path):
    """量规校验与 Scratch 共用 app/rubric.py，这条盯住它没被绕开。"""
    client = admin_client(tmp_path)
    with client:
        headers = login(client)
        rubric = {"max_score": 99, "criteria": [
            {"id": "c_shape", "label": "图形准确", "desc": "", "levels": [
                {"value": 1, "label": "达成", "points": 60, "desc": ""},
                {"value": 0, "label": "未达成", "points": 0, "desc": ""}]}]}
        assert create(client, headers, project_payload(rubric=rubric)).status_code == 422

        rubric["max_score"] = 60
        ok = create(client, headers, project_payload(rubric=rubric))
        assert ok.status_code == 201, ok.text
        detail = client.get(
            f"/api/admin/problems/{ok.json()['id']}", headers=headers
        ).json()["programming"]
        assert detail["rubric"]["max_score"] == 60
