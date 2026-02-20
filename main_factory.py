import os
import glob
import json
import logging
import smtplib
import shutil
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from core_engine import DataMachine
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from inputimeout import inputimeout, TimeoutOccurred
from db_manager import get_reproduce_info, record_production, get_file_md5

# ==========================================
# 1. 全局配置区
# ==========================================
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(_BASE_DIR, "raw_video")
WAREHOUSE = os.path.join(_BASE_DIR, "data_warehouse")
REJECTED_DIR = os.path.join(_BASE_DIR, "rejected_material")
REDUNDANT_DIR = os.path.join(_BASE_DIR, "redundant_archives")

load_dotenv()
logger = logging.getLogger(__name__)

def now_toronto():
    return datetime.now(ZoneInfo("America/Toronto"))

# ==========================================
# 2. 邮件（密码仅从 os.getenv 读取）
# ==========================================
def _send_mail(subject, body, report_path=None):
    if not DataMachine.email_config:
        DataMachine.load_config(os.path.join(_BASE_DIR, "factory_config.yaml"))
    cfg = DataMachine.email_config
    if not cfg:
        print("⚠️ [报警中断] YAML 中未发现 email_setting。")
        return
    auth_code = os.getenv('EMAIL_PASSWORD')
    if not auth_code:
        print("\n💡 [提醒]：未配置 EMAIL_PASSWORD，本次跳过邮件发送。\n")
        return
    msg = MIMEMultipart()
    msg['From'] = cfg.get('sender')
    msg['To'] = cfg.get('receiver')
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    if report_path and os.path.exists(report_path):
        try:
            with open(report_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(report_path))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(report_path)}"'
                msg.attach(part)
        except Exception as e:
            print(f"❌ 附件处理失败: {e}")
    try:
        server = smtplib.SMTP(cfg.get('smtp_server'), cfg.get('smtp_port', 587))
        server.starttls()
        server.login(cfg.get('sender'), auth_code)
        server.sendmail(cfg.get('sender'), [cfg.get('receiver')], msg.as_string())
        server.quit()
        print(f"📧 邮件已发送至：{cfg.get('receiver')}")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")


def send_batch_qc_report(batch_id, qc_archive, gate_val, report_path=None):
    """【批次质检报告】待处理物料清单 - Batch:[ID]。每行：合格 / 不合格 得分/准入 / 重复 曾于批次。"""
    lines = []
    for item in qc_archive:
        name = item["filename"]
        score = item["score"]
        if item.get("is_duplicate"):
            lines.append(f"  - {name}  [重复] 曾于批次 {item.get('duplicate_batch_id', '')} 处理（{item.get('duplicate_created_at', '')}）")
        elif item["passed"]:
            lines.append(f"  - {name}  [合格]")
        else:
            lines.append(f"  - {name}  [不合格] 得分: {score:.1f}% / 准入: {gate_val}%")
    body = "厂长您好，\n\n本批次检测已完成，结果如下（待处理物料清单）：\n\n" + "\n".join(lines)
    body += "\n\n请根据控制台逐项复核 (y/n/all/none)，不放行的将移至废片库或冗余库。\n--------------------------------------------------\n本邮件由 Datafactory 自动生成。"
    _send_mail(f"【批次质检报告】待处理物料清单 - Batch:{batch_id}", body, report_path)


def send_alert_line(pass_rate, report_path, gate_val):
    body = f"""厂长您好，

当前批次试产质量未通过检测（产线报警）：
- 目标合格率门槛：{gate_val}%
- 实际全通率：{pass_rate:.2f}%

详细不合格原因请查看附件 HTML 报告。
--------------------------------------------------
本邮件由 Datafactory 自动生成。
"""
    _send_mail("【产线报警】质量未达标", body, report_path)


def send_alert_duplicate(report_path, processed_at):
    body = f"""厂长您好，

【重复投产确认】

该物料指纹已于 {processed_at} 处理过，请厂长上线确认重复投产情况。

本批次质量报告见附件（如有）。
--------------------------------------------------
本邮件由 Datafactory 自动生成。
"""
    _send_mail("【重复投产确认】重复物料", body, report_path)


