import json
import logging
import re
import smtplib
import uuid
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import and_, or_, select, update

from .models import EmailOutbox, User
from .security import decrypt_code, utcnow

logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class InMemoryEmailSender:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, recipient: str, code: str, event_type: str = "verification") -> None:
        self.sent.append({"recipient": recipient, "code": code, "event_type": event_type})


class SmtpEmailSender:
    def __init__(self, settings):
        self.settings = settings

    def send(self, recipient: str, code: str, event_type: str = "verification") -> None:
        message = build_security_email(self.settings.smtp_from, recipient, code, event_type)
        with smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
            smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)


def build_code_email(sender: str, recipient: str, code: str, event_type: str) -> EmailMessage:
    """Build a consistent HTML email for every email-code security flow."""
    if event_type == "verification":
        subject, title = "【启程学堂】注册邮箱验证码", "确认你的邮箱"
        intro, details = "你正在完成本次注册的邮箱验证。", "请在页面中输入下面的 6 位验证码。"
    elif event_type == "password_change":
        subject, title = "【启程学堂】修改密码验证码", "确认修改密码"
        intro, details = "你正在修改登录密码。", "请在安全设置页面中输入下面的 6 位验证码。"
    else:
        subject, title = "【启程学堂】密码重置验证码", "确认重置密码"
        intro, details = "你正在找回登录密码。", "请在找回密码页面中输入下面的 6 位验证码。"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("启程学堂", sender))
    message["To"] = recipient
    message.set_content(
        f"你好，\n\n{intro} 验证码是 {code}，15 分钟内有效。请勿将验证码提供给他人；如非本人操作，请忽略此邮件。\n\n—— 启程学堂"
    )
    message.add_alternative(
        f"""<!doctype html>
<html lang="zh-CN">
  <body style="margin:0;padding:0;background:#f8f8f0;color:#222b28;font-family:-apple-system,BlinkMacSystemFont,'Noto Sans SC','Microsoft YaHei',sans-serif;">
    <main style="max-width:600px;margin:0 auto;padding:32px 20px;">
      <section style="overflow:hidden;border:1px solid rgba(34,43,40,.14);border-radius:8px;background:#ffffff;box-shadow:0 10px 24px rgba(34,43,40,.08);">
        <header style="padding:20px 28px;border-bottom:1px solid rgba(34,43,40,.14);background:#dcebe1;">
          <p style="margin:0;color:#2f806e;font-size:11px;font-weight:700;letter-spacing:.8px;">QICHENG ACADEMY · LEARNING PLATFORM</p>
          <h1 style="margin:8px 0 0;font-family:'Noto Serif SC','Songti SC',serif;font-size:24px;font-weight:500;letter-spacing:-1px;">{title}</h1>
        </header>
        <div style="padding:30px 28px 28px;">
          <p style="margin:0 0 16px;font-size:15px;line-height:1.8;">你好，{intro}</p>
          <p style="margin:0;color:#68716d;font-size:14px;line-height:1.8;">{details} 请勿将它提供给任何人：</p>
          <p style="margin:24px 0;padding:18px 16px;border-radius:4px;background:#f8f8f0;color:#2f806e;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:32px;font-weight:800;letter-spacing:8px;text-align:center;">{code}</p>
          <p style="margin:0;color:#68716d;font-size:13px;line-height:1.8;">验证码将在 <strong style="color:#222b28;">15 分钟</strong> 后失效。为保护你的账户，请勿将它提供给任何人。</p>
        </div>
        <footer style="padding:18px 28px;border-top:1px solid rgba(34,43,40,.14);color:#68716d;font-size:12px;line-height:1.7;">如非本人操作，请忽略此邮件。<br>—— 启程学堂</footer>
      </section>
    </main>
  </body>
</html>""",
        subtype="html",
    )
    return message


def build_verification_email(
    sender: str, recipient: str, code: str, event_type: str = "verification"
) -> EmailMessage:
    """Backward-compatible registration-email entry point."""
    return build_code_email(sender, recipient, code, event_type)


