# ─────────────────────────────────────────────────────────────────────────────
# DataFactory — Dockerfile
# Base: python:3.11-slim (Debian bookworm，自带 /etc/ssl/certs CA bundle)
#
# 服务入口（docker-compose 中按 command 切换）：
#   Pipeline  : python main.py --guard            (持续监控 raw/)
#   SENTINEL-1: python dashboard/sentinel.py      (port 8766)
#   HQ        : python dashboard/hq.py            (port 8767)
#   Review UI : python dashboard/app.py           (port 8765, review.mode=dashboard)
#   MLflow    : mlflow server ...                 (port 5000)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── 1. 系统依赖（单层，减少镜像层数）─────────────────────────────────────────
#
# ca-certificates   ★ HTTPS 证书链（修复 macOS 特有 SSL 失败；Linux 容器原生需要）
# libglib2.0-0      ★ OpenCV / GLib 核心运行时
# libgomp1          ★ OpenMP 并行（OpenCV 多核加速、YOLO 推理）
# libgl1            ★ OpenGL stub（opencv-python 完整版 import 需要 libGL.so.1）
# libsm6 libxext6   ★ X11 session/extension（opencv-python 完整版链接）
# libxrender1         X rendering（同上；headless 版可省，保留防回归）
# libfreetype6        matplotlib / Pillow 字体栅格化
# libjpeg62-turbo     Pillow JPEG 硬件加速解码
# libpng16-16         Pillow PNG 解码
# libpq5              psycopg2 运行时（binary 包已自带，此处作防御保险）
# ffmpeg              OpenCV VideoCapture 视频后端；不装时降级为纯 Python 解码
# gcc                 psutil 等少量 C 扩展现场编译备用
#
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libglib2.0-0 \
        libgomp1 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libfreetype6 \
        libjpeg62-turbo \
        libpng16-16 \
        libpq5 \
        ffmpeg \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# ── 2. 工作目录 ───────────────────────────────────────────────────────────────
WORKDIR /app

# ── 3. Python 依赖（分两层，利用 Docker 缓存）───────────────────────────────
#
# 安装顺序关键：
#   a) 升级 pip/setuptools（避免旧版 pip 解析错误）
#   b) CPU-only PyTorch（防 ultralytics 自动拉 CUDA 版，镜像从 ~3 GB → ~900 MB）
#      ★ 如需 GPU 推理，将 whl/cpu 改为 whl/cu121（或对应 CUDA 版本）
#   c) opencv-python-headless（容器无显示服务器，去掉 X11/libGL 运行时依赖）
#   d) 剩余依赖从 pyproject.toml 安装
#
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    # ── CPU-only PyTorch（~750 MB，GPU 环境请修改 index-url）──────────────
    && pip install --no-cache-dir \
        torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu \
    # ── headless OpenCV（替代完整版，去掉 X11/libGL 依赖）─────────────────
    && pip install --no-cache-dir opencv-python-headless>=4.8.0 \
    # ── 从 pyproject.toml 提取剩余依赖（跳过已装的 opencv-python）────────
    && python3 -c "import tomllib; \
deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; \
print('\n'.join(d for d in deps if not d.startswith('opencv-python')))" \
        > /tmp/deps.txt \
    && pip install --no-cache-dir -r /tmp/deps.txt \
    && rm /tmp/deps.txt

# ── 4. 复制项目代码 ───────────────────────────────────────────────────────────
COPY . .

# ── 5. 预建存储目录（volume mount 时宿主目录已存在则无影响）──────────────────
RUN mkdir -p \
        storage/raw \
        storage/archive \
        storage/rejected \
        storage/redundant \
        storage/reports \
        storage/for_labeling \
        storage/labeled_return \
        storage/training \
        storage/golden \
        storage/test/original \
        storage/pending_review \
        storage/quarantine \
        logs \
        models \
        mlflow_artifacts

# ── 6. 运行时环境变量默认值 ───────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg

# ── 7. 端口声明 ───────────────────────────────────────────────────────────────
# 8765 : Review Dashboard  (dashboard/app.py,   review.mode=dashboard)
# 8766 : SENTINEL-1        (dashboard/sentinel.py)
# 8767 : HQ Command Center (dashboard/hq.py)
# 5000 : MLflow UI         (mlflow server)
EXPOSE 8765 8766 8767 5000

# ── 默认入口：Guard 模式，持续监控 storage/raw/ ──────────────────────────────
CMD ["python", "main.py", "--guard"]
