import os
import glob
import json
import smtplib
import argparse  # 👈 新增：命令行解析零件
from datetime import datetime
from core_engine import DataMachine
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart  # 👈 修复报错的核心零件
from email.mime.application import MIMEApplication # 👈 处理附件的核心零件

# ==========================================
# 1. 全局配置区（Datafactory 总调度室）
# ==========================================
INPUT_DIR = "raw_video"
WAREHOUSE = "data_warehouse"




# ==========================================
# 2. 邮件报警零件
# ==========================================


def send_quality_alert(pass_rate, report_path, gate_val):
    """
    [邮件报警零件 3.0]：从 DataMachine 获取脱敏配置并发送预警
    """
    # 1. 领电池（从 DataMachine 的大脑获取配置）
    cfg = DataMachine.email_config
    if not cfg:
        print("⚠️ [报警中断] YAML 配置文件中未发现 email_setting，请检查配置。")
        return

    # 从字典中提取参数 (对应你 YAML 里的键名)
    smtp_server = cfg.get('smtp_server')
    # iCloud 专用 587 端口，如果 YAML 没写就默认 587
    smtp_port = cfg.get('smtp_port', 587)
    sender_email = cfg.get('sender')
    receiver_email = cfg.get('receiver')
    auth_code = cfg.get('password')

    # --- 2. 构造邮件基础信息 ---
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"🚨 质量预警：当前全通率 {pass_rate:.2f}% (未达标)"

    body = f"""厂长您好，

当前批次试产质量未通过检测：
- 目标合格率门槛：{gate_val}%
- 实际全通率：{pass_rate:.2f}%

详细的“不合格品原因”请下载附件中的 HTML 报告查看。
--------------------------------------------------
本邮件由 Datafactory 3.0 自动生成。
    """
    msg.attach(MIMEText(body, 'plain'))

    # --- 3. 添加附件 (HTML 报告) ---
    try:
        if os.path.exists(report_path):
            with open(report_path, "rb") as f:
                # 提取文件名
                file_name = os.path.basename(report_path)
                part = MIMEApplication(f.read(), Name=file_name)
                part['Content-Disposition'] = f'attachment; filename="{file_name}"'
                msg.attach(part)
        else:
            print(f"⚠️ 找不到报告文件: {report_path}")
    except Exception as e:
        print(f"❌ 附件处理失败: {e}")

    # --- 4. 建立加密连接并发送 (针对 iCloud 优化) ---
    try:
        # 使用 standard SMTP + TLS (iCloud/Gmail 常用)
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # 启动加密传输
        server.login(sender_email, auth_code)
        server.sendmail(sender_email, [receiver_email], msg.as_string())
        server.quit()
        print(f"📧 [iCloud预警] 质量报告已成功发送至：{receiver_email}")
    except Exception as e:
        print(f"❌ 邮件发送失败，请检查授权码或网络: {e}")
# ==========================================
# 3. 智能总厂核心流程
# ==========================================
def run_smart_factory(limit_val, gate_val):

    # 🏭 先让大脑加载配置
    DataMachine.load_config("factory_config.yaml")

    #  🎯 确定试产时长 (Limit) ---
    if limit_val is None:
        final_limit = DataMachine.config.get("trial_limit_seconds", 5)
    else:
        final_limit = int(limit_val)

    # 🎯 确定最终使用的 gate 阈值 (三重保险逻辑)
    if gate_val is None:
        # 如果命令行没传 (--gate)，优先看 YAML，YAML 没写就用大脑里的保底值
        final_gate = DataMachine.config.get("pass_rate_gate", 80.0)
    else:
        # 如果命令行传了，就听命令行的 (最高指令)
        final_gate = float(gate_val)

    print(f"🚀 生产指令：试产时长 {final_limit}s | 准入标准 {final_gate}%")

    # --- A. 初始化批次 ---
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    pilot_dir = os.path.join(WAREHOUSE, f"Batch_{batch_id}", "1_Pilot_Room")
    mass_dir = os.path.join(WAREHOUSE, f"Batch_{batch_id}", "2_Mass_Production")

    # --- B. 盘点原材料 ---
    videos = []
    for ext in ('*.mp4', '*.MP4', '*.mov', '*.MOV'):
        videos.extend(glob.glob(os.path.join(INPUT_DIR, ext)))

    if not videos:
        print(f"❌ 警告：在 {INPUT_DIR} 中未发现任何视频物料！")
        return

    # --- C. 第一阶段：试产 (Pilot) ---
    print(f"\n🚀 [阶段 1] 启动试制车间 | 批次: {batch_id} | 试产配置: 每段 {final_limit}s")
    DataMachine.start_production(videos, pilot_dir, batch_id, limit_seconds=final_limit)

    # --- D. 逻辑闸口：质量评估 ---
    with open(os.path.join(pilot_dir, "manifest.json"), 'r', encoding='utf-8') as f:
        results = json.load(f)

    total = len(results)
    normal = len([item for item in results if item['env'] == "Normal"])
    pass_rate = (normal / total) * 100 if total > 0 else 0

    print(f"📊 试产自检看板：全通率 {pass_rate:.2f}% (合格:{normal}/总计:{total})")

    # --- E. 决策引擎 ---
    start_mass_prod = False # noqa

    if pass_rate >= final_gate:
        print(f"✅ 质量达标（阈值 {final_gate}%），系统自动转入大规模制造...")
        start_mass_prod = True
    else:
        print(f"⚠️ 预警：全通率低于设定的 {final_gate}%！")
        # 调用报警函数（假设你已定义）
        send_quality_alert(pass_rate, os.path.join(pilot_dir, 'quality_report.html'), final_gate)

        print(f"📍 请查看报告: file://{os.path.abspath(os.path.join(pilot_dir, 'quality_report.html'))}")

        # --- 💥 核心防呆修改 💥 ---
        while True:
            confirm = input("\n🏭 质量未达标！厂长，是否强行开启全量量产？(y/n): ").strip().lower()

            if confirm == 'y':
                print("🚀 收到指令！厂长授权强制生产...")
                start_mass_prod = True  # 标记为 True，让流程走到 F 阶段
                break

            elif confirm == 'n':
                print("🛑 指令取消。产线已停机，请调整物料或参数后再试。")
                return

            else:
                print("⚠️ 警告：检测到无效输入。请输入 'y' 确认量产，或 'n' 停止生产。")

    # --- F. 第二阶段：大规模制造 (Mass Production) ---
    if start_mass_prod:
        print(f"\n🏭 [阶段 2] 启动大规模制造流水线（全量数据）...")
        # 注意：这里要使用前面定义的 videos 和 mass_dir
        count = DataMachine.start_production(
            video_paths=videos,
            target_dir=mass_dir,
            batch_id=batch_id,
            limit_seconds=None
        )
        print(f"\n🏆 量产报捷！共加工 {count} 张样图，成品存放在: {os.path.abspath(mass_dir)}")


# ==========================================
# 4. 命令行指挥台入口
# ==========================================
if __name__ == "__main__":
    # 配置命令行参数
    parser = argparse.ArgumentParser(description="Datafactory 自动化调度指挥系统")

    # --limit: 试产切多少秒
    parser.add_argument("--limit", type=int, default=None, help="试产切片秒数 (默认: 5)")
    # --gate: 全通率阈值
    parser.add_argument("--gate", type=int, default=None, help="量产准入全通率阈值 (默认: 80)")

    args = parser.parse_args()

    # 带着指令启动工厂
    run_smart_factory(limit_val=args.limit, gate_val=args.gate)