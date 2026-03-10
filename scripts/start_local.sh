#!/usr/bin/env bash
# scripts/start_local.sh — 一键本地启动 DataFactory 所有服务
#
# 用法:
#   bash scripts/start_local.sh          # 启动全部（Pipeline + Sentinel + HQ + MLflow）
#   bash scripts/start_local.sh --no-pipeline   # 跳过 pipeline（只开 dashboard）
#   bash scripts/start_local.sh --no-mlflow     # 跳过 MLflow UI
#
# 依赖：macOS Terminal（用 osascript 自动开 tab），无需安装 tmux。

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$BASE_DIR/.venv/bin/activate"

LAUNCH_PIPELINE=true
LAUNCH_MLFLOW=true

for arg in "$@"; do
    case "$arg" in
        --no-pipeline) LAUNCH_PIPELINE=false ;;
        --no-mlflow)   LAUNCH_MLFLOW=false ;;
    esac
done

# ── 在新 Terminal tab 里执行命令 ──────────────────────────────────────────
open_tab() {
    local title="$1"
    local cmd="$2"
    # 完整命令：cd → activate venv → 执行 → 失败时暂停（方便看报错）
    local full="cd '$BASE_DIR' && source '$VENV' && echo '=== $title ===' && $cmd; echo; echo '--- 进程已退出，按回车关闭 ---'; read"
    osascript \
        -e 'tell application "Terminal"' \
        -e '  activate' \
        -e '  tell application "System Events" to keystroke "t" using command down' \
        -e '  delay 0.4' \
        -e "  do script \"$full\" in selected tab of front window" \
        -e 'end tell' \
        2>/dev/null || true
}

# ── 检查 .venv ────────────────────────────────────────────────────────────
if [[ ! -f "$VENV" ]]; then
    echo "❌ 找不到 .venv，请先运行："
    echo "   python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DataFactory — 本地启动"
echo "  Pipeline:  $LAUNCH_PIPELINE"
echo "  MLflow UI: $LAUNCH_MLFLOW"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 先打开 Terminal（如果没开的话）
osascript -e 'tell application "Terminal" to activate' 2>/dev/null || true
sleep 0.5

# Tab 1 — Review
open_tab "Review" "python -m dashboard.app"
sleep 0.3

# Tab 2 — Sentinel
open_tab "Sentinel" "python dashboard/sentinel.py --source archive --port 8766"
sleep 0.3

# Tab 3 — HQ
open_tab "HQ" "python dashboard/hq.py --port 8767"
sleep 0.3

# Tab 3 — MLflow UI（可选）
if $LAUNCH_MLFLOW; then
    open_tab "MLflow" "bash scripts/start_mlflow_server.sh"
    sleep 0.3
fi

# Tab 4 — Pipeline（最后开，确保 dashboard 先就绪）
if $LAUNCH_PIPELINE; then
    open_tab "Pipeline" "python main.py --guard"
fi

echo ""
echo "✅ 已开启所有 tab，服务地址："
echo "   Review    → http://localhost:8765"
echo "   Sentinel  → http://localhost:8766"
echo "   HQ        → http://localhost:8767"
$LAUNCH_MLFLOW && echo "   MLflow    → http://localhost:5001"
echo ""
echo "停止：在各 tab 按 Ctrl-C，或直接关闭 Terminal 窗口。"
