"""课中练习单题化（v2）：新表 lesson_problem_blocks CRUD + 迁移 0033 验证。

对应《课中练习重构-实现计划-v2-2026-08-10》§8.1（S1/S2）与 §9.1：
- 迁移 0033：建表（字段/索引）、存量 practice→homework 改写（含无明细脏数据块，
  Q6 已定）、due_at 保持 NULL（Q4）、downgrade 可回滚（drop 新表 + 逆 UPDATE）；
- practice 块 CRUD：绑题正例（problem_type 服务端回填、shuffle_options 默认 True）、
  题目不存在/未 approved → 400、practice 传 paper → 400；
- homework 块回归：绑卷保持现状、homework 传 problem → 400；
- PUT 双分支：换题 / 换卷全量覆盖；删块级联清明细（FK CASCADE）。
"""
import importlib.util
from pathlib import Path

from test_admin_courses import add_section, create_category, create_course
from test_exam import admin_login, build_app

from app.models import LessonPaperBlock, LessonProblemBlock, Paper, Problem

# 0033 之前的 0032-era 最小表结构（只含 0033 会触碰的表/列；用原生 DDL 模拟存量库）。
# SQLite 驱动不支持一次 execute 多条语句，按条拆分执行。
_MINIMAL_SCHEMA_STATEMENTS = [
    "CREATE TABLE course_lessons (id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL)",
    "CREATE TABLE papers (id INTEGER PRIMARY KEY, title TEXT NOT NULL)",
    """CREATE TABLE course_lesson_blocks (
        id INTEGER PRIMARY KEY,
        lesson_id INTEGER NOT NULL,
        block_type VARCHAR(16) NOT NULL,
        title VARCHAR(200) NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        required BOOLEAN NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE lesson_paper_blocks (
        block_id INTEGER PRIMARY KEY REFERENCES course_lesson_blocks(id) ON DELETE CASCADE,
        paper_id INTEGER NOT NULL REFERENCES papers(id),
        mode VARCHAR(16) NOT NULL DEFAULT 'practice',
        attempt_limit INTEGER,
        shuffle_questions BOOLEAN NOT NULL DEFAULT 1,
        shuffle_options BOOLEAN NOT NULL DEFAULT 1,
        show_score BOOLEAN NOT NULL DEFAULT 1,
        show_analysis BOOLEAN NOT NULL DEFAULT 1,
        due_at DATETIME,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
]


def _load_migration_0033():
    """0033 迁移文件以数字开头，不能用常规 import；走 importlib。"""
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0033_lesson_problem_blocks.py"
    spec = importlib.util.spec_from_file_location("m0033_lesson_problem_blocks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration_engine(tmp_path: Path):
    from sqlalchemy import create_engine, event

    engine = create_engine(f"sqlite:///{tmp_path / 'migration_0033.db'}")
    # 与 build_database 同口径：打开外键校验，验证新表 FK 建得对。
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _run_with_operations(engine, fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        fn(Operations(ctx), conn)


def _seed_0032_practice_data(conn) -> None:
    """插入存量 practice 数据：1 条有明细 + 1 条无明细脏数据块 + 1 条已有 homework。"""
    conn.exec_driver_sql("INSERT INTO course_lessons (id, title) VALUES (1, '课时A'), (2, '课时B')")
    conn.exec_driver_sql("INSERT INTO papers (id, title) VALUES (1, '存量卷1')")
    conn.exec_driver_sql(
        "INSERT INTO course_lesson_blocks (id, lesson_id, block_type, title, sort_order, required) VALUES "
        "(1, 1, 'practice', '课中练习1', 0, 1), "
        "(2, 1, 'homework', '已有课后作业', 1, 1), "
        "(3, 2, 'practice', '脏数据练习', 0, 1)"
    )
    # 块 1 有明细：mode=practice，due_at=NULL（练习块必须为空，models.py:832 口径）
    conn.exec_driver_sql(
        "INSERT INTO lesson_paper_blocks "
        "(block_id, paper_id, mode, attempt_limit, shuffle_questions, shuffle_options, show_score, show_analysis, due_at) "
        "VALUES (1, 1, 'practice', 2, 1, 1, 1, 1, NULL)"
    )
    # 块 3 无明细（历史脏数据，Q6 已定一并改写）


# ---------- 迁移 0033 ----------


def test_migration_0033_upgrade_rewrites_practice_to_homework(tmp_path: Path):
    """upgrade：建新表 + 存量 practice→homework（含无明细脏数据块）+ due_at 保持 NULL。"""
    m0033 = _load_migration_0033()
    engine = _migration_engine(tmp_path)
    try:
        with engine.begin() as conn:
            for statement in _MINIMAL_SCHEMA_STATEMENTS:
                conn.exec_driver_sql(statement)
            _seed_0032_practice_data(conn)
            _run_migration_inline(conn, m0033.upgrade)
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT id, block_type FROM course_lesson_blocks ORDER BY id"
            ).all()
            assert rows == [(1, "homework"), (2, "homework"), (3, "homework")]
            modes = conn.exec_driver_sql(
                "SELECT block_id, mode FROM lesson_paper_blocks ORDER BY block_id"
            ).all()
            assert modes == [(1, "homework")]
            due = conn.exec_driver_sql(
                "SELECT due_at FROM lesson_paper_blocks WHERE block_id = 1"
            ).scalar_one()
            assert due is None  # Q4：保持 NULL 不限时，不凭空造截止时间
            cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(lesson_problem_blocks)").all()}
            assert {
                "block_id", "problem_id_no", "problem_type", "display_no", "score",
                "attempt_limit", "shuffle_options", "show_analysis", "created_at", "updated_at",
            } <= cols
            indexes = {row[1] for row in conn.exec_driver_sql(
                "PRAGMA index_list(lesson_problem_blocks)").all()}
            assert "ix_lesson_problem_blocks_problem_id_no" in indexes
            assert "ix_lesson_problem_blocks_problem_type" in indexes
            # 备份表：被改写块清单落盘（全配置字段），撑起 downgrade 无损还原与对账存档
            backup = {row[0]: row for row in conn.exec_driver_sql(
                "SELECT block_id, lesson_id, title, paper_id, mode, attempt_limit, due_at "
                "FROM _mig0033_rewritten_blocks ORDER BY block_id").all()}
            assert set(backup) == {1, 3}  # 仅被改写的 practice 块（块 2 是迁移前已有 homework，不落盘）
            assert backup[1] == (1, 1, "课中练习1", 1, "practice", 2, None)  # 原始 mode 存档
            assert backup[3][3] is None and backup[3][4] is None  # 无明细脏数据块：LEFT JOIN 全 NULL
    finally:
        engine.dispose()


def _run_migration_inline(conn, fn) -> None:
    """在给定连接上以 Alembic Operations 上下文执行迁移函数（upgrade/downgrade）。

    迁移函数内部 `from alembic import op` 走的是模块级代理：必须用
    `Operations.context()` 把当前 Operations 装成全局代理，直接传参调用会报
    「takes 0 positional arguments」。
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        fn()


def test_migration_0033_downgrade_restores_only_backedup_blocks(tmp_path: Path):
    """downgrade（备份表无损路径）：只还原备份清单内的块，不误伤迁移前已有 / 迁移后新建的 homework。"""
    m0033 = _load_migration_0033()
    engine = _migration_engine(tmp_path)
    try:
        with engine.begin() as conn:
            for statement in _MINIMAL_SCHEMA_STATEMENTS:
                conn.exec_driver_sql(statement)
            _seed_0032_practice_data(conn)
            _run_migration_inline(conn, m0033.upgrade)
            # 迁移后老师新建的 homework（块 4）：不在备份清单内，downgrade 不得改动
            conn.exec_driver_sql(
                "INSERT INTO course_lesson_blocks (id, lesson_id, block_type, title, sort_order, required) "
                "VALUES (4, 2, 'homework', '迁移后新建作业', 1, 1)"
            )
        with engine.begin() as conn:
            _run_migration_inline(conn, m0033.downgrade)
        with engine.connect() as conn:
            tables = {row[0] for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'").all()}
            assert "lesson_problem_blocks" not in tables
            assert "_mig0033_rewritten_blocks" not in tables  # 备份表随 downgrade 清理
            rows = conn.exec_driver_sql(
                "SELECT id, block_type FROM course_lesson_blocks ORDER BY id"
            ).all()
            # 无损还原：存量 practice（1/3）还原为 practice；块 2（迁移前已有 homework）
            # 与块 4（迁移后新建 homework）均保持 homework——不再被全量逆 UPDATE 误伤。
            assert rows == [(1, "practice"), (2, "homework"), (3, "practice"), (4, "homework")]
            modes = conn.exec_driver_sql(
                "SELECT block_id, mode FROM lesson_paper_blocks ORDER BY block_id"
            ).all()
            assert modes == [(1, "practice")]
    finally:
        engine.dispose()


def test_migration_0033_downgrade_fallback_when_backup_missing(tmp_path: Path):
    """downgrade 退化路径：备份表缺失时全量逆 UPDATE + 告警（保持旧版行为，可回滚老库）。"""
    m0033 = _load_migration_0033()
    engine = _migration_engine(tmp_path)
    try:
        with engine.begin() as conn:
            for statement in _MINIMAL_SCHEMA_STATEMENTS:
                conn.exec_driver_sql(statement)
            _seed_0032_practice_data(conn)
            _run_migration_inline(conn, m0033.upgrade)
            conn.exec_driver_sql("DROP TABLE _mig0033_rewritten_blocks")
        with engine.begin() as conn:
            _run_migration_inline(conn, m0033.downgrade)
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT id, block_type FROM course_lesson_blocks ORDER BY id"
            ).all()
            # 有损：块 2（迁移前已有 homework）也被全量逆 UPDATE 改回 practice
            assert rows == [(1, "practice"), (2, "practice"), (3, "practice")]
    finally:
        engine.dispose()


# ---------- 新表 CRUD（API 链路） ----------


def seed_problem(app, *, status: str = "approved", type: str = "choice",
                 problem_id_no: str = "Q100001", stem: str = "题面") -> dict:
    """直接落一道题（approved 用于绑题正例；draft 用于负例）。"""
    db = app.state.session_factory()
    try:
        p = Problem(type=type, title="题", stem=stem, status=status,
                    problem_id_no=problem_id_no, version_no=1, revision=1)
        db.add(p)
        db.flush()
        p.root_problem_id = p.id
        db.commit()
        return {"problem_id": p.id, "problem_id_no": p.problem_id_no, "type": p.type}
    finally:
        db.close()


def seed_paper(app, *, title: str = "作业卷A", status: str = "published") -> dict:
    db = app.state.session_factory()
    try:
        paper = Paper(title=title, status=status, paper_type="作业卷", subject="cpp")
        db.add(paper)
        db.commit()
        return {"paper_id": paper.id}
    finally:
        db.close()


def build_lesson(app):
    """建分类→课包→章节→无内容课时，返回 (client, headers, lesson_id)。"""
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时 1", "duration_minutes": 30}).json()
    return client, headers, lesson["id"]


def problem_block_payload(**detail) -> dict:
    body = {"block_type": "practice", "title": "课中练习", "detail": {"problem": detail}}
    return body


def paper_block_payload(**detail) -> dict:
    body = {"block_type": "homework", "title": "课后练习", "detail": {"paper": detail}}
    return body


def test_practice_block_bind_problem_positive(tmp_path: Path):
    """POST practice 带 problem：建块成功，problem_type 服务端回填、shuffle_options 默认 True。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    no = seed_problem(app)["problem_id_no"]
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=problem_block_payload(problem_id_no=no, display_no="1", score=10)).json()
    assert b["block_type"] == "practice"
    assert b["problem"]["problem_id_no"] == no
    assert b["problem"]["problem_type"] == "choice"          # 服务端从 problems.type 回填
    assert b["problem"]["display_no"] == "1"
    assert b["problem"]["score"] == 10
    assert b["problem"]["shuffle_options"] is True           # 默认 True（未传）
    assert b["problem"]["show_analysis"] is True
    assert b["problem"]["attempt_limit"] is None

    # GET 列表：practice 块返回 problem 明细
    data = client.get(f"/api/admin/lessons/{lid}/blocks", headers=headers).json()
    assert data["blocks"][0]["problem"]["problem_id_no"] == no


def test_practice_block_rejects_missing_or_unapproved_problem(tmp_path: Path):
    """POST practice 绑不存在的题 / 未审核通过的题 → 400。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    # 题目不存在
    resp = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=problem_block_payload(problem_id_no="Q999999"))
    assert resp.status_code == 400 and "不存在或未审核通过" in resp.json()["detail"]
    # 题目存在但未 approved（draft）
    no = seed_problem(app, status="draft")["problem_id_no"]
    resp = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=problem_block_payload(problem_id_no=no))
    assert resp.status_code == 400 and "不存在或未审核通过" in resp.json()["detail"]


