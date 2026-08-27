"""Alembic revision id 长度守卫。

Alembic 建 ``alembic_version`` 时把 ``version_num`` 声明成 ``VARCHAR(32)``。
超过 32 个字符的 revision id 在 **PostgreSQL 上直接写不进去**（StringDataRightTruncation），
整条升级事务回滚；而迁移测试跑在 SQLite 上，SQLite 不强制 VARCHAR 长度，照单全收——
于是这类缺陷能一路绿灯到生产。

`0069_audit_events_created_at_index`（34 字符）就是这么混进来的：它从未成功落过任何
PostgreSQL 库，直到 2026-08-27 升级配置库时才暴露，已改名为 `0069_audit_events_created_idx`。
"""

from pathlib import Path

import pytest

# Alembic 默认的 alembic_version.version_num 宽度。改这个常量前先确认线上表结构。
VERSION_NUM_MAX_LENGTH = 32

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _revision_ids() -> list[tuple[str, str]]:
    """从每个迁移文件里取出 (文件名, revision id)。"""
    found = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("revision = "):
                found.append((path.name, stripped.split("=", 1)[1].strip().strip("\"'")))
                break
    return found


def test_versions_directory_is_not_empty():
    """守卫自身的哨兵：解析不到任何 revision 时，下面那条会恒绿。"""
    assert len(_revision_ids()) > 50, "没解析到迁移文件，长度守卫等于没跑"


@pytest.mark.parametrize("filename,revision", _revision_ids())
def test_revision_id_fits_postgres_version_column(filename: str, revision: str):
    assert len(revision) <= VERSION_NUM_MAX_LENGTH, (
        f"{filename} 的 revision id 有 {len(revision)} 个字符，超过 "
        f"alembic_version.version_num 的 VARCHAR({VERSION_NUM_MAX_LENGTH})。"
        f"PostgreSQL 会拒绝写入并回滚整条升级；SQLite 不会报错，所以其它迁移测试抓不到。"
        f"改短 revision id（同时改下游的 down_revision 与引用它的测试）。"
    )
