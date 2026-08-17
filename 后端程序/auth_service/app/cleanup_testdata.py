"""清理没有被 test_data_packages 引用的 OJ 测试数据目录。

可由定时任务执行：python -m app.cleanup_testdata
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import select

from .config import get_settings
from .database import build_database
from .models import TestDataPackage


def main() -> None:
    settings = get_settings()
    root = Path(settings.testdata_upload_root).resolve()
    if not root.exists():
        print("测试数据目录不存在，无需清理。")
        return
    engine, factory = build_database(settings.database_url)
    db = factory()
    try:
        referenced = {Path(value).as_posix() for value in db.scalars(select(TestDataPackage.storage_dir))}
    finally:
        db.close(); engine.dispose()
    removed = 0
    for problem_dir in root.glob("problem_*"):
        if not problem_dir.is_dir():
            continue
        for candidate in problem_dir.iterdir():
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_dir() and relative not in referenced:
                shutil.rmtree(candidate, ignore_errors=True); removed += 1
        if problem_dir.exists() and not any(problem_dir.iterdir()):
            problem_dir.rmdir()
    print(f"已清理 {removed} 个孤儿测试数据目录。")


if __name__ == "__main__":
    main()
