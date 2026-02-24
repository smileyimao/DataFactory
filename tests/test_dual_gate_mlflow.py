#!/usr/bin/env python3
# tests/test_dual_gate_mlflow.py — 双门槛 + 真实邮件 + MLflow 验证
"""
用 3 条 mock 质检档案（95/60/30 分）验证：
1) 高≥dual_high → qualified（可选伪标签 stub）
2) 中 dual_low≤score<dual_high → blocked，并真实发送复核邮件（不 mock notifier）
3) 低 <dual_low → auto_reject，并调用 archiver 归档至废片库
4) 若 config 开启 MLflow，则记录批次 run（params + metrics）供 Dashboard 对比

QC 流程顺序（与 qc_engine 一致）：先重复检测（指纹+查重）→ 再视频不合格检测（抽帧质量）→ 再 YOLO（vision_scan）。
本脚本不跑真实指纹/产线/YOLO，仅用 mock 数据验证分流与邮件/归档/MLflow。

前置：config 中 email_setting 已配置；环境变量 EMAIL_PASSWORD 已设置（真实发邮件）。
"""
import os
import sys
import tempfile
import logging
from typing import List, Dict, Any, Tuple, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DUAL_GATE_HIGH = 90.0
DUAL_GATE_LOW = 50.0

MOCK_ITEMS = [
    {"score": 95.0, "filename": "high_95pts.mp4"},
    {"score": 60.0, "filename": "mid_60pts.mp4"},
    {"score": 30.0, "filename": "low_30pts.mp4"},
]


def _build_mock_qc_archive(source_archive_dir: str) -> List[Dict[str, Any]]:
    archive = []
    for m in MOCK_ITEMS:
        name = m["filename"]
        archive_path = os.path.join(source_archive_dir, name)
        archive.append({
            "filename": name,
            "archive_path": archive_path,
            "fingerprint": "",
            "score": m["score"],
            "passed": m["score"] >= 80.0,
            "is_duplicate": False,
            "duplicate_batch_id": None,
            "duplicate_created_at": None,
        })
    return archive


def _dual_gate_split(
    qc_archive: List[Dict],
    dual_high: float,
    dual_low: float,
) -> Tuple[List[Dict], List[Dict], List[Tuple[Dict, str]]]:
    qualified = [x for x in qc_archive if not x["is_duplicate"] and x["score"] >= dual_high]
    auto_reject = [(x, "quality") for x in qc_archive if not x["is_duplicate"] and x["score"] < dual_low]
    blocked = [x for x in qc_archive if x["is_duplicate"] or (dual_low <= x["score"] < dual_high)]
    return qualified, blocked, auto_reject


def _send_batch_qc_email(
    cfg: dict,
    qc_archive: List[Dict],
    batch_id: str,
    gate: float,
    report_path: str,
    extra_attachments: Optional[List[str]] = None,
) -> bool:
    from engines import notifier
    email_cfg = cfg.get("email_setting") or {}
    if not email_cfg:
        logger.warning("未配置 email_setting，跳过发邮件")
        return False
    body_lines = ["厂长您好，\n\n本批次检测已完成，结果如下（待处理物料清单）：\n\n"]
    for item in qc_archive:
        name = item["filename"]
        if item.get("is_duplicate"):
            body_lines.append(f"  - {name}  [重复] 曾于批次 {item.get('duplicate_batch_id', '')} 处理（{item.get('duplicate_created_at', '')}）")
        elif item["score"] >= gate:
            body_lines.append(f"  - {name}  [合格] 得分: {item['score']:.1f}%")
        else:
            body_lines.append(f"  - {name}  [不合格] 得分: {item['score']:.1f}% / 准入: {gate}%")
    body_lines.append("\n\n请根据控制台逐项复核 (y/n/all/none)，不放行的将移至废片库或冗余库。")
    body_lines.append("\n附件含：质量报告 + 批次工业报表。\n--------------------------------------------------\n本邮件由 Datafactory 自动生成（双门槛测试）。")
    return notifier.send_mail(
        email_cfg,
        f"【批次质检报告】待处理物料清单 - Batch:{batch_id}（双门槛测试）",
        "\n".join(body_lines),
        report_path=report_path if report_path and os.path.exists(report_path) else None,
        extra_attachments=extra_attachments,
    )


def _maybe_log_mlflow(
    cfg: dict,
    batch_id: str,
    file_count: int,
    qualified_count: int,
    blocked_count: int,
    auto_reject_count: int,
    industrial_report_path: Optional[str] = None,
) -> None:
    mf = cfg.get("mlflow") or {}
    if not mf.get("enabled"):
        return
    try:
        import mlflow
        if mf.get("tracking_uri"):
            mlflow.set_tracking_uri(mf["tracking_uri"])
        mlflow.set_experiment(mf.get("experiment_name", "datafactory"))
        with mlflow.start_run(run_name=f"test_dual_gate_{batch_id}"):
            mlflow.log_params({
                "batch_id": batch_id,
                "test_dual_gate": "true",
                "dual_gate_high": DUAL_GATE_HIGH,
                "dual_gate_low": DUAL_GATE_LOW,
            })
            mlflow.log_metrics({
                "file_count": file_count,
                "qualified_count": qualified_count,
                "blocked_count": blocked_count,
                "auto_reject_count": auto_reject_count,
            })
            if industrial_report_path and os.path.isfile(industrial_report_path):
                mlflow.log_artifact(industrial_report_path, artifact_path="industrial_report")
        logger.info("MLflow 已记录测试 run: test_dual_gate_%s", batch_id)
    except Exception as e:
        logger.warning("MLflow 记录失败（已跳过）: %s", e)


