# tests/unit/test_notifier.py — notifier.send_mail 单元测试
"""验证邮件发送逻辑，全程 mock SMTP，不真实发送。"""
import os
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit

EMAIL_CFG = {
    "smtp_server": "smtp.example.com",
    "smtp_port": 587,
    "sender": "factory@example.com",
    "receiver": "admin@example.com",
}


class TestSendMail:
    def test_returns_false_when_no_config(self):
        """email_cfg 为空时返回 False，不尝试连接。"""
        from utils.notifier import send_mail

        result = send_mail({}, "subject", "body")
        assert result is False

    def test_returns_false_when_no_password(self):
        """EMAIL_PASSWORD 未设置时返回 False。"""
        from utils.notifier import send_mail

        env = os.environ.copy()
        env.pop("EMAIL_PASSWORD", None)
        with patch.dict(os.environ, env, clear=True):
            result = send_mail(EMAIL_CFG, "subject", "body")
        assert result is False

    def test_sends_with_valid_config(self):
        """有效配置 + 密码时，调用 SMTP 并返回 True。"""
        from utils.notifier import send_mail

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {"EMAIL_PASSWORD": "secret"}):
            with patch("smtplib.SMTP", return_value=mock_smtp):
                result = send_mail(EMAIL_CFG, "Test Subject", "Test Body")

        assert result is True
        mock_smtp.sendmail.assert_called_once()

    def test_subject_and_body_in_message(self):
        """发送的邮件包含正确的 subject 和 body。"""
        from utils.notifier import send_mail

        captured = {}
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        def capture_sendmail(sender, receiver, msg_str):
            captured["msg"] = msg_str

        mock_smtp.sendmail.side_effect = capture_sendmail

        with patch.dict(os.environ, {"EMAIL_PASSWORD": "secret"}):
            with patch("smtplib.SMTP", return_value=mock_smtp):
                send_mail(EMAIL_CFG, "My Subject", "My Body")

        assert "My Subject" in captured.get("msg", "")
        assert "My Body" in captured.get("msg", "")

    def test_attachment_nonexistent_file_does_not_crash(self):
        """附件路径不存在时，邮件仍正常发送（附件跳过）。"""
        from utils.notifier import send_mail

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch.dict(os.environ, {"EMAIL_PASSWORD": "secret"}):
            with patch("smtplib.SMTP", return_value=mock_smtp):
                result = send_mail(
                    EMAIL_CFG, "subj", "body",
                    report_path="/nonexistent/report.html",
                )
        assert result is True

    def test_smtp_exception_returns_false(self):
        """SMTP 连接异常时返回 False，不向上抛异常。"""
        from utils.notifier import send_mail

        with patch.dict(os.environ, {"EMAIL_PASSWORD": "secret"}):
            with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
                result = send_mail(EMAIL_CFG, "subj", "body")
        assert result is False
