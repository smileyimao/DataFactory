# utils/notifier.py — 邮件通知，只发送不决策（P2：重试配置驱动）
import os
import smtplib
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _attach_file(msg: MIMEMultipart, path: str) -> None:
    """将单个文件加入邮件为附件。"""
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(path)}"'
            msg.attach(part)
    except Exception as e:
        logger.warning("附件处理失败: %s", e)


def send_mail(
    email_cfg: Dict[str, Any],
    subject: str,
    body: str,
    report_path: Optional[str] = None,
    extra_attachments: Optional[List[str]] = None,
    password_env_key: str = "EMAIL_PASSWORD",
) -> bool:
    """
    发送邮件。email_cfg 需含 smtp_server, smtp_port(可选), sender, receiver。
    密码从 os.environ[password_env_key] 读取；未配置则跳过并返回 False。
    report_path 与 extra_attachments 中的路径会作为附件一并发送。
    """
    if not email_cfg:
        return False
    auth = os.getenv(password_env_key)
    if not auth:
        logger.warning("邮件未发送：未配置 %s（请在 .env 中设置邮箱授权码）", password_env_key)
        return False
    msg = MIMEMultipart()
    msg["From"] = email_cfg.get("sender", "")
    msg["To"] = email_cfg.get("receiver", "")
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    if report_path:
        _attach_file(msg, report_path)
    for path in extra_attachments or []:
        _attach_file(msg, path)
    max_retries = int(email_cfg.get("max_retries", 1))
    retry_delay = float(email_cfg.get("retry_delay_seconds", 5))
    last_err = None
    for attempt in range(1, max_retries + 1):
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
            last_err = e
            if attempt < max_retries:
                logger.warning("邮件发送失败 (attempt %d/%d)，%s 秒后重试: %s", attempt, max_retries, retry_delay, e)
                time.sleep(retry_delay)
            else:
                logger.exception("邮件发送最终失败 (%d 次尝试): %s", max_retries, e)
                print(f"⚠️ [邮件] 发送失败: {e}")
    return False
