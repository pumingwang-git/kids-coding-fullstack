"""滑块验证码：真图优先（Pillow 切片），无图时回退自研 SVG。

流程（与图片验证码同一套安全策略）：
- 从 data/captcha_images/ 随机选一张图，缩放裁剪为 320x160；
- 随机拼图位置 (x, y)，用拼图形状（圆角方形 + 右侧凸起 + 左侧凹槽）从图上
  抠出拼图块；背景图对应区域压暗 + 描边；拼图块单独成图；
- 水平偏移 x 是唯一秘密，Fernet 加密入库；用户拖动松手后服务端在容差内
  校验（|提交值 - 答案| <= 6）；
- 挑战一次性、5 分钟过期、最多尝试 5 次。预校验（check）不消费，登录
  完全成功后消费（consume）。
"""
import base64
import io
import random
import secrets
import threading
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SliderCaptchaChallenge
from .security import as_utc, decrypt_code, encrypt_code, utcnow

W, H = 320, 160
PIECE = 48
CORNER = 6
NOTCH = 8
TOLERANCE = 10
MISALIGNED_MESSAGE = "滑块未对齐，请再试一次。"
EXPIRED_MESSAGE = "滑块验证已失效，请刷新后重试。"
AUTH_SERVICE_ROOT = Path(__file__).resolve().parent.parent
CAPTCHA_IMAGES_DIR = AUTH_SERVICE_ROOT / "data" / "captcha_images"
BUNDLED_CAPTCHA_IMAGES_DIR = AUTH_SERVICE_ROOT / "captcha_images"
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

_PHOTO_POOL: list[Image.Image] = []
_PHOTO_POOL_READY = False
_PHOTO_LOCK = threading.Lock()
_PIECE_MASK: Image.Image | None = None
_PIECE_MASK_LOCK = threading.Lock()

# ---------------------------------------------------------------- 拼图形状

