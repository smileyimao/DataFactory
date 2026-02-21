# engines/notifier.py — 邮件通知，只发送不决策
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def send_mail(
    email_cfg: Dict[str, Any],
    subject: str,
    body: str,
    report_path: Optional[str] = None,
    password_env_key: str = "EMAIL_PASSWORD",
) -> bool:
    """
    发送邮件。email_cfg 需含 smtp_server, smtp_port(可选), sender, receiver。
    密码从 os.environ[password_env_key] 读取；未配置则跳过并返回 False。
    """
    if not email_cfg:
        return False
    auth = os.getenv(password_env_key)
    if not auth:
        return False
    msg = MIMEMultipart()
    msg["From"] = email_cfg.get("sender", "")
    msg["To"] = email_cfg.get("receiver", "")
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    if report_path and os.path.exists(report_path):
        try:
            with open(report_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(report_path))
                part["Content-Disposition"] = f'attachment; filename="{os.path.basename(report_path)}"'
                msg.attach(part)
        except Exception as e:
            logger.warning("附件处理失败: %s", e)
    try:
        port = int(email_cfg.get("smtp_port", 587))
        server = smtplib.SMTP(email_cfg.get("smtp_server", ""), port)
        server.starttls()
        server.login(email_cfg.get("sender", ""), auth)
        server.sendmail(email_cfg.get("sender", ""), [email_cfg.get("receiver", "")], msg.as_string())
        server.quit()
        logger.info("邮件已发送至: %s", email_cfg.get("receiver"))
        return True
    except Exception as e:
        logger.exception("邮件发送失败: %s", e)
        return False
