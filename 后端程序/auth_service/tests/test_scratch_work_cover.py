"""自由作品封面：采集、校验、落盘与下发（设计见《63、Scratch 作品封面》）。

封面唯一的来源是学生浏览器里的舞台截图，所以它是**用户可控字节**，这个文件守的
就是"可控字节进了服务端会不会出事"，外加两条容易写反的降级：

- 落盘的必须是服务端重编码的字节，不是上传上来的那份（剥 EXIF、剥尾部附加数据）；
- 封面坏了**不许牵连作品保存**——封面是装饰，作品是资产；
- 封面文件丢了**不许变成裂图或 500**，回落到生成占位图。

权限口径与文件其余部分一致：别人的作品封面 404（范围闸，与"不存在"逐字相同），
私密作品在画廊路径下同样 404——封面能猜到，等于私密作品的画面能被枚举。
"""
from io import BytesIO
from pathlib import Path

from PIL import Image
from test_exam import scsrf, student_login
from test_scratch import sb3_bytes, scratch_env, scripted_sprite, stage_target
from test_scratch_works import new_work

from app.scratch_cover import COVER_HEIGHT, COVER_MAX_UPLOAD_BYTES, COVER_WIDTH


# ---------- 小工具 ----------


def png_bytes(width=COVER_WIDTH, height=COVER_HEIGHT, color=(20, 140, 90)):
    buffer = BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def save_with_cover(sclient, work_id, sb3, cover=None, *, cover_name="cover.webp"):
    files = {"file": ("work.sb3", sb3, "application/zip")}
    if cover is not None:
        files["cover"] = (cover_name, cover, "image/png")
    return sclient.put(f"/api/scratch/works/{work_id}", headers=scsrf(sclient),
                       files=files, data={"source": "manual"})


def project(tmp_path: Path):
    """登录学生 + 一份作品 + 一份合法 .sb3。"""
    app = scratch_env(tmp_path)
    sclient = student_login(app, "alice")
    work = new_work(sclient, "封面测试", is_public=False)
    return app, sclient, work, sb3_bytes([stage_target(), scripted_sprite()])


def cover_dir(tmp_path: Path):
    return tmp_path / "scratch" / "covers"


def stored_covers(tmp_path: Path):
    root = cover_dir(tmp_path)
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


# ---------- 不传封面：一切照旧 ----------