def test_practice_block_rejects_paper_payload(tmp_path: Path):
    """新建 practice 传 paper → 400「课中练习块请绑定题目」（v2 双分支兼容保护）。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    paper = seed_paper(app)
    resp = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json={"block_type": "practice", "title": "p",
                             "detail": {"paper": {"paper_id": paper["paper_id"], "mode": "practice"}}})
    assert resp.status_code == 400
    assert "课中练习块请绑定题目" in resp.json()["detail"]


def test_homework_block_bind_paper_regression(tmp_path: Path):
    """POST homework 带 paper：保持现状（绑卷 + 投放规则），GET 返回 paper 明细。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    paper = seed_paper(app)
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=paper_block_payload(paper_id=paper["paper_id"], mode="homework",
                                             attempt_limit=2, due_at=None)).json()
    assert b["block_type"] == "homework"
    assert b["paper"]["paper_id"] == paper["paper_id"]
    assert b["paper"]["mode"] == "homework"
    assert b["paper"]["attempt_limit"] == 2
    assert b["paper"]["due_at"] is None


def test_homework_block_rejects_problem_payload(tmp_path: Path):
    """homework 传 problem → 400「课后练习块请绑定试卷」。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    no = seed_problem(app)["problem_id_no"]
    resp = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json={"block_type": "homework", "title": "h",
                             "detail": {"problem": {"problem_id_no": no}}})
    assert resp.status_code == 400
    assert "课后练习块请绑定试卷" in resp.json()["detail"]


def test_put_practice_swap_problem_full_overwrite(tmp_path: Path):
    """PUT practice：换题全量覆盖明细；块类型仍不可改。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    no1 = seed_problem(app, problem_id_no="Q100010")["problem_id_no"]
    no2 = seed_problem(app, problem_id_no="Q100011", type="judge")["problem_id_no"]
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=problem_block_payload(problem_id_no=no1, display_no="1", score=10)).json()
    # 换题：display_no/score 一并覆盖
    up = client.put(f"/api/admin/lesson-blocks/{b['id']}", headers=headers,
                    json=problem_block_payload(problem_id_no=no2, display_no="2", score=20,
                                               attempt_limit=0)).json()
    assert up["problem"]["problem_id_no"] == no2
    assert up["problem"]["problem_type"] == "judge"          # 快照跟随新题回填
    assert up["problem"]["display_no"] == "2"
    assert up["problem"]["score"] == 20
    assert up["problem"]["attempt_limit"] is None            # 0 → NULL 转换
    db = app.state.session_factory()
    try:
        assert db.scalar(__import__("sqlalchemy").select(LessonProblemBlock).where(
            LessonProblemBlock.block_id == b["id"]).limit(1)) is not None
        assert db.scalar(__import__("sqlalchemy").select(LessonPaperBlock).where(
            LessonPaperBlock.block_id == b["id"]).limit(1)) is None  # 未误写 paper 明细
    finally:
        db.close()
    # 块类型不可改
    resp = client.put(f"/api/admin/lesson-blocks/{b['id']}", headers=headers,
                      json=paper_block_payload(paper_id=seed_paper(app)["paper_id"], mode="homework"))
    assert resp.status_code == 400


