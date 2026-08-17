"""清理没有被引用的题干配图与课包封面。

    python -m app.cleanup_media --dry-run      # 先看会动哪些
    python -m app.cleanup_media                # 真删
    0 4 * * *  cd /srv/auth_service && .venv/bin/python -m app.cleanup_media

**为什么是离线扫描而不是实时引用计数**：引用关系存在 Markdown 正文的 URL 里，
"插入后又删掉""复制题干到另一道题""审核打回后重写"这些动作没有一个经过可以挂计数的
地方。硬做计数只会得到一个慢慢变得不准的数字，而它错的方向要么是漏删（无害），
要么是**删掉正在用的图**（题干直接裂）。扫一遍全文是唯一不会骗人的做法。

**为什么要宽限期**：录题人上传了图、还没点保存就去吃饭，这时图已在库里但没有任何
引用。扫描器立刻删掉，回来一保存就是一张裂图。宽限期从"最后一次被看见"算起，
从没被引用过的则从上传时间算起。

**两套存储区域，各自扫各自的引用列**：
- 题干配图：data/media + media_assets 表，引用列是题目正文/解析/选项（/media/ URL）；
- 课包封面：data/course_covers + course_covers 表，引用列是 courses.cover_url
  （/course-covers/ URL）。两个根目录分开关在 sweep_media / sweep_course_covers 里，
  谁也不碰谁的磁盘文件。

⚠️ 将来把配图放进新的文本列（比如课程节点简介），**必须回到 _SCANNED_COLUMNS 补一行**，
否则那些图会被当成孤儿删掉。这是本脚本唯一的危险点。
"""

from __future__ import annotations

import argparse
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from .config import get_settings
from .database import build_database
from .models import ChoiceOption, Course, CourseCover, MediaAsset, Problem
from .routers.admin_media import course_cover_relative_path, media_relative_path
from .security import as_utc, utcnow

# 所有可能出现配图的文本列。少一行 = 那一列引用的图会被误删。
# Course.description 是课包简介：后台用 Vditor 编辑，插图会以 /media/ URL 进正文。
_SCANNED_COLUMNS = (Problem.stem, Problem.analysis, ChoiceOption.content, Course.description)

# 与 media_relative_path() 拼出的 URL 严格对应。宽松匹配（比如只找 40 位十六进制）
# 会把题面里恰好出现的哈希串当成引用，那是往"不敢删"的方向错，但会让脚本永远清不掉东西。
_MEDIA_URL_RE = re.compile(r"/media/[0-9a-f]{2}/([0-9a-f]{64})\.[A-Za-z0-9]{1,8}")

# 课包封面的 URL 前缀独立于题干配图（course_cover_relative_path 拼出的形状）。
_COURSE_COVER_URL_RE = re.compile(r"/course-covers/[0-9a-f]{2}/([0-9a-f]{64})\.[A-Za-z0-9]{1,8}")


def _referenced(db) -> set[str]:
    found: set[str] = set()
    for column in _SCANNED_COLUMNS:
        for text in db.scalars(select(column)):
            if text:
                found.update(_MEDIA_URL_RE.findall(text))
    return found


def sweep_media(db, root: Path, retention_days: int, *, dry_run: bool = False,
                verbose: bool = True) -> tuple[int, int]:
    """回收孤儿图，返回（删除的行数, 删除的磁盘文件数）。

    与 main() 分开是为了能在测试里直接用测试会话调它——CLI 那层只负责读配置、
    开连接、打印，不该是唯一入口（cleanup_testdata.py 的教训）。
    """
    now = utcnow()
    cutoff = now - timedelta(days=retention_days)
    referenced = _referenced(db)
    assets = list(db.scalars(select(MediaAsset)))

    removed_rows = 0
    known_files: set[Path] = set()
    for asset in assets:
        path = root / media_relative_path(asset.sha256, asset.ext)
        if asset.sha256 in referenced:
            known_files.add(path)
            if not dry_run:
                asset.last_seen_at = now
            continue
        # 没被引用：从"最后一次被看见"起算宽限；从没被看见过的从上传时间起算。
        # 后者正是"传了图还没保存题目"的那一批，也是宽限期存在的全部理由。
        anchor = asset.last_seen_at or asset.uploaded_at
        if anchor is not None and as_utc(anchor) > cutoff:
            known_files.add(path)   # 还在宽限期内，文件不算孤儿
            continue
        removed_rows += 1
        if verbose:
            print(f"[{'dry-run' if dry_run else 'delete'}] 图片 {asset.sha256[:12]}… "
                  f"({asset.byte_size} 字节，上传于 {asset.uploaded_at})")
        if not dry_run:
            path.unlink(missing_ok=True)
            db.delete(asset)

    # 库里没有的磁盘文件：上传写盘成功但写库失败留下的残骸，以及 .part 半成品。
    removed_files = 0
    if root.exists():
        for candidate in root.rglob("*"):
            if not candidate.is_file() or candidate in known_files:
                continue
            if not dry_run:
                candidate.unlink(missing_ok=True)
            removed_files += 1
            if verbose:
                print(f"[{'dry-run' if dry_run else 'delete'}] 孤儿文件 {candidate.name}")

    if not dry_run:
        db.commit()
    return removed_rows, removed_files


