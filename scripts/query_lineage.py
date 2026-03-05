#!/usr/bin/env python3
# scripts/query_lineage.py — v3 血缘查询：Batch_ID → raw → QC → refinery/inspection → labeled → training
"""
查询数据血缘：batch_lineage、label_import。
用法:
  python scripts/query_lineage.py                    # 列出最近批次
  python scripts/query_lineage.py --batch Batch_xxx  # 查询指定批次
  python scripts/query_lineage.py --import Import_xxx # 查询标注回传
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import config_loader
from db import db_connection, db_tools


def _list_recent_batches(db_url: str, limit: int = 10) -> None:
    """列出最近批次血缘。"""
    if not db_url:
        print("❌ 数据库未配置，请设置 DATABASE_URL 环境变量")
        return
    p = db_connection.ph(db_url)
    try:
        conn = db_connection.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            "SELECT batch_id, batch_base, source_dir, refinery_dir, inspection_dir, created_at "
            f"FROM batch_lineage ORDER BY created_at DESC LIMIT {p}",
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        if not rows:
            print("暂无 batch_lineage 记录")
            return
        print(f"📊 最近 {len(rows)} 条批次血缘:\n")
        for r in rows:
            batch_id, batch_base, src, ref, insp, created = r
            print(f"  {batch_id}  @ {created}")
            print(f"    raw → {src or '—'}")
            print(f"    refinery → {ref or '—'}")
            print(f"    inspection → {insp or '—'}")
            print()
    except Exception as e:
        print(f"❌ 查询失败: {e}")


def _show_batch(db_url: str, batch_id: str) -> None:
    """展示单批次血缘详情。"""
    info = db_tools.get_batch_lineage(db_url, batch_id)
    if not info:
        print(f"❌ 未找到批次 {batch_id}")
        return
    print(f"📊 批次血缘: {info['batch_id']}\n")
    print(json.dumps(info, indent=2, ensure_ascii=False))


def _show_train(db_url: str, run_id: str) -> None:
    """展示模型训练血缘。"""
    if not db_url:
        print("❌ 数据库未配置，请设置 DATABASE_URL 环境变量")
        return
    p = db_connection.ph(db_url)
    try:
        conn = db_connection.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            f"SELECT run_id, model_name, registry_uri, base_model, training_dir, "
            f"import_ids, dataset_size, epochs, map50, map50_95, precision, recall, "
            f"mlflow_run_id, created_at "
            f"FROM model_train WHERE run_id = {p}",
            (run_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            print(f"❌ 未找到训练记录 {run_id}")
            return
        keys = ["run_id", "model_name", "registry_uri", "base_model", "training_dir",
                "import_ids", "dataset_size", "epochs", "map50", "map50_95",
                "precision", "recall", "mlflow_run_id", "created_at"]
        d = dict(zip(keys, row))
        if d.get("import_ids"):
            try:
                d["import_ids"] = json.loads(d["import_ids"])
            except (json.JSONDecodeError, TypeError):
                pass
        print(f"📊 模型训练血缘: {d['run_id']}\n")
        print(json.dumps(d, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ 查询失败: {e}")


def _list_recent_trains(db_url: str, limit: int = 10) -> None:
    """列出最近的模型训练记录。"""
    if not db_url:
        print("❌ 数据库未配置，请设置 DATABASE_URL 环境变量")
        return
    p = db_connection.ph(db_url)
    try:
        conn = db_connection.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            f"SELECT run_id, model_name, registry_uri, map50, map50_95, dataset_size, created_at "
            f"FROM model_train ORDER BY created_at DESC LIMIT {p}",
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        if not rows:
            print("暂无 model_train 记录（尚未运行 train_model.py）")
            return
        print(f"🤖 最近 {len(rows)} 条训练记录:\n")
        for r in rows:
            run_id, name, uri, m50, m5095, ds, created = r
            print(f"  {run_id}  @ {created}")
            print(f"    模型: {name}  Registry: {uri or '—'}")
            print(f"    mAP50: {m50:.4f}  mAP50-95: {m5095:.4f}  数据: {ds} 样本")
            print()
    except Exception as e:
        print(f"❌ 查询失败: {e}")


def _show_import(db_url: str, import_id: str) -> None:
    """展示标注回传血缘。"""
    if not db_url:
        print("❌ 数据库未配置，请设置 DATABASE_URL 环境变量")
        return
    p = db_connection.ph(db_url)
    try:
        conn = db_connection.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            f"SELECT import_id, batch_ids, training_dir, consistency_rate, merged_count, created_at "
            f"FROM label_import WHERE import_id = {p}",
            (import_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            print(f"❌ 未找到 import {import_id}")
            return
        imp_id, batch_ids_json, training_dir, rate, merged, created = row
        batch_ids = json.loads(batch_ids_json) if batch_ids_json else []
        print(f"📊 标注回传血缘: {imp_id}\n")
        print(f"  关联批次: {batch_ids}")
        print(f"  训练目录: {training_dir}")
        print(f"  伪标签一致率: {rate:.2%}  并入文件数: {merged}")
        print(f"  创建时间: {created}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="DataFactory v3 血缘查询")
    parser.add_argument("--batch",    type=str, help="查询指定 batch_id 的 QC 血缘")
    parser.add_argument("--import-id", dest="import_id", type=str,
                        help="查询指定 import_id 的标注回传血缘")
    parser.add_argument("--train-id", dest="train_id", type=str,
                        help="查询指定 run_id 的模型训练血缘")
    parser.add_argument("--trains",   action="store_true",
                        help="列出最近的模型训练记录")
    parser.add_argument("--limit",    type=int, default=10, help="列表时显示条数")
    args = parser.parse_args()

    cfg, paths = config_loader.get_config_and_paths(BASE_DIR)
    db_url = paths.get("db_url", "")

    if args.batch:
        _show_batch(db_url, args.batch)
    elif args.import_id:
        _show_import(db_url, args.import_id)
    elif args.train_id:
        _show_train(db_url, args.train_id)
    elif args.trains:
        _list_recent_trains(db_url, args.limit)
    else:
        _list_recent_batches(db_url, args.limit)


if __name__ == "__main__":
    main()
