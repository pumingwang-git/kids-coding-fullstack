"""group legacy help requests into durable class chat lines

⚠️ 这条迁移之后还跟着三条补丁，读到这里的人先看一眼再动手：

    0079_restore_help_answered_at      补回 help_requests.answered_at
    0080_restore_help_assign_rev       补回 help_requests.assignment_revision
    0082_help_status_checks            补回 answered 相关的两条 CHECK

它们是本迁移重建 help_requests 时丢列/丢约束留下的账，全部用 `sa.inspect` 做成
条件式、可重复执行。**不要"顺手"把它们折叠回本文件**：本文件是 304 行的数据迁移，
带三处方言分支和重复键检测，为了链子好看去改一条已经跑通的迁移不划算
（2026-08-31 裁决，见《68》§6 L7）。要动它们，先确认目标库的 alembic_version。
"""

from collections import defaultdict
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "0075_help_request_grouping"
down_revision = "0074_help_chat_realtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    legacy_rows = (
        bind.execute(
            sa.text(
                "SELECT id, class_id, student_id, body, context_type, context_id, created_at "
                "FROM help_requests ORDER BY id"
            )
        )
        .mappings()
        .all()
    )

    normalized: dict[int, tuple[str | None, str]] = {}
    grouped_ids: dict[tuple[int, int, str], list[int]] = defaultdict(list)
    for row in legacy_rows:
        source, key = _legacy_context(bind, row)
        normalized[row["id"]] = (source, key)
        grouped_ids[(row["class_id"], row["student_id"], key)].append(row["id"])
    duplicates = [ids for ids in grouped_ids.values() if len(ids) > 1]
    if duplicates:
        rendered = ", ".join("[" + ", ".join(map(str, ids)) + "]" for ids in duplicates)
        raise RuntimeError(f"0075 duplicate help context rows require manual repair: {rendered}")

    grouping_columns = (
        sa.Column("chat_line_id", sa.Integer(), nullable=True),
        sa.Column("context_source", sa.String(length=32), nullable=True),
        sa.Column("context_key", sa.String(length=255), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    if bind.dialect.name == "postgresql":
        for column in grouping_columns:
            op.add_column("help_requests", column)
    else:
        with op.batch_alter_table("help_requests", recreate="auto") as batch:
            for column in grouping_columns:
                batch.add_column(column)

    line_ids: dict[tuple[int, int], int] = {}
    line_table = sa.table(
        "help_chat_lines",
        sa.column("id", sa.Integer()),
        sa.column("class_id", sa.Integer()),
        sa.column("student_id", sa.Integer()),
        sa.column("last_message_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    for row in legacy_rows:
        pair = (row["class_id"], row["student_id"])
        if pair not in line_ids:
            created_at = row["created_at"]
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            line_ids[pair] = bind.execute(
                sa.insert(line_table)
                .values(
                    class_id=row["class_id"],
                    student_id=row["student_id"],
                    last_message_at=created_at,
                    created_at=created_at,
                )
                .returning(line_table.c.id)
            ).scalar_one()
        source, key = normalized[row["id"]]
        has_message = bind.scalar(
            sa.text("SELECT count(*) FROM help_messages WHERE help_request_id=:request_id"),
            {"request_id": row["id"]},
        )
        if not has_message:
            bind.execute(
                sa.text(
                    "INSERT INTO help_messages "
                    "(help_request_id, sender_user_id, body, request_key_hash, request_hash, created_at) "
                    "VALUES (:request_id, :student_id, :body, :key_hash, :request_hash, :created_at)"
                ),
                {
                    "request_id": row["id"],
                    "student_id": row["student_id"],
                    "body": row["body"],
                    "key_hash": f"legacy-first:{row['id']}",
                    "request_hash": f"legacy-first:{row['id']}",
                    "created_at": row["created_at"],
                },
            )
        latest_message_at = bind.scalar(
            sa.text("SELECT max(created_at) FROM help_messages WHERE help_request_id=:request_id"),
            {"request_id": row["id"]},
        )
        bind.execute(
            sa.text(
                "UPDATE help_requests SET chat_line_id=:line_id, context_source=:source, "
                "context_key=:context_key, last_message_at=:last_message_at WHERE id=:request_id"
            ),
            {
                "line_id": line_ids[pair],
                "source": source,
                "context_key": key,
                "last_message_at": latest_message_at or row["created_at"],
                "request_id": row["id"],
            },
        )

    for (class_id, student_id), line_id in line_ids.items():
        bind.execute(
            sa.text(
                "UPDATE help_chat_lines SET last_message_at=("
                "SELECT max(last_message_at) FROM help_requests WHERE chat_line_id=:line_id"
                ") WHERE id=:line_id"
            ),
            {"line_id": line_id},
        )

    naming = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    if bind.dialect.name == "postgresql":
        # PostgreSQL can alter these columns in place. Recreating help_requests would
        # first drop its primary key, which is still referenced by help_messages.
        op.alter_column("help_requests", "chat_line_id", existing_type=sa.Integer(), nullable=False)
        op.alter_column(
            "help_requests",
            "context_key",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        op.alter_column(
            "help_requests",
            "last_message_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        op.create_foreign_key(
            "fk_help_requests_chat_line_id_help_chat_lines",
            "help_requests",
            "help_chat_lines",
            ["chat_line_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_unique_constraint(
            "uq_help_requests_line_context",
            "help_requests",
            ["chat_line_id", "context_key"],
        )
    else:
        with op.batch_alter_table(
            "help_requests",
            recreate="always",
            naming_convention=naming,
        ) as batch:
            batch.alter_column("chat_line_id", existing_type=sa.Integer(), nullable=False)
            batch.alter_column("context_key", existing_type=sa.String(length=255), nullable=False)
            batch.alter_column(
                "last_message_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )
            batch.create_foreign_key(
                "fk_help_requests_chat_line_id_help_chat_lines",
                "help_chat_lines",
                ["chat_line_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch.create_unique_constraint(
                "uq_help_requests_line_context",
                ["chat_line_id", "context_key"],
            )
    for column in ("chat_line_id", "last_message_at"):
        op.create_index(f"ix_help_requests_{column}", "help_requests", [column])

    inspector = sa.inspect(bind)
    message_fk = next(
        (
            fk
            for fk in inspector.get_foreign_keys("help_messages")
            if fk["constrained_columns"] == ["help_request_id"]
        ),
        None,
    )
    fk_name = (message_fk or {}).get("name") or "fk_help_messages_help_request_id_help_requests"
    if bind.dialect.name == "postgresql":
        if message_fk is not None:
            op.drop_constraint(fk_name, "help_messages", type_="foreignkey")
        op.create_foreign_key(
            "fk_help_messages_help_request_id_help_requests",
            "help_messages",
            "help_requests",
            ["help_request_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_unique_constraint(
            "uq_help_messages_student_key",
            "help_messages",
            ["help_request_id", "sender_user_id", "request_key_hash"],
        )
    else:
        with op.batch_alter_table(
            "help_messages",
            recreate="always",
            naming_convention=naming,
        ) as batch:
            if message_fk is not None:
                batch.drop_constraint(fk_name, type_="foreignkey")
            batch.create_foreign_key(
                "fk_help_messages_help_request_id_help_requests",
                "help_requests",
                ["help_request_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch.create_unique_constraint(
                "uq_help_messages_student_key",
                ["help_request_id", "sender_user_id", "request_key_hash"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM help_requests")) or bind.scalar(
        sa.text("SELECT count(*) FROM help_messages")
    ):
        raise RuntimeError("0075 downgrade refused: help request history is not empty")

    naming = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    with op.batch_alter_table(
        "help_messages",
        recreate="always",
        naming_convention=naming,
    ) as batch:
        batch.drop_constraint("uq_help_messages_student_key", type_="unique")
        batch.drop_constraint(
            "fk_help_messages_help_request_id_help_requests",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_help_messages_help_request_id_help_requests",
            "help_requests",
            ["help_request_id"],
            ["id"],
            ondelete="CASCADE",
        )
    for column in ("last_message_at", "chat_line_id"):
        op.drop_index(f"ix_help_requests_{column}", table_name="help_requests")
    with op.batch_alter_table(
        "help_requests",
        recreate="always",
        naming_convention=naming,
    ) as batch:
        batch.drop_constraint("uq_help_requests_line_context", type_="unique")
        batch.drop_constraint(
            "fk_help_requests_chat_line_id_help_chat_lines",
            type_="foreignkey",
        )
        for column in ("last_message_at", "context_key", "context_source", "chat_line_id"):
            batch.drop_column(column)


def _legacy_context(bind, row) -> tuple[str | None, str]:
    context_type = row["context_type"]
    context_id = row["context_id"]
    if context_type == "general" and context_id is None:
        return None, "general"
    if context_type in {"course", "lesson"} and context_id is not None:
        return None, f"{context_type}:{context_id}"
    if context_type == "block" and context_id is not None:
        return None, f"lesson_block:{context_id}"
    if context_type == "problem" and context_id is not None:
        problem_number = bind.scalar(
            sa.text("SELECT problem_id_no FROM problems WHERE id=:context_id"),
            {"context_id": context_id},
        )
        if problem_number:
            return None, f"lesson_problem:{problem_number}"
    if context_type == "attempt" and context_id is not None:
        problem_numbers = (
            bind.execute(
                sa.text(
                    "SELECT DISTINCT lpb.problem_id_no FROM lesson_problem_attempts lpa "
                    "JOIN lesson_problem_blocks lpb ON lpb.block_id=lpa.block_id "
                    "WHERE lpa.id=:context_id"
                ),
                {"context_id": context_id},
            )
            .scalars()
            .all()
        )
        if len(problem_numbers) == 1:
            return "lesson_attempt", f"attempt:lesson_attempt:{context_id}:{problem_numbers[0]}"
    raise RuntimeError(f"0075 cannot normalize help_request id={row['id']}")