def run() -> int:
    from config import config_loader
    from core import archiver
    from core import time_utils

    config_loader.set_base_dir(PROJECT_ROOT)
    cfg = config_loader.load_config()
    paths = cfg.get("paths", {})
    cfg.setdefault("production_setting", {})["dual_gate_high"] = DUAL_GATE_HIGH
    cfg.setdefault("production_setting", {})["dual_gate_low"] = DUAL_GATE_LOW
    gate = float(cfg.get("production_setting", {}).get("pass_rate_gate", 80.0))

    batch_id = time_utils.now_toronto().strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory(prefix="test_dual_gate_") as tmp:
        source_archive_dir = os.path.join(tmp, "source")
        rejected_dir = os.path.join(tmp, "rejected")
        redundant_dir = os.path.join(tmp, "redundant")
        qc_dir = os.path.join(tmp, "reports")
        os.makedirs(source_archive_dir, exist_ok=True)
        os.makedirs(rejected_dir, exist_ok=True)
        os.makedirs(redundant_dir, exist_ok=True)
        os.makedirs(qc_dir, exist_ok=True)

        for m in MOCK_ITEMS:
            p = os.path.join(source_archive_dir, m["filename"])
            with open(p, "wb") as f:
                f.write(b"")
        report_path = os.path.join(qc_dir, "quality_report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("<html><body>双门槛测试报告</body></html>")

        cfg_tmp = dict(cfg)
        cfg_tmp["paths"] = dict(paths)
        cfg_tmp["paths"]["rejected_material"] = rejected_dir
        cfg_tmp["paths"]["redundant_archives"] = redundant_dir

        qc_archive = _build_mock_qc_archive(source_archive_dir)
        qualified, blocked, auto_reject = _dual_gate_split(qc_archive, DUAL_GATE_HIGH, DUAL_GATE_LOW)

        assert len(qualified) == 1 and qualified[0]["score"] == 95.0, "高分应 1 条 qualified"
        assert len(blocked) == 1 and blocked[0]["score"] == 60.0, "中分应 1 条 blocked"
        assert len(auto_reject) == 1 and auto_reject[0][0]["score"] == 30.0, "低分应 1 条 auto_reject"
        logger.info("断言通过: qualified=1(95), blocked=1(60), auto_reject=1(30)")

        for x in qualified:
            logger.info("伪标签 stub: 高分合格 %s -> 可写伪标签路径（本测试仅打 log）", x["filename"])

        from engines import report_tools as rt
        industrial_report_path = rt.generate_batch_industrial_report(
            qc_archive,
            qualified,
            blocked,
            auto_reject,
            batch_id,
            qc_dir,
            gate,
            dual_high=DUAL_GATE_HIGH,
            dual_low=DUAL_GATE_LOW,
        )
        # 预览：复制到项目内固定路径，便于本地打开查看效果
        preview_dir = os.path.join(PROJECT_ROOT, "tests", "output")
        os.makedirs(preview_dir, exist_ok=True)
        preview_path = os.path.join(preview_dir, "batch_industrial_report_preview.html")
        if os.path.isfile(industrial_report_path):
            with open(industrial_report_path, "r", encoding="utf-8") as f:
                with open(preview_path, "w", encoding="utf-8") as out:
                    out.write(f.read())
            print(f"📍 工业报表预览: file://{os.path.abspath(preview_path)}")
        extra = [industrial_report_path] if os.path.isfile(industrial_report_path) else None
        sent = _send_batch_qc_email(cfg_tmp, qc_archive, batch_id, gate, report_path, extra_attachments=extra)
        if sent:
            logger.info("邮件已真实发送，请查收收件箱确认")
        else:
            logger.warning("邮件未发送（未配置 email_setting 或 EMAIL_PASSWORD）")

        archiver.archive_rejected(cfg_tmp, auto_reject, batch_id)
        batch_fails = os.path.join(rejected_dir, f"Batch_{batch_id}_Fails")
        assert os.path.isdir(batch_fails), "废片库批次目录应已创建"
        logger.info("auto_reject 已归档至废片库: %s", batch_fails)

        _maybe_log_mlflow(
            cfg_tmp,
            batch_id,
            file_count=3,
            qualified_count=len(qualified),
            blocked_count=len(blocked),
            auto_reject_count=len(auto_reject),
            industrial_report_path=industrial_report_path,
        )

    print("✅ 双门槛测试完成：qualified(95)、blocked(60)+真实邮件、auto_reject(30)+归档、MLflow 已记录（若开启）")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
