#!/usr/bin/env bash
# scripts/run_demo_a.sh — A 视频一键开工：清空 → 投料 → pipeline → 导出 CVAT
#
# 实验流程：A 视频（训练）→ pipeline → 低置信进 for_labeling → CVAT 标注 → 回传 → retrain → B 验证
# 用法: ./scripts/run_demo_a.sh  或  bash scripts/run_demo_a.sh
#
# 前置：5 个行车记录仪视频已在 storage/test/original/
# 配置：若数车辆（car/truck），建议 vision.cascade_light_model_path: "" 避免 COCO 级联过滤掉车

set -e
cd "$(dirname "$0")/.."

echo "=========================================="
echo "  DataFactory Demo A — 一键开工"
echo "=========================================="
echo ""
echo "提示：若数车辆(car/truck)，请先设置 config cascade_light_model_path: \"\""
echo "      (COCO 级联会过滤掉矿车等，留空则关闭级联)"
echo ""

# 1. 清空旧数据（便于反复测试）
echo ""
echo "[1/5] 清空 archive / reports / db ..."
python scripts/reset_factory.py --execute --target for-test --confirm-dangerous

# 2. 投料：test/original → raw
echo ""
echo "[2/5] 投料：test/original → raw ..."
mkdir -p storage/raw
cp -v storage/test/original/*.MOV storage/raw/ 2>/dev/null || cp -v storage/test/original/*.mp4 storage/raw/ 2>/dev/null || {
  echo "❌ storage/test/original 下无 .MOV 或 .mp4 文件"
  exit 1
}

# 3. 跑 pipeline（gate 50 降低门槛，更多进 inspection 供标注）
echo ""
echo "[3/5] 跑 pipeline（--gate 50）..."
python main.py --gate 50

# 4. 从 archive 仅导出 inspection（低置信）到 for_labeling，refinery 伪标签直接用
echo ""
echo "[4/5] 导出待标注清单 (仅 inspection → for_labeling) ..."
python scripts/export_for_labeling.py --last 1 --inspection-only

# 5. 打包 CVAT 用 zip（图片 + 原生 XML 标注）
echo ""
echo "[5/5] 导出 CVAT zip ..."
python scripts/export_for_cvat.py --vehicle
python scripts/export_for_cvat_native.py --vehicle

echo ""
echo "=========================================="
echo "  ✅ A 视频处理完成"
echo "=========================================="
echo "下一步："
echo "  1. 若 review.mode=dashboard：另开终端运行 python -m dashboard.app 复核放行"
echo "  2. CVAT：Create task → for_cvat.zip；Upload annotations → CVAT for images 1.1 → for_cvat_native.zip"
echo "  3. 标注低置信图片"
echo "  4. 导出标注 → python scripts/import_labeled_return.py --dir /path/to/exported"
echo "  5. 达标后并入 training，retrain 模型"
echo "  6. B 视频用 count_vehicles_track 对比 baseline vs 新模型"
echo ""
