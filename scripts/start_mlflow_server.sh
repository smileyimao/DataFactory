#!/usr/bin/env bash
# scripts/start_mlflow_server.sh — 启动 MLflow Tracking Server（局域网可访问）
#
# 用法:
#   bash scripts/start_mlflow_server.sh          # 前台运行（日志直接输出）
#   bash scripts/start_mlflow_server.sh --daemon  # 后台运行，日志写 logs/mlflow_server.log
#
# 模型团队访问地址: http://<本机IP>:5000
# 本机访问地址:     http://localhost:5000

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

source .venv/bin/activate 2>/dev/null || true

HOST="0.0.0.0"
PORT="5000"
# Use MLFLOW_BACKEND_URI env var if set, otherwise fall back to local SQLite
BACKEND="${MLFLOW_BACKEND_URI:-sqlite:///${BASE_DIR}/db/mlflow.db}"
ARTIFACTS="${BASE_DIR}/mlflow_artifacts"

mkdir -p "$ARTIFACTS"

LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MLflow Tracking Server"
echo "  本机:     http://localhost:${PORT}"
echo "  局域网:   http://${LOCAL_IP}:${PORT}"
echo "  数据库:   ${BACKEND}"
echo "  Artifacts: ${ARTIFACTS}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "${1:-}" == "--daemon" ]]; then
    LOG="logs/mlflow_server.log"
    mkdir -p logs
    nohup mlflow server \
        --backend-store-uri "$BACKEND" \
        --artifacts-destination "$ARTIFACTS" \
        --host "$HOST" \
        --port "$PORT" \
        >> "$LOG" 2>&1 &
    echo "  后台运行 PID=$!，日志: $LOG"
else
    mlflow server \
        --backend-store-uri "$BACKEND" \
        --artifacts-destination "$ARTIFACTS" \
        --host "$HOST" \
        --port "$PORT"
fi