def send_duplicate_confirm_request(processed_at):
    body = f"""厂长您好，

【重复投产确认请求】

该物料指纹已于 {processed_at} 处理过，请厂长上线确认重复投产情况。
请选择 [y] 强行重产 或 [n] 移入冗余库（10 分钟内未响应将自动移入冗余库）。
--------------------------------------------------
本邮件由 Datafactory 自动生成。
"""
    _send_mail("【重复投产确认请求】", body)


# ==========================================
# 3. 集中质检复核流程
# ==========================================
VALID_REVIEW_INPUTS = frozenset({"y", "n", "all", "none"})


def _ask_review_one(prompt_suffix, timeout=600):
    """循环询问直到得到 y/n/all/none 或超时。超时返回 'none'，并记录 Timeout Emergency Stop。"""
    while True:
        try:
            user_input = inputimeout(prompt=prompt_suffix, timeout=timeout).strip().lower()
        except TimeoutOccurred:
            print("\n检测到响应超时，已自动执行 [none] 策略，物料已移至废片库。")
            logger.warning("Timeout Emergency Stop: 600s 无有效输入，已自动执行 [none] 策略，物料已移至废片库。")
            return "none"
        if user_input in VALID_REVIEW_INPUTS:
            logger.info("厂长决策指令: %s", user_input)
            return user_input
        logger.warning("无效指令 [%s]，要求重新输入 (y/n/all/none)", user_input or "(空回车)")
        print(f"⚠️ 无效指令 [{user_input or '(空回车)'}]！请重新输入 (y/n/all/none): ")


