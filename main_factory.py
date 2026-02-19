import os
import glob
import json
import smtplib
import shutil
import argparse  # 👈 新增：命令行解析零件
from datetime import datetime
from core_engine import DataMachine
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart  # 👈 修复报错的核心零件
from email.mime.application import MIMEApplication # 👈 处理附件的核心零件
from inputimeout import inputimeout, TimeoutOccurred
from db_manager import check_reproduce, record_production

# ==========================================
# 1. 全局配置区（Datafactory_v1.0 总调度室）
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
    auth_code = os.getenv('EMAIL_PASSWORD')

    if not auth_code:
        print("\n💡 [提醒]：检测到未配置环境变量 EMAIL_PASSWORD。")
        print("   -> 本次运行将跳过邮件发送环节，其他处理流程正常继续。")
        print("   -> 若需发送报告，请在 PyCharm 运行配置中设置该变量。\n")

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
    # 【核心逻辑】：只有拿到了 auth_code，才去撞门发邮件
    if auth_code:
        try:
            # 使用 standard SMTP + TLS (iCloud/Gmail 常用)
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()  # 启动加密传输
            server.login(sender_email, auth_code)
            server.sendmail(sender_email, [receiver_email], msg.as_string())
            server.quit()
            print(f"📧 [iCloud预警] 质量报告已成功发送至：{receiver_email}")
        except Exception as e:
            # 即使报错（比如网络断了），也只是打印错误，不影响主流程
            print(f"❌ 邮件发送失败，请检查授权码或网络: {e}")
    else:
        # 如果 auth_code 是 None（即没设环境变量），就走这条路
        print("⏭️  [跳过发送]：未检测到环境变量 EMAIL_PASSWORD，已自动跳过邮件预警环节。")

