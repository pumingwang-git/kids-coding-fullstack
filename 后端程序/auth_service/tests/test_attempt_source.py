"""作答来源抽象（X1）回归。

对应《16、paper_attempts 作答来源改造设计（X1）》第七节验收标准。

X1 的定位是**基础设施**：让 attempt 能挂在任意来源上，本次不接入任何新来源。
因此最重要的验收是「考试页行为零变化」——那条由 test_exam.py 79 条用例把关。
本文件补的是抽象层本身与表结构的性质：

- 适配器把 ExamLink 的七组能力一一映射到 AttemptSource；
- 唯一约束用不含可空列的复合键，NULL 空洞（评测报告 P0 风险 1）不存在；
- 不同 source_type 的相同 source_id 互不干扰；
- 迁移 0037 升降级双向可跑，四条数据保全断言生效。
"""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from test_exam import build_app, build_exam, start

from app.attempt_source import (
    SOURCE_EXAM_LINK,
    AttemptSource,
    attempt_scope,
    from_exam_link,
    resolve_by_exam_token,
    resolve_for_attempt,
)
from app.models import ExamLink, PaperAttempt

# ---------- 抽象层 ----------


def test_from_exam_link_maps_seven_capability_groups(tmp_path: Path):
    """七组能力逐条对齐 ExamLink，字段名照抄——适配器是纯搬运，不做语义转换。"""
    app = build_app(tmp_path)
    env = build_exam(tmp_path / "e", link={
        "attempt_limit": 3, "score_policy": "last", "duration_minutes": 45,
        "show_score": "after_close", "show_analysis": "never", "feedback_mode": "compile_only",
        "shuffle_questions": True, "shuffle_options": True,
    })
    db = env.app.state.session_factory()
    try:
        link = db.scalar(
            __import__("sqlalchemy").select(ExamLink).where(ExamLink.access_token == env.token)
        )
        source = from_exam_link(link)
    finally:
        db.close()

    assert source.source_type == SOURCE_EXAM_LINK
    assert source.source_id == link.id and source.paper_id == link.paper_id
    assert source.label == link.name and source.active is True
    assert source.legacy_exam_link_id == link.id and source.leaderboard_enabled is True
    # ① 时间窗 ② 时长 ③ 次数
    assert (source.open_at, source.close_at) == (link.open_at, link.close_at)
    assert source.duration_minutes == 45 and source.late_start_policy == link.late_start_policy
    assert source.attempt_limit == 3
    # ④ 计分 ⑤⑥⑦ 呈现
    assert source.score_policy == "last"
    assert source.show_score == "after_close"
    assert source.show_analysis == "never"
    assert source.feedback_mode == "compile_only"
    assert source.shuffle_questions is True and source.shuffle_options is True


def test_attempt_source_is_immutable(tmp_path: Path):
    """冻结 dataclass：exam.py 里这些字段只读几十次、从不写。写就该报错。"""
    env = build_exam(tmp_path)
    db = env.app.state.session_factory()
    try:
        source, _ = resolve_by_exam_token(db, env.token)
    finally:
        db.close()
    assert isinstance(source, AttemptSource)
    with pytest.raises(Exception):
        source.attempt_limit = 99


def test_resolve_for_attempt_round_trips(tmp_path: Path):
    """按 attempt 反查来源，拿回同一个 source。"""
    env = build_exam(tmp_path)
    attempt_id = start(env)
    db = env.app.state.session_factory()
    try:
        attempt = db.get(PaperAttempt, attempt_id)
        assert attempt.source_type == SOURCE_EXAM_LINK
        assert attempt.source_id == attempt.exam_link_id, "考试来源的冗余外键要与 source_id 一致"
        source, paper = resolve_for_attempt(db, attempt)
        assert source.source_id == attempt.source_id
        assert paper.id == attempt.paper_id
    finally:
        db.close()


