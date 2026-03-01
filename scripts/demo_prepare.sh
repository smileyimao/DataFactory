#!/usr/bin/env bash
# scripts/demo_prepare.sh — 演示前预演练：跑完整流程并验证 CVAT zip 可导入
#
# 用法: ./scripts/demo_prepare.sh           # 完整流程 + 验证
#       ./scripts/demo_prepare.sh --verify  # 仅验证已有 zip（不跑 pipeline）
#
# 建议：演示前 1 天跑一次，确认 zip 可成功导入 CVAT，演示当天直接复用
#
# 输出：storage/for_labeling/for_cvat.zip（已验证无空格、路径正确）

set -e
cd "$(dirname "$0")/.."

VERIFY_ONLY=false
[ "$1" = "--verify" ] && VERIFY_ONLY=true

echo "=========================================="
echo "  DataFactory Demo 预演练"
echo "=========================================="
echo ""

if [ "$VERIFY_ONLY" = false ]; then
  echo "[1/3] 执行 run_demo_a.sh ..."
  bash scripts/run_demo_a.sh
else
  echo "[1/3] 跳过 pipeline，仅验证已有 zip"
fi

# 2. 验证 zip（CVAT 原生：for_cvat.zip 图片，for_cvat_native.zip 标注）
ZIP_TASK="${PWD}/storage/for_labeling/for_cvat.zip"
ZIP_NATIVE="${PWD}/storage/for_labeling/for_cvat_native.zip"
echo ""
echo "[2/3] 验证 CVAT zip ..."
for z in "$ZIP_TASK" "$ZIP_NATIVE"; do
  if [ ! -f "$z" ]; then
    echo "❌ $(basename "$z") 不存在"
    exit 1
  fi
done

TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT
unzip -q "$ZIP_TASK" -d "$TMP"
N_IMG=$(ls "$TMP"/*.jpg 2>/dev/null | wc -l)
if [ "$N_IMG" -eq 0 ]; then
  echo "❌ for_cvat.zip 无图片"
  exit 1
fi

unzip -q -o "$ZIP_NATIVE" -d "$TMP"
if [ ! -f "$TMP/annotations.xml" ]; then
  echo "❌ for_cvat_native.zip 无 annotations.xml"
  exit 1
fi

echo "✅ 验证通过：$N_IMG 张图，CVAT 原生标注完整"
echo ""
echo "[3/3] 完成"
echo ""
echo "=========================================="
echo "  演示当天可直接使用"
echo "=========================================="
echo "  创建 Task：$ZIP_TASK"
echo "  上传标注：$ZIP_NATIVE (CVAT for images 1.1)"
echo ""