def test_save_without_cover_still_works_and_falls_back_to_generated_svg(tmp_path: Path):
    """封面是可选的。不传照样保存成功，`thumbnail_url` 仍然给得出一张能显示的图。"""
    _app, sclient, work, sb3 = project(tmp_path)
    assert save_with_cover(sclient, work["id"], sb3).status_code == 200

    listed = sclient.get("/api/scratch/works").json()["items"][0]
    assert listed["thumbnail_url"], "thumbnail_url 永远不该为空——前端不判空"
    resp = sclient.get(listed["thumbnail_url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert not stored_covers(tmp_path), "没传封面就不该有文件落盘"


# ---------- 传了封面：落盘 + 下发 ----------


def test_uploaded_cover_is_stored_and_served_as_webp(tmp_path: Path):
    _app, sclient, work, sb3 = project(tmp_path)
    assert save_with_cover(sclient, work["id"], sb3, png_bytes()).status_code == 200

    listed = sclient.get("/api/scratch/works").json()["items"][0]
    resp = sclient.get(listed["thumbnail_url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    image = Image.open(BytesIO(resp.content))
    assert (image.format, image.size) == ("WEBP", (COVER_WIDTH, COVER_HEIGHT))
    assert len(stored_covers(tmp_path)) == 1


def test_stored_bytes_are_reencoded_not_the_uploaded_ones(tmp_path: Path):
    """落盘的必须是服务端编出来的字节。

    这条守的是"剥 EXIF、剥尾部附加数据"那一整类问题：只要原样落盘，PNG 后面接一段
    ZIP 就能原样发回给浏览器。所以取回的字节必须与上传的不同，且必须是 WebP。
    """
    _app, sclient, work, sb3 = project(tmp_path)
    uploaded = png_bytes() + b"PK\x03\x04TRAILING-PAYLOAD"   # 尾部挂一段伪装数据
    assert save_with_cover(sclient, work["id"], sb3, uploaded).status_code == 200

    listed = sclient.get("/api/scratch/works").json()["items"][0]
    served = sclient.get(listed["thumbnail_url"]).content
    assert served != uploaded
    assert b"TRAILING-PAYLOAD" not in served
    assert Image.open(BytesIO(served)).format == "WEBP"


def test_resaving_changes_the_cache_version_in_the_url(tmp_path: Path):
    """哨兵：换了封面，下发地址必须跟着变。

    响应头是 `private, max-age=60`，地址不变的话学生刚保存完看到的还是旧封面，
    看着就像"保存没生效"。
    """
    _app, sclient, work, sb3 = project(tmp_path)
    save_with_cover(sclient, work["id"], sb3, png_bytes(color=(10, 10, 10)))
    first = sclient.get("/api/scratch/works").json()["items"][0]["thumbnail_url"]

    save_with_cover(sclient, work["id"], sb3, png_bytes(color=(240, 30, 30)))
    second = sclient.get("/api/scratch/works").json()["items"][0]["thumbnail_url"]
    assert first != second, "封面换了地址没变，客户端会拿缓存里的旧图"


# ---------- 坏封面：拒收，但不牵连作品 ----------


def test_bad_cover_never_fails_the_save(tmp_path: Path):
    """伪装成图片的字节被拒，**而作品本体保存成功**。

    这是本设计里最容易写反的一条：把 CoverInvalid 转成 400，学生就会因为一张截图
    存不进去而整份作品保存失败。
    """
    _app, sclient, work, sb3 = project(tmp_path)
    resp = save_with_cover(sclient, work["id"], sb3, sb3, cover_name="cover.png")  # 拿 .sb3 冒充图
    assert resp.status_code == 200, "封面不合法不该让保存失败"

    listed = sclient.get("/api/scratch/works").json()["items"][0]
    assert listed["has_content"] is True
    assert sclient.get(listed["thumbnail_url"]).headers["content-type"].startswith("image/svg+xml")
    assert not stored_covers(tmp_path), "被拒的封面不该留下文件"


def test_oversized_cover_is_rejected_before_it_lands(tmp_path: Path):
    """超过体积上限直接拒，且不落盘。"""
    _app, sclient, work, sb3 = project(tmp_path)
    huge = png_bytes(1024, 1024, color=(3, 200, 111)) + b"\x00" * COVER_MAX_UPLOAD_BYTES
    assert len(huge) > COVER_MAX_UPLOAD_BYTES
    assert save_with_cover(sclient, work["id"], sb3, huge).status_code == 200
    assert not stored_covers(tmp_path)


def test_oversized_dimension_is_rejected(tmp_path: Path):
    """尺寸闸：声明得下、解出来是巨图的，在 resize 之前就拦掉。"""
    _app, sclient, work, sb3 = project(tmp_path)
    # 纯色大图压得很小，体积闸放得过去，只有尺寸闸能拦
    giant = png_bytes(4096, 64, color=(255, 255, 255))
    assert len(giant) <= COVER_MAX_UPLOAD_BYTES
    assert save_with_cover(sclient, work["id"], sb3, giant).status_code == 200
    assert not stored_covers(tmp_path)


def test_missing_cover_file_falls_back_instead_of_breaking(tmp_path: Path):
    """封面文件被误删 / 换过存储根：回落到生成图，不是 404 也不是裂图。"""
    _app, sclient, work, sb3 = project(tmp_path)
    save_with_cover(sclient, work["id"], sb3, png_bytes())
    for path in stored_covers(tmp_path):
        path.unlink()

    listed = sclient.get("/api/scratch/works").json()["items"][0]
    resp = sclient.get(listed["thumbnail_url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")


# ---------- 权限 ----------


def test_other_students_cover_is_404_word_for_word(tmp_path: Path):
    """范围闸：别人的作品封面与"不存在"逐字相同，不能是 403。"""
    app = scratch_env(tmp_path)
    alice = student_login(app, "alice")
    bob = student_login(app, "bob")
    work = new_work(alice, "alice 的作品", is_public=False)
    save_with_cover(alice, work["id"], sb3_bytes([stage_target(), scripted_sprite()]), png_bytes())

    denied = bob.get(f"/api/scratch/works/{work['id']}/cover")
    missing = bob.get("/api/scratch/works/999999/cover")
    assert denied.status_code == 404
    assert denied.json() == missing.json()


def test_private_work_cover_is_404_in_gallery(tmp_path: Path):
    """私密作品在画廊路径下取封面同样 404——否则等于把私密作品的画面开放枚举。"""
    app = scratch_env(tmp_path)
    alice = student_login(app, "alice")
    bob = student_login(app, "bob")
    work = new_work(alice, "私密作品", is_public=False)
    save_with_cover(alice, work["id"], sb3_bytes([stage_target(), scripted_sprite()]), png_bytes())

    assert bob.get(f"/api/scratch/gallery/{work['id']}/cover").status_code == 404
    # 哨兵（别拦过头）：改成公开之后，同一条路径必须能取到
    alice.patch(f"/api/scratch/works/{work['id']}", headers=scsrf(alice), json={"is_public": True})
    ok = bob.get(f"/api/scratch/gallery/{work['id']}/cover")
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "image/webp"


# ---------- 老数据 ----------


def test_legacy_work_without_cover_still_lists_and_renders(tmp_path: Path):
    """哨兵：本次改动之前的作品（cover_key 为空）列表照常返回、封面照常显示。"""
    _app, sclient, work, sb3 = project(tmp_path)
    save_with_cover(sclient, work["id"], sb3)          # 从头到尾没传过封面

    items = sclient.get("/api/scratch/works").json()["items"]
    assert len(items) == 1
    assert items[0]["thumbnail_url"].endswith("/cover?v=0")
    assert sclient.get(items[0]["thumbnail_url"]).status_code == 200