def test_no_source_type_branch_outside_the_factory():
    """红线：除 attempt_source.resolve_for_attempt 外，全项目禁止 if source_type ==。

    散落的来源分支是这次改造唯一不可逆的技术债（计划评测报告第三条新纪律）。
    """
    # 只认**作答来源**的字面量。视频块也有个 source_type（platform/embed/direct），
    # 那是完全不同的概念，按裸字段名查会把它们全误报进来。
    root = Path(__file__).resolve().parents[1] / "app"
    literals = ('"exam_link"', "'exam_link'", '"lesson_homework"', "'lesson_homework'")
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "attempt_source.py":
            continue  # 工厂本身就是那唯一一处分派
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped.startswith(("if ", "elif ")):
                continue
            if "source_type" in stripped and any(lit in stripped for lit in literals):
                offenders.append(f"{path.relative_to(root)}:{lineno}  {stripped}")
    assert not offenders, "作答来源分支散落到了工厂之外：\n" + "\n".join(offenders)


# ---------- 唯一性：没有 NULL 空洞 ----------


def test_unique_key_has_no_nullable_column(tmp_path: Path):
    """唯一键 (source_type, source_id, user_id, attempt_no) 四列全部 NOT NULL。

    评测报告 P0 风险 1 担心的是「exam_link_id 改可空后 NULL 互不相等 → 非考试来源
    完全失去唯一性保护」。本设计把可空列从键里拿掉，那个坑根本不存在。
    """
    app = build_app(tmp_path)
    table = PaperAttempt.__table__
    uq = next(c for c in table.constraints if getattr(c, "name", "") == "uq_attempt_source")
    cols = [c.name for c in uq.columns]
    assert cols == ["source_type", "source_id", "user_id", "attempt_no"]
    for name in cols:
        assert table.c[name].nullable is False, f"{name} 可空，唯一键会出现 NULL 空洞"
    # exam_link_id 已退化为可空的冗余外键
    assert table.c["exam_link_id"].nullable is True


