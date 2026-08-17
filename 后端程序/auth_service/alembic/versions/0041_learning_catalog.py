"""add data-driven learning catalog

Revision ID: 0041_learning_catalog
Revises: 0040_course_area_kind
Create Date: 2026-08-13

新增专区、工作台模块、分类树、课程类型与标签。迁移保留现有课程和分类 ID；旧
python/frontend 专区归入 programmer，旧 C++ 系统课程分类归入 C/C++ > C++ 基础。
"""
from alembic import op
import sqlalchemy as sa


revision = "0041_learning_catalog"
down_revision = "0040_course_area_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_areas",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("audience", sa.String(length=200), nullable=True),
        sa.Column("theme_key", sa.String(length=32), nullable=False, server_default="default"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planning"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_learning_areas_status", "learning_areas", ["status"])
    areas = sa.table(
        "learning_areas",
        sa.column("key", sa.String), sa.column("name", sa.String),
        sa.column("description", sa.String), sa.column("audience", sa.String),
        sa.column("theme_key", sa.String), sa.column("status", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(areas, [
        {"key": "kids", "name": "少儿编程", "description": "面向 8–14 岁学习者的编程与科创学习空间。",
         "audience": "8–14 岁学生", "theme_key": "kids", "status": "active", "sort_order": 10},
        {"key": "programmer", "name": "程序员专区", "description": "围绕职业开发能力组织路线、课程与项目实践。",
         "audience": "希望系统提升开发能力的学习者", "theme_key": "programmer", "status": "planning", "sort_order": 20},
    ])

    op.create_table(
        "learning_area_modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_key", sa.String(length=32), sa.ForeignKey("learning_areas.key", ondelete="CASCADE"), nullable=False),
        sa.Column("module_key", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planning"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("area_key", "module_key", name="uq_learning_area_module"),
    )
    op.create_index("ix_learning_area_modules_area_key", "learning_area_modules", ["area_key"])

    op.create_table(
        "course_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_key", sa.String(length=32), sa.ForeignKey("learning_areas.key", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("area_key", "key", name="uq_course_type_area_key"),
    )
    op.create_index("ix_course_types_area_key", "course_types", ["area_key"])
    op.create_index("ix_course_types_is_active", "course_types", ["is_active"])

    naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    inspector = sa.inspect(op.get_bind())
    unique_name = next(
        (item.get("name") for item in inspector.get_unique_constraints("course_categories")
         if item.get("column_names") == ["name"]),
        None,
    )
    with op.batch_alter_table("course_categories", naming_convention=naming) as batch:
        batch.add_column(sa.Column("area_key", sa.String(length=32), nullable=False, server_default="kids"))
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("key", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("description", sa.String(length=300), nullable=True))
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.create_foreign_key("fk_course_categories_area", "learning_areas", ["area_key"], ["key"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_course_categories_parent", "course_categories", ["parent_id"], ["id"], ondelete="RESTRICT")
        batch.drop_constraint(unique_name or "uq_course_categories_name", type_="unique")
    op.execute(sa.text("UPDATE course_categories SET key = 'legacy-' || id WHERE key IS NULL"))
    with op.batch_alter_table("course_categories") as batch:
        batch.alter_column("key", existing_type=sa.String(length=64), nullable=False)
        batch.create_unique_constraint("uq_course_category_tree_key", ["area_key", "parent_id", "key"])
    op.create_index("ix_course_categories_area_key", "course_categories", ["area_key"])
    op.create_index("ix_course_categories_parent_id", "course_categories", ["parent_id"])
    op.create_index("ix_course_categories_is_active", "course_categories", ["is_active"])

    op.execute(sa.text("UPDATE courses SET area_key = 'programmer' WHERE area_key IN ('python', 'frontend')"))
    with op.batch_alter_table("courses") as batch:
        batch.alter_column("course_kind", existing_type=sa.String(length=16), type_=sa.String(length=32), nullable=False)
        batch.create_foreign_key("fk_courses_area", "learning_areas", ["area_key"], ["key"], ondelete="RESTRICT")

    op.create_table(
        "course_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_key", sa.String(length=32), sa.ForeignKey("learning_areas.key", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("area_key", "key", name="uq_course_tag_area_key"),
    )
    op.create_index("ix_course_tags_area_key", "course_tags", ["area_key"])
    op.create_index("ix_course_tags_is_active", "course_tags", ["is_active"])
    op.create_table(
        "course_tag_links",
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("course_tags.id", ondelete="RESTRICT"), primary_key=True),
    )

    # 将历史上名为“C++ 系统课程”的分类调整为树中的 C++ 基础，保留它原本的 ID。
    bind = op.get_bind()
    old = bind.execute(sa.text(
        "SELECT id FROM course_categories WHERE name = :name ORDER BY id LIMIT 1"
    ), {"name": "C++ 系统课程"}).first()
    if old:
        direction = bind.execute(sa.text(
            "SELECT id FROM course_categories WHERE area_key='kids' AND parent_id IS NULL AND key='cpp'"
        )).first()
        if direction is None:
            bind.execute(sa.text(
                "INSERT INTO course_categories (area_key, parent_id, key, name, sort_order, is_active) "
                "VALUES ('kids', NULL, 'cpp', :name, 30, :active)"
            ), {"name": "C/C++", "active": True})
            direction_id = bind.execute(sa.text(
                "SELECT id FROM course_categories WHERE area_key='kids' AND parent_id IS NULL AND key='cpp'"
            )).scalar_one()
        else:
            direction_id = direction.id
        bind.execute(sa.text(
            "UPDATE course_categories SET area_key='kids', parent_id=:parent, key='cpp-1', name=:name "
            "WHERE id=:id"
        ), {"parent": direction_id, "name": "C++ 基础", "id": old.id})


def downgrade() -> None:
    op.drop_table("course_tag_links")
    op.drop_index("ix_course_tags_is_active", table_name="course_tags")
    op.drop_index("ix_course_tags_area_key", table_name="course_tags")
    op.drop_table("course_tags")
    with op.batch_alter_table("courses") as batch:
        batch.drop_constraint("fk_courses_area", type_="foreignkey")
        batch.alter_column("course_kind", existing_type=sa.String(length=32), type_=sa.String(length=16), nullable=False)
    op.execute(sa.text("UPDATE courses SET area_key = 'kids' WHERE area_key = 'programmer'"))
    op.drop_index("ix_course_categories_is_active", table_name="course_categories")
    op.drop_index("ix_course_categories_parent_id", table_name="course_categories")
    op.drop_index("ix_course_categories_area_key", table_name="course_categories")
    with op.batch_alter_table("course_categories") as batch:
        batch.drop_constraint("uq_course_category_tree_key", type_="unique")
        batch.drop_constraint("fk_course_categories_parent", type_="foreignkey")
        batch.drop_constraint("fk_course_categories_area", type_="foreignkey")
        batch.drop_column("is_active")
        batch.drop_column("description")
        batch.drop_column("key")
        batch.drop_column("parent_id")
        batch.drop_column("area_key")
        batch.create_unique_constraint("uq_course_categories_name", ["name"])
    op.drop_index("ix_course_types_is_active", table_name="course_types")
    op.drop_index("ix_course_types_area_key", table_name="course_types")
    op.drop_table("course_types")
    op.drop_index("ix_learning_area_modules_area_key", table_name="learning_area_modules")
    op.drop_table("learning_area_modules")
    op.drop_index("ix_learning_areas_status", table_name="learning_areas")
    op.drop_table("learning_areas")