def build_security_email(sender: str, recipient: str, code: str, event_type: str) -> EmailMessage:
    if event_type == "verification":
        return build_verification_email(sender, recipient, code)
    if event_type == "login_alert":
        return build_login_alert_email(sender, recipient, code)
    return build_code_email(sender, recipient, code, event_type)


def build_login_alert_email(sender: str, recipient: str, payload: str) -> EmailMessage:
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        data = {}
    location = (
        " / ".join(
            part for part in (data.get("country"), data.get("province"), data.get("city")) if part
        )
        or "地区暂未识别"
    )
    ip = str(data.get("ip") or "未知")
    masked_ip = ip[: ip.rfind(".") + 1] + "***" if "." in ip else "已隐藏"
    body = (
        "检测到你的账号在新的 IP 或新地区登录。\n\n"
        f"登录时间：{data.get('time') or '未知'}\n登录地区：{location}\n登录 IP：{masked_ip}\n"
        f"设备信息：{data.get('user_agent') or '未知设备'}\n\n"
        "如果是你本人操作，可忽略此邮件；如非本人，请立即重置密码，并在安全中心启用双重验证。"
    )
    message = EmailMessage()
    message["Subject"] = "【启程学堂】检测到异地或新 IP 登录"
    message["From"] = formataddr(("启程学堂", sender))
    message["To"] = recipient
    message.set_content(body)
    return message


def safe_smtp_error(error: Exception) -> str:
    """Keep SMTP diagnostics useful without writing recipients or secrets to logs."""
    return EMAIL_PATTERN.sub("[redacted-email]", str(error))[:500]


def _claim_outbox(db, settings, outbox_id: int, now):
    token = str(uuid.uuid4())
    stale_before = now - timedelta(seconds=settings.outbox_lock_seconds)
    eligible = and_(
        EmailOutbox.id == outbox_id,
        EmailOutbox.status.in_(("pending", "retry")),
        EmailOutbox.attempts < settings.outbox_max_attempts,
        EmailOutbox.next_attempt_at <= now,
        or_(EmailOutbox.locked_at.is_(None), EmailOutbox.locked_at < stale_before),
    )
    if not db.execute(
        update(EmailOutbox).where(eligible).values(locked_at=now, lock_token=token)
    ).rowcount:
        db.commit()
        return None
    outbox = db.scalar(
        select(EmailOutbox).where(EmailOutbox.id == outbox_id, EmailOutbox.lock_token == token)
    )
    user = db.get(User, outbox.user_id) if outbox else None
    db.commit()
    return token, outbox, user


def deliver_outbox(session_factory, sender, settings, outbox_id: int) -> bool:
    db = session_factory()
    try:
        now = utcnow()
        claimed = _claim_outbox(db, settings, outbox_id, now)
        if not claimed:
            return False
        token, outbox, user = claimed
        try:
            if not user:
                raise RuntimeError("outbox user no longer exists")
            sender.send(
                user.email, decrypt_code(settings, outbox.encrypted_code), outbox.event_type
            )
        except Exception as error:
            attempts = outbox.attempts + 1
            terminal = attempts >= settings.outbox_max_attempts
            delay = settings.outbox_retry_base_seconds * (2 ** max(0, attempts - 1))
            db.execute(
                update(EmailOutbox)
                .where(EmailOutbox.id == outbox_id, EmailOutbox.lock_token == token)
                .values(
                    attempts=attempts,
                    status="dead" if terminal else "retry",
                    last_error="delivery_failed",
                    locked_at=None,
                    lock_token=None,
                    next_attempt_at=now + timedelta(seconds=delay),
                )
            )
            db.commit()
            logger.warning(
                "SMTP delivery failed: outbox_id=%s error_type=%s error=%s",
                outbox_id,
                type(error).__name__,
                safe_smtp_error(error),
            )
            return False
        db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == outbox_id, EmailOutbox.lock_token == token)
            .values(
                attempts=outbox.attempts + 1,
                status="sent",
                last_error=None,
                locked_at=None,
                lock_token=None,
            )
        )
        db.commit()
        return True
    finally:
        db.close()