def test_same_source_duplicate_attempt_no_rejected(tmp_path: Path):
    """同一来源同一学员的 attempt_no 不可重复（并发开考的护栏）。"""
    env = build_exam(tmp_path)
    attempt_id = start(env)
    db = env.app.state.session_factory()
    try:
        origin = db.get(PaperAttempt, attempt_id)
        db.add(PaperAttempt(
            source_type=origin.source_type, source_id=origin.source_id,
            exam_link_id=origin.exam_link_id, paper_id=origin.paper_id,
            user_id=origin.user_id, attempt_no=origin.attempt_no,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_different_source_types_may_share_source_id(tmp_path: Path):
    """不同来源的相同 source_id 互不干扰——否则课时块 id 会和考试链接 id 撞。"""
    env = build_exam(tmp_path)
    attempt_id = start(env)
    db = env.app.state.session_factory()
    try:
        origin = db.get(PaperAttempt, attempt_id)
        db.add(PaperAttempt(
            source_type="lesson_homework",       # 只换来源类型
            source_id=origin.source_id,          # 故意用同一个 id
            exam_link_id=None,                   # 非考试来源没有链接
            paper_id=origin.paper_id, user_id=origin.user_id,
            attempt_no=origin.attempt_no,
        ))
        db.commit()  # 不该冲突
        rows = db.query(PaperAttempt).filter_by(source_id=origin.source_id).count()
        assert rows == 2
    finally:
        db.close()


def test_attempt_scope_filters_by_source(tmp_path: Path):
    """attempt_scope 只圈本来源的作答，不会把同 id 的其它来源捞进来。"""
    env = build_exam(tmp_path)
    attempt_id = start(env)
    db = env.app.state.session_factory()
    try:
        origin = db.get(PaperAttempt, attempt_id)
        db.add(PaperAttempt(
            source_type="lesson_homework", source_id=origin.source_id, exam_link_id=None,
            paper_id=origin.paper_id, user_id=origin.user_id, attempt_no=1,
        ))
        db.commit()
        source, _ = resolve_for_attempt(db, origin)
        scoped = db.query(PaperAttempt).filter(*attempt_scope(source)).all()
        assert [a.id for a in scoped] == [origin.id]
    finally:
        db.close()


# ---------- 迁移 0037 ----------


def _load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0037_attempt_source.py"
    spec = importlib.util.spec_from_file_location("m0037_attempt_source", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_schema(conn):
    """0036 之后、0037 之前的 paper_attempts（exam_link_id NOT NULL + 旧唯一约束）。"""
    conn.exec_driver_sql("""
        CREATE TABLE paper_attempts (
            id INTEGER PRIMARY KEY,
            exam_link_id INTEGER NOT NULL,
            paper_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            attempt_no INTEGER NOT NULL DEFAULT 1,
            started_at TIMESTAMP,
            deadline_at TIMESTAMP,
            submitted_at TIMESTAMP,
            submit_kind VARCHAR(16),
            shuffle_seed INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            penalty_minutes INTEGER DEFAULT 0,
            status VARCHAR(16) DEFAULT 'ongoing',
            duration_seconds INTEGER,
            ip_hmac VARCHAR(128),
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_paper_attempts UNIQUE (exam_link_id, user_id, attempt_no)
        )
    """)
    conn.exec_driver_sql(
        "INSERT INTO paper_attempts (id, exam_link_id, paper_id, user_id, attempt_no, total_score)"
        " VALUES (1, 7, 3, 11, 1, 88), (2, 7, 3, 12, 1, 60), (3, 9, 3, 11, 1, 0)"
    )


def test_migration_0037_upgrade_backfills_and_preserves_data(tmp_path: Path):
    """升级：回填 source_id=exam_link_id，四条数据保全断言通过，行数与总分不变。"""
    module = _load_migration()
    engine = create_engine(f"sqlite:///{tmp_path / 'm37.db'}")
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with engine.begin() as conn:
        _legacy_schema(conn)
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()

        rows = conn.exec_driver_sql(
            "SELECT id, source_type, source_id, exam_link_id, total_score"
            " FROM paper_attempts ORDER BY id"
        ).all()
        assert len(rows) == 3, "行数不能变"
        assert sum(r[4] for r in rows) == 148, "总分不能变"
        for r in rows:
            assert r[1] == "exam_link"
            assert r[2] == r[3], "source_id 必须等于 exam_link_id"

        cols = {c[1]: c for c in conn.exec_driver_sql("PRAGMA table_info(paper_attempts)").all()}
        assert cols["exam_link_id"][3] == 0, "exam_link_id 应已改为可空"
        assert cols["source_type"][3] == 1 and cols["source_id"][3] == 1, "来源两列必须 NOT NULL"

        # 断言唯一约束的**行为**而不是索引名：SQLite 整表重建后表级 UNIQUE 会落成
        # 匿名的 sqlite_autoindex_*，名字对不上不代表约束没建。
        conn.exec_driver_sql(
            "INSERT INTO paper_attempts (id, source_type, source_id, exam_link_id,"
            " paper_id, user_id, attempt_no) VALUES (90, 'exam_link', 7, 7, 3, 11, 9)"
        )
        with pytest.raises(Exception):
            conn.exec_driver_sql(
                "INSERT INTO paper_attempts (id, source_type, source_id, exam_link_id,"
                " paper_id, user_id, attempt_no) VALUES (91, 'exam_link', 7, 7, 3, 11, 9)"
            )


def test_migration_0037_downgrade_restores_and_refuses_when_unsafe(tmp_path: Path):
    """降级：纯考试数据可还原；存在非考试来源的作答时**拒绝降级**而不是丢数据。"""
    module = _load_migration()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    # 情形 A：只有考试来源 → 可降级
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    with engine.begin() as conn:
        _legacy_schema(conn)
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
            module.downgrade()
        cols = {c[1] for c in conn.exec_driver_sql("PRAGMA table_info(paper_attempts)").all()}
        assert "source_type" not in cols and "source_id" not in cols
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM paper_attempts").scalar() == 3

    # 情形 B：混入课时来源 → 必须拒绝
    engine_b = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    with engine_b.begin() as conn:
        _legacy_schema(conn)
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        conn.exec_driver_sql(
            "INSERT INTO paper_attempts (id, source_type, source_id, exam_link_id,"
            " paper_id, user_id, attempt_no) VALUES (4, 'lesson_homework', 5, NULL, 3, 11, 1)"
        )
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError, match="无法降级"):
                module.downgrade()
