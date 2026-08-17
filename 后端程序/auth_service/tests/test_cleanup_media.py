"""孤儿配图/封面清理。

这个脚本唯一的危险动作是删文件，所以用例重点全在"什么**不该**被删"：
还被题目引用的、还在宽限期内的（刚传完还没保存进题目的那一批）、
以及课包简介里引用的配图与课包封面——两个存储区域各扫各的引用列。
"""

from datetime import timedelta
from io import BytesIO

from PIL import Image
from test_exam import admin_login, build_app

from app.cleanup_media import sweep_course_covers, sweep_media
from app.models import ChoiceOption, Course, CourseCover, MediaAsset, Problem
from app.security import utcnow


def build_media_app(tmp_path, **overrides):
    return build_app(
        tmp_path,
        media_upload_root=str(tmp_path / "media"),
        course_cover_upload_root=str(tmp_path / "course_covers"),
        **overrides,
    )


def upload(client, headers, color) -> dict:
    with BytesIO() as stream:
        Image.new("RGB", (24, 16), color).save(stream, format="PNG")
        response = client.post("/api/admin/media/images", headers=headers,
                               files={"file": ("p.png", stream.getvalue(), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()


def upload_cover(client, headers, color) -> dict:
    with BytesIO() as stream:
        Image.new("RGB", (32, 20), color).save(stream, format="PNG")
        response = client.post("/api/admin/course-covers", headers=headers,
                               files={"file": ("cover.png", stream.getvalue(), "image/png")})
    assert response.status_code == 201, response.text
    return response.json()


def age_asset(app, sha256: str, days: int):
    """把上传时间往前推，跳过宽限期。"""
    db = app.state.session_factory()
    try:
        asset = db.get(MediaAsset, sha256)
        asset.uploaded_at = utcnow() - timedelta(days=days)
        db.commit()
    finally:
        db.close()


def age_cover(app, sha256: str, days: int):
    db = app.state.session_factory()
    try:
        cover = db.get(CourseCover, sha256)
        cover.uploaded_at = utcnow() - timedelta(days=days)
        db.commit()
    finally:
        db.close()


def test_referenced_image_is_kept(tmp_path):
    """题干里引用着的图，无论多老都不能删。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)
    asset = upload(client, headers, (10, 20, 30))
    age_asset(app, asset["sha256"], days=400)

    db = app.state.session_factory()
    try:
        db.add(Problem(type="choice", stem=f"如图所示 ![]({asset['url']})", analysis=""))
        db.commit()
        removed_rows, removed_files = sweep_media(db, tmp_path / "media", 30, verbose=False)
    finally:
        db.close()

    assert (removed_rows, removed_files) == (0, 0)
    assert (tmp_path / "media" / asset["url"].removeprefix("/media/")).is_file()


def test_image_referenced_only_by_an_option_is_kept(tmp_path):
    """图形选择题的选项就是一张图。漏扫 choice_options 会把整套选项图删光。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)
    asset = upload(client, headers, (40, 50, 60))
    age_asset(app, asset["sha256"], days=400)

    db = app.state.session_factory()
    try:
        problem = Problem(type="choice", stem="选出正确的图形", analysis="")
        db.add(problem)
        db.flush()
        db.add(ChoiceOption(problem_id=problem.id, option_label="A",
                            content=f"![]({asset['url']})", is_correct=True))
        db.commit()
        removed_rows, _ = sweep_media(db, tmp_path / "media", 30, verbose=False)
    finally:
        db.close()

    assert removed_rows == 0


def test_fresh_unreferenced_image_survives_grace_period(tmp_path):
    """传了图还没点保存就去吃饭。立刻删掉的话，回来一保存就是一张裂图。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)
    asset = upload(client, headers, (70, 80, 90))

    db = app.state.session_factory()
    try:
        removed_rows, removed_files = sweep_media(db, tmp_path / "media", 30, verbose=False)
    finally:
        db.close()

    assert (removed_rows, removed_files) == (0, 0)
    assert (tmp_path / "media" / asset["url"].removeprefix("/media/")).is_file()


def test_stale_unreferenced_image_is_removed(tmp_path):
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)
    asset = upload(client, headers, (100, 110, 120))
    age_asset(app, asset["sha256"], days=400)
    path = tmp_path / "media" / asset["url"].removeprefix("/media/")

    db = app.state.session_factory()
    try:
        removed_rows, _ = sweep_media(db, tmp_path / "media", 30, verbose=False)
        assert db.get(MediaAsset, asset["sha256"]) is None
    finally:
        db.close()

    assert removed_rows == 1
    assert not path.exists()


def test_dry_run_touches_nothing(tmp_path):
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)
    asset = upload(client, headers, (130, 140, 150))
    age_asset(app, asset["sha256"], days=400)
    path = tmp_path / "media" / asset["url"].removeprefix("/media/")

    db = app.state.session_factory()
    try:
        removed_rows, _ = sweep_media(db, tmp_path / "media", 30, dry_run=True, verbose=False)
        assert db.get(MediaAsset, asset["sha256"]) is not None
    finally:
        db.close()

    assert removed_rows == 1        # 报告了，但没动
    assert path.is_file()


def test_orphan_file_without_row_is_removed(tmp_path):
    """写盘成功但写库失败会留下这种残骸，还有 .part 半成品。"""
    app = build_media_app(tmp_path)
    root = tmp_path / "media"
    (root / "ab").mkdir(parents=True, exist_ok=True)
    stray = root / "ab" / f"ab{'0' * 62}.png"
    stray.write_bytes(b"leftover")

    db = app.state.session_factory()
    try:
        _rows, removed_files = sweep_media(db, root, 30, verbose=False)
    finally:
        db.close()

    assert removed_files == 1
    assert not stray.exists()


# ==================== 课包简介配图 ====================


def test_image_referenced_only_by_course_description_is_kept(tmp_path):
    """课包简介用 Vditor 编辑，插图以 /media/ URL 进 Course.description。
    漏扫这一列，简介里的图会被当孤儿删掉——cleanup_media.py 的文档里
    明确警告过这个危险点。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)
    asset = upload(client, headers, (11, 22, 33))
    age_asset(app, asset["sha256"], days=400)

    db = app.state.session_factory()
    try:
        db.add(Course(title="课包", description=f"简介插图 ![]({asset['url']})"))
        db.commit()
        removed_rows, _ = sweep_media(db, tmp_path / "media", 30, verbose=False)
    finally:
        db.close()

    assert removed_rows == 0
    assert (tmp_path / "media" / asset["url"].removeprefix("/media/")).is_file()


# ==================== 课包封面（独立存储区域） ====================


def test_course_cover_sweeps_its_own_area_only(tmp_path):
    """封面清理只扫 course_covers 目录与 Course.cover_url 引用列；
    题干配图目录里放什么它都不碰（两个清理函数各扫各的区域）。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)

    cover = upload_cover(client, headers, (200, 100, 50))
    age_cover(app, cover["sha256"], days=400)

    # 题干配图区放一张孤儿文件：sweep_course_covers 不该碰它
    media_stray = tmp_path / "media" / "ab" / f"ab{'0' * 62}.png"
    media_stray.parent.mkdir(parents=True, exist_ok=True)
    media_stray.write_bytes(b"problem-media-stray")

    db = app.state.session_factory()
    try:
        # 封面被课包引用 → 封面清理不删它
        db.add(Course(title="课包", cover_url=cover["url"]))
        db.commit()
        rows, files = sweep_course_covers(db, tmp_path / "course_covers", 30, verbose=False)
    finally:
        db.close()

    assert (rows, files) == (0, 0)
    assert (tmp_path / "course_covers" / cover["url"].removeprefix("/course-covers/")).is_file()
    assert media_stray.is_file()  # 题干配图目录不受封面清理影响


def test_stale_unreferenced_cover_is_removed(tmp_path):
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)
    cover = upload_cover(client, headers, (210, 120, 60))
    age_cover(app, cover["sha256"], days=400)
    path = tmp_path / "course_covers" / cover["url"].removeprefix("/course-covers/")

    db = app.state.session_factory()
    try:
        removed_rows, _ = sweep_course_covers(db, tmp_path / "course_covers", 30, verbose=False)
        assert db.get(CourseCover, cover["sha256"]) is None
    finally:
        db.close()

    assert removed_rows == 1
    assert not path.exists()