def _referenced_course_covers(db) -> set[str]:
    """课包封面的引用列只有 courses.cover_url 一个。"""
    found: set[str] = set()
    for url in db.scalars(select(Course.cover_url)):
        if url:
            found.update(_COURSE_COVER_URL_RE.findall(url))
    return found


def sweep_course_covers(db, root: Path, retention_days: int, *, dry_run: bool = False,
                        verbose: bool = True) -> tuple[int, int]:
    """回收孤儿课包封面，返回（删除的行数, 删除的磁盘文件数）。

    与 sweep_media 同构，但只碰 course_covers 表与 course_covers 目录——
    两个清理函数各扫各的存储区域，互不干扰（这是封面单独开存储区的全部理由）。
    """
    now = utcnow()
    cutoff = now - timedelta(days=retention_days)
    referenced = _referenced_course_covers(db)
    assets = list(db.scalars(select(CourseCover)))

    removed_rows = 0
    known_files: set[Path] = set()
    for asset in assets:
        path = root / course_cover_relative_path(asset.sha256, asset.ext)
        if asset.sha256 in referenced:
            known_files.add(path)
            if not dry_run:
                asset.last_seen_at = now
            continue
        anchor = asset.last_seen_at or asset.uploaded_at
        if anchor is not None and as_utc(anchor) > cutoff:
            known_files.add(path)
            continue
        removed_rows += 1
        if verbose:
            print(f"[{'dry-run' if dry_run else 'delete'}] 封面 {asset.sha256[:12]}… "
                  f"({asset.byte_size} 字节，上传于 {asset.uploaded_at})")
        if not dry_run:
            path.unlink(missing_ok=True)
            db.delete(asset)

    removed_files = 0
    if root.exists():
        for candidate in root.rglob("*"):
            if not candidate.is_file() or candidate in known_files:
                continue
            if not dry_run:
                candidate.unlink(missing_ok=True)
            removed_files += 1
            if verbose:
                print(f"[{'dry-run' if dry_run else 'delete'}] 孤儿封面文件 {candidate.name}")

    if not dry_run:
        db.commit()
    return removed_rows, removed_files


def main() -> None:
    parser = argparse.ArgumentParser(description="清理没有被任何题目引用的题干配图与课包封面。")
    parser.add_argument("--dry-run", action="store_true", help="只列出将被删除的文件，不写库也不删文件")
    args = parser.parse_args()

    settings = get_settings()
    root = Path(settings.media_upload_root).resolve()
    cover_root = Path(settings.course_cover_upload_root).resolve()
    engine, factory = build_database(settings.database_url)
    db = factory()
    try:
        rows, files = sweep_media(db, root, settings.media_retention_days, dry_run=args.dry_run)
        cover_rows, cover_files = sweep_course_covers(
            db, cover_root, settings.media_retention_days, dry_run=args.dry_run)
    finally:
        db.close()
        engine.dispose()
    prefix = "将清理" if args.dry_run else "已清理"
    print(f"{prefix} {rows} 张孤儿图片、{files} 个游离文件、"
          f"{cover_rows} 张孤儿封面、{cover_files} 个游离封面文件。")


if __name__ == "__main__":
    main()
