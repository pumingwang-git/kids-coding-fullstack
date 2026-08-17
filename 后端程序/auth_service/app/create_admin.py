"""创建/更新 B 端管理员账号。

用法（PowerShell）：
    $env:ADMIN_USERNAME="admin"; $env:ADMIN_PASSWORD="Your-Admin-pass-123!"; python -m app.create_admin
或位置参数：
    python -m app.create_admin admin "Your-Admin-pass-123!" "超级管理员"
"""
import os
import sys

from sqlalchemy import select

from .config import get_settings
from .database import build_database
from .models import AdminUser
from .permissions import validate_admin_role
from .security import password_hash


def main() -> None:
    username = os.environ.get("ADMIN_USERNAME") or (sys.argv[1] if len(sys.argv) > 1 else "")
    password = os.environ.get("ADMIN_PASSWORD") or (sys.argv[2] if len(sys.argv) > 2 else "")
    display = os.environ.get("ADMIN_DISPLAY_NAME") or (sys.argv[3] if len(sys.argv) > 3 else username)
    role = os.environ.get("ADMIN_ROLE") or "super_admin"
    if not username or not password:
        print("用法：ADMIN_USERNAME=xxx ADMIN_PASSWORD=yyy python -m app.create_admin")
        raise SystemExit(1)
    try:
        role = validate_admin_role(role)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    settings = get_settings()
    _, factory = build_database(settings.database_url)
    db = factory()
    try:
        existing = db.scalar(select(AdminUser).where(AdminUser.username == username))
        if existing:
            existing.password_hash = password_hash.hash(password)
            existing.display_name = display
            existing.role = role
            existing.status = "active"
            existing.failed_login_count = 0
            existing.locked_until = None
            db.commit()
            print(f"已更新管理员：{username}（{role}）")
        else:
            db.add(
                AdminUser(
                    username=username,
                    password_hash=password_hash.hash(password),
                    display_name=display,
                    role=role,
                )
            )
            db.commit()
            print(f"已创建管理员：{username}（{role}）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
