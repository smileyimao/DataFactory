#!/usr/bin/env python3
"""测试邮件配置：检查 .env 加载与 SMTP 连接。"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

def main():
    pw = os.getenv("EMAIL_PASSWORD")
    if not pw:
        print("❌ EMAIL_PASSWORD 未配置（.env 中未设置或未加载）")
        return 1
    print("✓ EMAIL_PASSWORD 已加载")

    from config import config_loader
    cfg, _ = config_loader.get_config_and_paths(BASE_DIR)
    email_cfg = cfg.get("email_setting", {})
    if not email_cfg:
        print("❌ email_setting 未配置")
        return 1
    print(f"✓ SMTP: {email_cfg.get('smtp_server')}:{email_cfg.get('smtp_port')}")
    print(f"  发件: {email_cfg.get('sender')} -> {email_cfg.get('receiver')}")

    from engines import notifier
    ok = notifier.send_mail(
        email_cfg,
        "【DataFactory 测试】邮件配置验证",
        "这是一封测试邮件。若收到则说明配置正确。",
    )
    if ok:
        print("✓ 邮件已发送，请查收收件箱（含垃圾邮件）")
        return 0
    print("❌ 邮件发送失败，请查看上方错误信息")
    return 1

if __name__ == "__main__":
    sys.exit(main())
