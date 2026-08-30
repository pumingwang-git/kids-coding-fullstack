"""自由作品封面：校验、重编码与内容寻址落盘（设计见《63、Scratch 作品封面》）。

封面唯一的来源是学生浏览器里的舞台画布——`.sb3` 是 `project.json` 加素材的 ZIP，
服务端要从它出图就得把 Scratch VM 和 scratch-render 跑起来，为一张缩略图付这个
代价不划算。所以图是客户端截的，**也正因为是客户端截的，这里一个字节都不能信**。

## 三件事，每件都不能省

1. **不信格式声明**。只信 Pillow 的解码结果，不看 Content-Type 也不看文件名——
   改个后缀就能把任意文件塞进来，而这个目录里的文件是要被浏览器当图片加载的。
   与 `admin_media._decode` 同一条理由，那边的注释写得更细。
2. **无条件重编码**。落盘的永远是我们自己编出来的字节，不是上传上来的那份。
   一次重编码同时解决：剥掉 EXIF、剥掉附加在图片尾部的伪装数据（PNG 后面接一段
   ZIP 是经典手法）、把体积和尺寸钉死成常量。
3. **解码前先卡尺寸**。`Image.open()` 只读文件头，不解像素；`COVER_MAX_DIMENSION`
   在真正 `resize` 之前拦住"声明 50000×50000 的 PNG"这类像素炸弹。

## 与 `scratch_sb3` 的分工

那个模块每个函数都在处理 ZIP 结构，封面是图片，两码事，所以另起一个文件。
落盘策略照抄它：同一个受控根目录、两级散列、先写 `.part` 再 `replace`，
**同样不做引用计数删除**（同一张图可能被多份作品指向，删之前得扫全表）。
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# 舞台原生就是 480×360，输出与它一致：不缩放就没有长宽比的取舍。
COVER_WIDTH = 480
COVER_HEIGHT = 360

# 客户端出的是 480×360 WebP q80，实测约 4 KB。这里给 128 倍余量：够宽松到不会
# 误伤（换浏览器、换编码参数），又远小到不足以当上传通道用。
COVER_MAX_UPLOAD_BYTES = 512 * 1024

# 解码前的尺寸闸。舞台截图不可能超过这个数，超了就是别的东西。
COVER_MAX_DIMENSION = 2048

# 能收的输入格式。SVG 天然进不来（Pillow 不认它），但要把话说清楚：**即使 Pillow
# 认，也不能收**——SVG 是可执行 XML，能带 <script>，而这个文件会被 <img> 加载。
_ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP"}

COVER_MEDIA_TYPE = "image/webp"


class CoverInvalid(Exception):
    """封面不合规。调用方**吞掉它**——封面是装饰，不该让保存失败（见《63》§5.1）。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def normalize_cover(raw: bytes) -> bytes:
    """校验 + 重编码成 480×360 WebP。任何不合规抛 `CoverInvalid`。"""
    if not raw:
        raise CoverInvalid("封面内容为空。")
    if len(raw) > COVER_MAX_UPLOAD_BYTES:
        raise CoverInvalid(f"封面不能超过 {COVER_MAX_UPLOAD_BYTES // 1024} KB。")

    try:
        probe = Image.open(BytesIO(raw))
        probe.verify()          # verify() 之后对象不可再用，必须重新 open
        image = Image.open(BytesIO(raw))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise CoverInvalid("封面不是有效的图片。") from exc

    if (image.format or "").upper() not in _ACCEPTED_FORMATS:
        raise CoverInvalid("封面只支持 PNG / JPEG / WebP。")
    if max(image.width, image.height) > COVER_MAX_DIMENSION:
        raise CoverInvalid("封面尺寸过大。")

    try:
        # convert 在 resize 之前：带调色板（P 模式）的 PNG 直接 resize 会把颜色搅成
        # 一团。alpha 一并压掉——舞台的 WebGL 上下文 alpha 是 false，本来就没有透明。
        flat = image.convert("RGB")
        if (flat.width, flat.height) != (COVER_WIDTH, COVER_HEIGHT):
            flat = flat.resize((COVER_WIDTH, COVER_HEIGHT), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        flat.save(buffer, format="WEBP", quality=80, method=6)
    except (OSError, ValueError) as exc:
        raise CoverInvalid("封面处理失败。") from exc
    return buffer.getvalue()


def cover_relative_path(digest: str) -> str:
    """内容寻址相对路径：`covers/ab/abcd….webp`。

    `covers/` 这一层是故意的：与 `.sb3` 共用 `scratch_upload_root`，但两类文件各占
    一棵子树，将来写清理脚本时不会互相扫到对方（与 course_cover 和题干配图分区同理）。
    """
    return f"covers/{digest[:2]}/{digest}.webp"


def store_cover(raw: bytes, settings) -> tuple[str, str]:
    """把**已经 normalize 过的**字节写进受控根目录，返回 (cover_key, sha256)。

    先写 `.part` 再 `replace`：直接写目标路径的话，写一半崩了会留下一个大小对不上
    的文件，而它的文件名是哈希——看起来完全正常，永远不会被重新写入覆盖
    （与 `store_sb3` / `admin_media.upload_image` 同一条理由）。
    """
    digest = hashlib.sha256(raw).hexdigest()
    relative = cover_relative_path(digest)
    root = Path(settings.scratch_upload_root).resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        raise CoverInvalid("封面存储目录配置无效。")
    if target.exists() and target.stat().st_size == len(raw):
        return relative, digest
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".webp.part")
    try:
        temporary.write_bytes(raw)
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise CoverInvalid("封面保存失败。") from exc
    return relative, digest


def read_cover(cover_key: str, settings) -> bytes | None:
    """按 key 读回字节；文件不在就返回 None（调用方回落到生成占位图）。

    **key 不是权限凭证**：调用方必须已经过完归属 / 公开性判断。
    路径逃逸兜底与 `read_sb3` 同理：key 理论上一定是我们自己写进去的那个形状，
    但下发文件这条路径值得多一次 resolve 比对。
    """
    root = Path(settings.scratch_upload_root).resolve()
    target = (root / cover_key).resolve()
    if root not in target.parents or not target.is_file():
        return None
    return target.read_bytes()
