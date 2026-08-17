"""验收辅助：解密滑块验证码答案（只读查询，不修改数据库）。

用法：.venv/Scripts/python 解密滑块-临时.py <slider_id>
"""
import sys

from sqlalchemy import create_engine, text

from app.config import get_settings
from app.security import decrypt_code

slider_id = sys.argv[1]
settings = get_settings()
engine = create_engine(settings.database_url)
with engine.connect() as conn:
    row = conn.execute(
        text("SELECT answer_x_encrypted FROM slider_captcha_challenges WHERE id = :id"),
        {"id": slider_id},
    ).fetchone()
print(decrypt_code(settings, row[0]) if row else "NOT_FOUND")