def run_smart_factory(limit_val=None, gate_val=None, file_md5=None, video_paths=None):
    """
    集中质检复核模式：连续完成当前 Batch 所有视频检测 → 质检档案 → 一封体检报告邮件 → 仅对不合格项交互复核 (y/n/all/none)。
    video_paths: 若传入则只处理该列表（须为绝对路径），不扫描 raw_video。
    """
    DataMachine.load_config(os.path.join(_BASE_DIR, "factory_config.yaml"))

    if limit_val is not None:
        try:
            final_limit = int(limit_val)
        except (ValueError, TypeError):
            final_limit = DataMachine.config.get("trial_limit_seconds", 5)
    else:
        final_limit = DataMachine.config.get("trial_limit_seconds", 5)

    if gate_val is not None:
        try:
            final_gate = float(gate_val)
        except (ValueError, TypeError):
            final_gate = DataMachine.config.get("pass_rate_gate", 80.0)
    else:
        final_gate = DataMachine.config.get("pass_rate_gate", 80.0)

    print(f"🚀 [指挥部] 生产指令已确认：生产时长 {final_limit}s，准入标准 {final_gate}%")

    batch_id = now_toronto().strftime("%Y%m%d_%H%M%S")
    pilot_dir = os.path.join(WAREHOUSE, f"Batch_{batch_id}", "1_Pilot_Room")
    mass_dir = os.path.join(WAREHOUSE, f"Batch_{batch_id}", "2_Mass_Production")
    source_archive_dir = os.path.join(WAREHOUSE, f"Batch_{batch_id}", "0_Source_Video")

    if video_paths:
        videos = [os.path.abspath(p) for p in video_paths if os.path.isfile(p)]
    else:
        videos = []
        for ext in ('*.mp4', '*.MP4', '*.mov', '*.MOV'):
            videos.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
        videos = [os.path.abspath(v) for v in videos]

    if not videos:
        if video_paths:
            print(f"❌ 警告：指定的视频路径无效或文件不存在：{video_paths}")
        else:
            print(f"❌ 警告：未发现视频物料：{os.path.abspath(INPUT_DIR)}")
        return

    # 先算指纹（移动前），用于质检档案与归档
    path_to_md5 = {}
    for v in videos:
        fp = get_file_md5(v) or ""
        path_to_md5[v] = fp
        logger.info("指纹采集结果: 文件=%s 指纹=%s", os.path.basename(v), fp[:16] + "..." if len(fp) > 16 else fp)

    # 阶段 1：连续完成当前 Batch 所有视频检测（不中断）
    os.makedirs(pilot_dir, exist_ok=True)
    print(f"\n🚀 [阶段 1] 启动试制车间 | 批次: {batch_id} | 试产配置: 每段 {final_limit}s")
    DataMachine.start_production(videos, pilot_dir, batch_id, limit_seconds=final_limit)

    os.makedirs(source_archive_dir, exist_ok=True)
    for v_path in videos:
        dest = os.path.join(source_archive_dir, os.path.basename(v_path))
        try:
            logger.info("Moving [%s] to [%s] due to [Batch archive 0_Source_Video]", os.path.basename(v_path), os.path.abspath(dest))
            shutil.move(v_path, dest)
            print(f"📦 [归档成功]: {os.path.basename(v_path)} -> 0_Source_Video")
        except Exception as e:
            logger.exception("归档失败: %s -> %s", v_path, e)
            print(f"⚠️ [归档失败]: {v_path} -> {e}")

    # 质检档案：按文件汇总得分
    with open(os.path.join(pilot_dir, "manifest.json"), 'r', encoding='utf-8') as f:
        results = json.load(f)

    from collections import defaultdict
    by_source = defaultdict(lambda: {"normal": 0, "total": 0})
    for r in results:
        src = r.get("source", "")
        by_source[src]["total"] += 1
        if r.get("env") == "Normal":
            by_source[src]["normal"] += 1

    qc_archive = []
    for v_path in videos:
        bname = os.path.basename(v_path)
        stat = by_source.get(bname, {"normal": 0, "total": 0})
        total = stat["total"] or 1
        score = (stat["normal"] / total) * 100
        passed = score >= final_gate
        archive_path = os.path.join(source_archive_dir, bname)
        fp = path_to_md5.get(v_path, "")
        rep = get_reproduce_info(fp) if fp else None
        is_dup = rep is not None
        qc_archive.append({
            "filename": bname,
            "archive_path": archive_path,
            "fingerprint": fp,
            "score": score,
            "passed": passed,
            "is_duplicate": is_dup,
            "duplicate_batch_id": rep["batch_id"] if rep else None,
            "duplicate_created_at": rep.get("created_at") if rep else None,
        })
        status = "合格" if passed else "不合格"
        if is_dup:
            logger.info("质量得分: 文件名=%s 指纹=%s 分数=%.2f%% 状态=重复 曾于批次=%s", bname, (fp or "")[:16], score, rep.get("batch_id", ""))
        else:
            logger.info("质量得分: 文件名=%s 指纹=%s 分数=%.2f%% 状态=%s 准入=%.1f%%", bname, (fp or "")[:16], score, status, final_gate)

    print(f"📊 试产自检看板：批次 {batch_id} 共 {len(qc_archive)} 个文件，准入标准 {final_gate}%")

    # 被拦 = 不合格（质量）或 重复；合格且不重复 = 自动放行
    qualified = [x for x in qc_archive if x["passed"] and not x["is_duplicate"]]
    blocked = [x for x in qc_archive if not (x["passed"] and not x["is_duplicate"])]

    report_path = os.path.join(pilot_dir, "quality_report.html")
    send_batch_qc_report(batch_id, qc_archive, final_gate, report_path)
    print(f"📍 报告: file://{os.path.abspath(report_path)}")

    to_produce = list(qualified)
    to_reject = []  # 每个元素为 (item, reason: 'quality'|'duplicate')

    # 交互复核：仅针对被拦项，说明原因（不合格 得分/准入 或 重复 曾于批次），y/n/all/none
    if blocked:
        print("\n⏳ [交互复核] 仅接受 y / n / all / none；600 秒无响应将自动执行 [none]。")
        remaining = list(blocked)
        while remaining:
            item = remaining[0]
            name = item["filename"]
            if item["is_duplicate"]:
                reason = f"重复 曾于批次 {item.get('duplicate_batch_id', '')} ({item.get('duplicate_created_at', '')})"
            else:
                reason = f"不合格 得分: {item['score']:.1f}% / 准入: {final_gate}%"
            prompt = f"\n当前: {name} - {reason}\n  [y]放行 [n]丢弃 (y/n/all/none) [600s后默认none]: "
            cmd = _ask_review_one(prompt, timeout=600)
            if cmd == "y":
                to_produce.append(item)
                remaining.pop(0)
            elif cmd == "n":
                to_reject.append((item, "duplicate" if item["is_duplicate"] else "quality"))
                remaining.pop(0)
            elif cmd == "all":
                to_produce.extend(remaining)
                remaining.clear()
                print("已选择 [all]，剩余被拦项全部放行。")
            else:
                for x in remaining:
                    to_reject.append((x, "duplicate" if x["is_duplicate"] else "quality"))
                remaining.clear()
                print("已选择 [none]，剩余被拦项全部丢弃（不合格→废片库，重复→冗余库）。")

    # 丢弃项：重复 → redundant_archives（原名）；不合格 → rejected_material/Batch_ID_Fails（原名_得分pts）
    os.makedirs(REJECTED_DIR, exist_ok=True)
    os.makedirs(REDUNDANT_DIR, exist_ok=True)
    batch_fails_dir = os.path.join(REJECTED_DIR, f"Batch_{batch_id}_Fails")
    os.makedirs(batch_fails_dir, exist_ok=True)
    for item, reason in to_reject:
        src = item["archive_path"]
        if not os.path.isfile(src):
            continue
        name = item["filename"]
        if reason == "duplicate":
            dest = os.path.join(REDUNDANT_DIR, name)
            dest_abs = os.path.abspath(dest)
            logger.info("Moving [%s] to [%s] due to [Duplicate -> redundant_archives]", name, dest_abs)
            try:
                shutil.move(src, dest)
                print(f"📦 [冗余库] {name} 已移入 redundant_archives")
            except Exception as e:
                logger.exception("冗余库移动失败: %s -> %s", name, e)
                print(f"⚠️ [冗余库] 移动失败: {name} -> {e}")
        else:
            base, ext = os.path.splitext(name)
            new_name = f"{base}_{item['score']:.0f}pts{ext}"
            dest = os.path.join(batch_fails_dir, new_name)
            dest_abs = os.path.abspath(dest)
            logger.info("Moving [%s] to [%s] due to [Rejected material _XXpts to Batch_Fails]", name, dest_abs)
            try:
                shutil.move(src, dest)
                print(f"📦 [废片库] {name} -> {new_name}")
            except Exception as e:
                logger.exception("废片移动失败: %s -> %s", name, e)
                print(f"⚠️ [废片库] 移动失败: {name} -> {e}")

    # 阶段 2：仅对 to_produce 量产
    if not to_produce:
        print("🛑 无物料进入量产，本批次结束。")
        return

    new_video_paths = [x["archive_path"] for x in to_produce if os.path.isfile(x["archive_path"])]
    if not new_video_paths:
        print("❌ 量产列表为空或文件已移动，跳过量产。")
        return

    print(f"\n🏭 [阶段 2] 大规模制造流水线（共 {len(new_video_paths)} 个文件）...")
    count = DataMachine.start_production(
        video_paths=new_video_paths,
        target_dir=mass_dir,
        batch_id=batch_id,
        limit_seconds=None,
    )
    print(f"🏆 量产报捷！共加工 {count} 张样图，成品存放在: {os.path.abspath(mass_dir)}")

    ts = now_toronto().strftime("%Y-%m-%d %H:%M:%S")
    for x in to_produce:
        if x.get("fingerprint"):
            record_production(batch_id, x["fingerprint"], x["score"], "SUCCESS", created_at=ts)
    print(f"📔 [档案入库] 批次 {batch_id} 的指纹已存入历史大账本。")


# ==========================================
# 4. 命令行入口
# ==========================================
if __name__ == "__main__":
    import log_setup
    log_setup.setup_logging(_BASE_DIR)
    parser = argparse.ArgumentParser(description="Datafactory 集中质检复核")
    parser.add_argument("--limit", type=int, default=None, help="试产切片秒数")
    parser.add_argument("--gate", type=float, default=None, help="准入阈值")
    args = parser.parse_args()
    run_smart_factory(limit_val=args.limit, gate_val=args.gate)