def _piece_mask() -> Image.Image:
    """56x48 的拼图形状蒙版：圆角方形 + 右侧凸起，左侧凹槽镂空。"""
    global _PIECE_MASK
    with _PIECE_MASK_LOCK:
        if _PIECE_MASK is not None:
            return _PIECE_MASK
        mask = Image.new("L", (PIECE + NOTCH, PIECE), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, PIECE - 1, PIECE - 1], radius=CORNER, fill=255)
        draw.ellipse([PIECE - NOTCH, PIECE // 2 - NOTCH, PIECE + NOTCH, PIECE // 2 + NOTCH], fill=255)
        draw.ellipse([-NOTCH, PIECE // 2 - NOTCH, NOTCH, PIECE // 2 + NOTCH], fill=0)
        _PIECE_MASK = mask
        return mask


def _cover_resize(img: Image.Image, width: int, height: int) -> Image.Image:
    """等比缩放 + 居中裁剪到目标尺寸，并修正 EXIF 方向。"""
    img = ImageOps.exif_transpose(img)
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    img = img.resize((round(src_w * scale), round(src_h * scale)), Image.Resampling.LANCZOS)
    left = (img.width - width) // 2
    top = (img.height - height) // 2
    return img.crop((left, top, left + width, top + height)).convert("RGB")


def _data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def _photo_challenge() -> dict:
    """从真实图片生成滑块挑战。"""
    pool = _load_photo_pool()
    base = _cover_resize(random.choice(pool), W, H)
    low_x = PIECE + NOTCH + 10
    x = low_x + secrets.randbelow(W - PIECE - NOTCH - 20 - low_x)
    y = 20 + secrets.randbelow(H - PIECE - 40)

    # 背景：孔位区域压暗 + 描边
    bg = base.convert("RGBA")
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_dark = ImageDraw.Draw(dark)
    draw_dark.rounded_rectangle([x, y, x + PIECE - 1, y + PIECE - 1], radius=CORNER, fill=(0, 0, 0, 92))
    draw_dark.ellipse([x + PIECE - NOTCH, y + PIECE // 2 - NOTCH, x + PIECE + NOTCH, y + PIECE // 2 + NOTCH], fill=(0, 0, 0, 92))
    draw_dark.ellipse([x - NOTCH, y + PIECE // 2 - NOTCH, x + NOTCH, y + PIECE // 2 + NOTCH], fill=(0, 0, 0, 0))
    bg.alpha_composite(dark)
    draw_bg = ImageDraw.Draw(bg)
    outline = (255, 255, 255, 170)
    draw_bg.rounded_rectangle([x, y, x + PIECE - 1, y + PIECE - 1], radius=CORNER, outline=outline, width=2)
    draw_bg.ellipse([x + PIECE - NOTCH, y + PIECE // 2 - NOTCH, x + PIECE + NOTCH, y + PIECE // 2 + NOTCH], outline=outline, width=2)
    draw_bg.arc([x - NOTCH, y + PIECE // 2 - NOTCH, x + NOTCH, y + PIECE // 2 + NOTCH], start=90, end=270, fill=outline, width=2)
    bg_rgb = bg.convert("RGB")

    # 拼图块：抠出 (x,y) 处的内容，平移到 (0,y)，绿色描边
    piece_canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    crop = base.crop((x, y, x + PIECE + NOTCH, y + PIECE)).convert("RGBA")
    piece_canvas.paste(crop, (0, y), _piece_mask())
    draw_piece = ImageDraw.Draw(piece_canvas)
    border = (47, 128, 110, 255)
    draw_piece.rounded_rectangle([0, y, PIECE - 1, y + PIECE - 1], radius=CORNER, outline=border, width=2)
    draw_piece.ellipse([PIECE - NOTCH, y + PIECE // 2 - NOTCH, PIECE + NOTCH, y + PIECE // 2 + NOTCH], outline=border, width=2)
    draw_piece.arc([-NOTCH, y + PIECE // 2 - NOTCH, NOTCH, y + PIECE // 2 + NOTCH], start=90, end=270, fill=border, width=2)

    buf_bg = io.BytesIO()
    bg_rgb.save(buf_bg, format="JPEG", quality=82, optimize=True)
    buf_piece = io.BytesIO()
    piece_canvas.save(buf_piece, format="PNG", optimize=True)
    return {
        "challenge_id": str(uuid.uuid4()),
        "background": _data_url(buf_bg.getvalue(), "image/jpeg"),
        "piece": _data_url(buf_piece.getvalue(), "image/png"),
        "answer_x": x,
        "answer_y": y,
        "expires_at": utcnow() + timedelta(minutes=5),
    }


# ---------------------------------------------------------------- SVG 回退

def _svg_challenge() -> dict:
    """无真实图片时回退到自研 SVG（保持同一响应结构）。"""
    x = secrets.randbelow(W - PIECE - 40) + PIECE + 20
    y = secrets.randbelow(H - PIECE - 40) + 20
    challenge_id = str(uuid.uuid4())
    noise = _svg_noise(random.Random(secrets.randbelow(1 << 32)))
    shapes = _svg_shapes(x, y, PIECE)
    gradient = (
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#eaf2ec"/><stop offset="1" stop-color="#d3e2d8"/></linearGradient>'
    )
    background = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        f"<defs>{gradient}<mask id=\"hole\"><rect width=\"{W}\" height=\"{H}\" fill=\"#fff\"/>"
        f"{shapes}</mask></defs>"
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>{noise}'
        f'<g mask="url(#hole)"><rect width="{W}" height="{H}" fill="#000" opacity="0.09"/></g>'
        f"{_svg_outline(x, y, PIECE)}</svg>"
    )
    piece = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        f"<defs>{gradient}<clipPath id=\"pc\">{shapes}</clipPath></defs>"
        f'<g clip-path="url(#pc)" transform="translate({-x} 0)">'
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>{noise}</g>'
        f'<g transform="translate({-x} 0)">'
        f'<path d="{_svg_square(x, y, PIECE)} {_svg_circle(x, y + PIECE // 2, NOTCH)}" '
        f'fill="none" stroke="#2f806e" stroke-width="2"/>'
        f'<circle cx="{x + PIECE}" cy="{y + PIECE // 2}" r="{NOTCH}" fill="none" '
        f'stroke="#2f806e" stroke-width="2"/></g></svg>'
    )
    return {
        "challenge_id": challenge_id,
        "background": _data_url(background.encode(), "image/svg+xml"),
        "piece": _data_url(piece.encode(), "image/svg+xml"),
        "answer_x": x,
        "answer_y": y,
        "expires_at": utcnow() + timedelta(minutes=5),
    }


def _svg_square(x: int, y: int, s: int, r: int = CORNER) -> str:
    return (
        f"M{x + r},{y} L{x + s - r},{y} A{r},{r} 0 0 1 {x + s},{y + r} "
        f"L{x + s},{y + s - r} A{r},{r} 0 0 1 {x + s - r},{y + s} "
        f"L{x + r},{y + s} A{r},{r} 0 0 1 {x},{y + s - r} "
        f"L{x},{y + r} A{r},{r} 0 0 1 {x + r},{y} Z"
    )


def _svg_circle(cx: int, cy: int, r: int) -> str:
    return f"M{cx - r},{cy} A{r},{r} 0 1 0 {cx + r},{cy} A{r},{r} 0 1 0 {cx - r},{cy} Z"


def _svg_shapes(x: int, y: int, s: int) -> str:
    dent = f'<path d="{_svg_square(x, y, s)} {_svg_circle(x, y + s // 2, NOTCH)}" fill-rule="evenodd"/>'
    return dent + f'<circle cx="{x + s}" cy="{y + s // 2}" r="{NOTCH}"/>'


def _svg_outline(x: int, y: int, s: int) -> str:
    return (
        f'<path d="{_svg_square(x, y, s)} {_svg_circle(x, y + s // 2, NOTCH)}" '
        f'fill="none" stroke="#0000002e" stroke-width="1.5"/>'
        f'<circle cx="{x + s}" cy="{y + s // 2}" r="{NOTCH}" fill="none" stroke="#0000002e" stroke-width="1.5"/>'
    )


def _svg_noise(rng: random.Random) -> str:
    colors = ("#2f806e", "#b95c50", "#314e75", "#7d4a36", "#45523b", "#62406e")
    parts = []
    for _ in range(14):
        parts.append(
            f'<circle cx="{rng.randrange(2, W)}" cy="{rng.randrange(2, H)}" '
            f'r="{rng.randrange(2, 6)}" fill="{rng.choice(colors)}" '
            f'opacity="{round(rng.uniform(0.08, 0.22), 2)}"/>'
        )
    for _ in range(3):
        parts.append(
            f'<path d="M{rng.randrange(0, W)} {rng.randrange(0, H)} '
            f'L{rng.randrange(0, W)} {rng.randrange(0, H)}" '
            f'stroke="{rng.choice(colors)}" stroke-width="{rng.randrange(1, 3)}" opacity="0.15"/>'
        )
    return "".join(parts)


# ---------------------------------------------------------------- 图库加载

def _load_photo_pool() -> list[Image.Image]:
    global _PHOTO_POOL, _PHOTO_POOL_READY
    with _PHOTO_LOCK:
        if _PHOTO_POOL_READY:
            return _PHOTO_POOL
        pool: list[Image.Image] = []
        # 数据卷里的图库允许后续运营替换；Docker 的 /app/data 被空卷覆盖时，
        # 再使用镜像自带的图库，保证不会无声降级为 SVG。
        for image_dir in (CAPTCHA_IMAGES_DIR, BUNDLED_CAPTCHA_IMAGES_DIR):
            if not image_dir.is_dir():
                continue
            candidate_pool = []
            for path in sorted(image_dir.iterdir()):
                if path.suffix.lower() in _IMAGE_EXTS:
                    try:
                        with Image.open(path) as img:
                            img.load()
                        candidate_pool.append(Image.open(path))
                    except Exception:
                        continue
            if candidate_pool:
                pool = candidate_pool
                break
        _PHOTO_POOL = pool
        _PHOTO_POOL_READY = True
        return pool


def create_slider_challenge() -> dict:
    """生成一次滑块挑战：真图优先，图库为空时回退 SVG。"""
    if _load_photo_pool():
        return _photo_challenge()
    return _svg_challenge()


# ---------------------------------------------------------------- 校验

def _fetch_challenge(db: Session, challenge_id: str | None):
    return (
        db.scalar(
            select(SliderCaptchaChallenge)
            .where(SliderCaptchaChallenge.id == challenge_id)
            .with_for_update()
        )
        if challenge_id
        else None
    )


def _slider_status(challenge, settings, slider_x: int | None, now) -> str:
    """返回 valid / misaligned / dead。"""
    if (
        not challenge
        or challenge.consumed_at
        or as_utc(challenge.expires_at) < now
        or challenge.attempt_count >= 5
    ):
        return "dead"
    try:
        answer = int(decrypt_code(settings, challenge.answer_x_encrypted))
    except Exception:
        return "dead"
    if slider_x is not None and abs(int(slider_x) - answer) <= TOLERANCE:
        return "valid"
    return "misaligned"


def _count_failure(challenge, now) -> None:
    if challenge and not challenge.consumed_at:
        challenge.attempt_count += 1
        if challenge.attempt_count >= 5:
            challenge.consumed_at = now


def check_slider_challenge(db: Session, settings, challenge_id: str | None, slider_x: int | None) -> str:
    """预校验（拖动松手时调用）：misaligned 计一次尝试，成功不消费挑战。

    返回 valid / misaligned / dead——调用方据此给出不同提示。
    """
    now = utcnow()
    challenge = _fetch_challenge(db, challenge_id)
    status = _slider_status(challenge, settings, slider_x, now)
    if status == "misaligned":
        _count_failure(challenge, now)
        db.commit()
        if challenge and challenge.attempt_count >= 5:
            status = "dead"
    return status


def consume_slider_challenge(db: Session, settings, challenge_id: str | None, slider_x: int | None) -> None:
    """登录完全成功后一次性消费已验证的挑战；失败不消耗，可重试。"""
    now = utcnow()
    challenge = _fetch_challenge(db, challenge_id)
    status = _slider_status(challenge, settings, slider_x, now)
    if status == "misaligned":
        raise HTTPException(400, MISALIGNED_MESSAGE)
    if status != "valid":
        raise HTTPException(400, EXPIRED_MESSAGE)
    challenge.consumed_at = now