def test_put_homework_swap_paper_regression(tmp_path: Path):
    """PUT homework：换卷全量覆盖，保持现状。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    p1 = seed_paper(app, title="卷1")
    p2 = seed_paper(app, title="卷2")
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=paper_block_payload(paper_id=p1["paper_id"], mode="homework")).json()
    up = client.put(f"/api/admin/lesson-blocks/{b['id']}", headers=headers,
                    json=paper_block_payload(paper_id=p2["paper_id"], mode="homework",
                                             attempt_limit=3, shuffle_questions=False)).json()
    assert up["paper"]["paper_id"] == p2["paper_id"]
    assert up["paper"]["attempt_limit"] == 3
    assert up["paper"]["shuffle_questions"] is False


def test_delete_block_cascades_problem_detail(tmp_path: Path):
    """删块即清明细：FK ondelete=CASCADE（实现计划 v2 §3.1 说明 5）。"""
    app = build_app(tmp_path)
    client, headers, lid = build_lesson(app)
    no = seed_problem(app)["problem_id_no"]
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=problem_block_payload(problem_id_no=no)).json()
    db = app.state.session_factory()
    try:
        assert db.get(LessonProblemBlock, b["id"]) is not None
    finally:
        db.close()
    assert client.delete(f"/api/admin/lesson-blocks/{b['id']}", headers=headers).status_code == 200
    db = app.state.session_factory()
    try:
        assert db.get(LessonProblemBlock, b["id"]) is None
    finally:
        db.close()