# ==========================================
# 3. 智能总厂核心流程
# ==========================================
def run_smart_factory(limit_val=None, gate_val=None, file_md5=None):
    # 🏭 1. 先让大脑加载配置（这一步建立了基准）
    DataMachine.load_config("factory_config.yaml")

    # --- 🎯 2. 确定试产时长 (Limit) ---
    # 逻辑：命令行(args.limit) > YAML配置 > 硬编码默认值(5)
    if limit_val is not None:
        try:
            final_limit = int(limit_val)  # 强制转换，防止传进来的是字符串
        except (ValueError, TypeError):
            print(f"⚠️ [输入异常] limit_val '{limit_val}' 无效，将回退至系统默认值")
            final_limit = DataMachine.config.get("trial_limit_seconds", 5)
    else:
        final_limit = DataMachine.config.get("trial_limit_seconds", 5)

    # --- 🎯 3. 确定最终使用的 gate 阈值 ---
    # 逻辑：命令行(args.gate) > YAML配置 > 硬编码默认值(80.0)
    if gate_val is not None:
        try:
            final_gate = float(gate_val)  # 强制转换，兼容 60 和 60.0
        except (ValueError, TypeError):
            print(f"⚠️ [输入异常] gate_val '{gate_val}' 无效，将回退至系统默认值")
            final_gate = DataMachine.config.get("pass_rate_gate", 80.0)
    else:
        final_gate = DataMachine.config.get("pass_rate_gate", 80.0)

    # 4. 这里的打印就是你的“仪表盘”，确认参数覆盖是否生效
    print(f"🚀 [指挥部] 生产指令已确认：")
    print(f"   ├─ 生产时长：{final_limit}s")
    print(f"   └─ 准入标准：{final_gate}%")

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

    # --- D. 物料入库：将原始视频移动到 Batch 文件夹中 ---
    # 在 Batch 目录下创建一个 '0_Source_Video' 文件夹
    # 这样你的 Batch 文件夹里就有：1_Pilot, 2_Mass, 0_Source
    source_archive_dir = os.path.join(WAREHOUSE, f"Batch_{batch_id}", "0_Source_Video")
    os.makedirs(source_archive_dir, exist_ok=True)

    for v_path in videos:
        try:
            # 搬运原始视频
            shutil.move(v_path, os.path.join(source_archive_dir, os.path.basename(v_path)))
            print(f"📦 [归档成功]: 原始视频 {os.path.basename(v_path)} 已存入 0_Source_Video")
        except Exception as e:
            print(f"⚠️ [归档失败]: {v_path} 搬运出错: {e}")

    # --- E. 逻辑闸口：质量评估 ---
    with open(os.path.join(pilot_dir, "manifest.json"), 'r', encoding='utf-8') as f:
        results = json.load(f)

    total = len(results)
    normal = len([item for item in results if item['env'] == "Normal"])
    pass_rate = (normal / total) * 100 if total > 0 else 0

    print(f"📊 试产自检看板：全通率 {pass_rate:.2f}% (合格:{normal}/总计:{total})")

    # --- F. 决策引擎 ---
    start_mass_prod = False # noqa

    # 👈 [新增]：查账逻辑。看看这个指纹之前量产成功过吗？
    history_batch = check_reproduce(file_md5) if file_md5 else None

    # 修改判断逻辑：质量达标 且 不是重复物料，才自动量产
    if pass_rate >= final_gate and not history_batch:
        print(f"✅ 质量达标（阈值 {final_gate}%），且是新物料，系统自动转入大规模制造...")
        start_mass_prod = True
    else:
        # 进入人工干预环节
        if history_batch:
            print(f"⚠️  [档案馆拦截]：检测到该文件已在批次 {history_batch} 中完成过量产！")
        else:
            print(f"⚠️  预警：全通率 ({pass_rate:.2f}%) 低于设定的 {final_gate}%！")

        # 发送报警邮件
        report_path = os.path.join(pilot_dir, 'quality_report.html')
        send_quality_alert(pass_rate, report_path, final_gate)

        print(f"📍 请查看报告: file://{os.path.abspath(report_path)}")
        print("⏳ [系统进入决策等待] 10分钟内无有效指令将自动判定为放弃/跳过。")

        while True:
            try:
                # 👈 [防呆提示语优化]
                reason = "重复物料" if history_batch else "质量不合格"
                prompt = f"\n🏭 厂长，检测到【{reason}】。是否【强行】开启全量量产？(y/n) [10min后自动选n]: "
                user_input = inputimeout(prompt=prompt, timeout=600).strip().lower()

                if user_input == 'y':
                    print("🚀 厂长现场授权：强制启动全量生产！")
                    start_mass_prod = True
                    break
                elif user_input == 'n' or user_input == "":
                    print("🛑 厂长指令：放弃本次任务。")
                    return  # 彻底结束
                else:
                    print(f"⚠️  无效输入 '{user_input}'，请输入 y 或 n。")
            except TimeoutOccurred:
                print("\n\n⏰ [超时熔断] 10 分钟未响应，系统默认放弃。")
                return

    # --- G. 第二阶段：大规模制造 (Mass Production) ---
    if start_mass_prod:
        # 💡 厂长补丁：因为视频被挪到了 0_Source_Video，更新一下路径列表
        new_video_paths = [os.path.join(source_archive_dir, os.path.basename(v)) for v in videos]

        print(f"\n🏭 [阶段 2] 启动大规模制造流水线（全量数据）...")
        count = DataMachine.start_production(
            video_paths=new_video_paths,  # 👈 使用更新后的路径
            target_dir=mass_dir,
            batch_id=batch_id,
            limit_seconds=None
        )
        print(f"\n🏆 量产报捷！共加工 {count} 张样图，成品存放在: {os.path.abspath(mass_dir)}")
        # 👈 [新增]：量产成功，向档案馆记账
        if file_md5:
            record_production(batch_id, file_md5, pass_rate, "SUCCESS")
            print(f"📔 [档案入库]: 批次 {batch_id} 的指纹已存入历史大账本。")


# ==========================================
# 4. 命令行指挥台入口
# ==========================================
if __name__ == "__main__":
    # 配置命令行参数
    parser = argparse.ArgumentParser(description="Datafactory 自动化调度指挥系统")

    # 1. 改为 float，这样它就能认 60.0 或者 60 了
    parser.add_argument("--limit", type=int, default=None, help="试产切片秒数")
    parser.add_argument("--gate", type=float, default=None, help="准入阈值 (例如: 60.0)")

    args = parser.parse_args()

    # 带着指令启动工厂
    run_smart_factory(limit_val=args.limit, gate_val=args.gate)