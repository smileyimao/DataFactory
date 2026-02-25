# 根目录说明 (Root Layout)

项目根目录下各文件与文件夹的用途说明。数据与日志由程序自动写入，不提交到 Git。

---

## 文件（根目录直接可见）

| 名称 | 说明 |
|------|------|
| **main.py** | 生产总开关。`python main.py` 单次运行；`python main.py --guard` 监控模式。 |
| **README.md** | 项目门户：快速入门、架构索引、运行命令。 |
| **CHANGELOG.md** | 版本变更记录（v1.3 → v1.5 → v1.6 …）。 |
| **requirements.txt** | 运行依赖。`pip install -r requirements.txt`；生产/Docker 仅装此文件。 |
| **requirements-dev.txt** | 开发与测试依赖（pytest、hypothesis、httpx 等）。`pip install -r requirements.txt -r requirements-dev.txt`；CI 与本地开发用，生产镜像不装。 |
| **.gitignore** | Git 忽略规则：数据目录、`.env`、`logs/`、`__pycache__` 等不提交。 |
| **.env** | 本地敏感配置（数据库密码、邮箱授权码等），不提交；复制 `.env.example` 后填写。 |
| **.env.example** | 环境变量示例，提交到仓库，供他人复制为 `.env`。 |
| **pyproject.toml** | 项目元数据与工具配置：black、isort、mypy 格式化；pytest 路径与 markers。 |
| **ROOT_LAYOUT.md** | 本文件：根目录结构说明。 |

---

## 目录（按职责）

| 目录 | 说明 |
|------|------|
| **config/** | 司令部。`settings.yaml` 路径与阈值；`config_loader.py` 加载与目录初始化；`logging.py` 日志配置。 |
| **core/** | 传送带。业务流：ingest → qc_engine → reviewer → archiver；time_utils（时区）；guard 监控。 |
| **engines/** | 工具箱。quality_tools、db_tools、report_tools、notifier、file_tools、retry_utils、metrics、vision_detector 等纯工具。 |
| **storage/** | 仓储中心。程序读写：raw、archive、rejected、redundant、test、reports。启动时自动创建子目录。 |
| **models/** | 模型库。YOLO 及级联检测 .pt 文件；路径在 `vision.model_path` 配置。 |
| **db/** | 账本。`factory_admin.db` 生产数据库；`mlflow.db` MLflow 实验记录（tracking_uri 默认）；启动时若不存在会初始化。 |
| **docs/** | 图纸室。架构说明、配置说明、Roadmap、交接文档等。 |
| **templates/** | 排版房。如 `email_report.html` 邮件报告模板（demo 用）。 |
| **scripts/** | 运维工具。如 `reset_factory.py`、`export_for_labeling.py`、`import_labeled_return.py`、`compare_models.py`。 |
| **dashboard/** | 厂长中控台。`review.mode=dashboard` 时 `python -m dashboard.app` 启动 Web 复核。 |
| **tests/** | 测试套件。`pytest tests/ -v -m "not e2e"`；unit/integration/e2e/api 分层。 |
| **legacy/** | 博物馆。旧版脚本（main_factory、factory_guard 等），兼容参考用。 |
| **logs/** | 流水账。按日写入 `factory_YYYY-MM-DD.log`，不提交。 |

---

## 不提交、可忽略或自动生成

- **.env** — 本地私密，已在 `.gitignore`。
- **.venv/** — 虚拟环境，`python -m venv .venv` 创建，已在 `.gitignore`。
- **logs/** — 运行日志，已在 `.gitignore`。
- **storage/** — 若在 `.gitignore` 中排除部分子目录（如 raw），则不会提交物料与报表。
- **db/** — 数据库文件通常不提交（factory_admin.db、mlflow.db 等）。MLflow 默认 `db/mlflow.db`，根目录 `mlflow.db`、`mlruns/` 已废弃并清理。
- **__pycache__/**、**.pytest_cache/**、**.hypothesis/** — 自动生成，已在 `.gitignore`。
- **.idea/** — IDE 配置，可选不提交。

---

## 快速对照

```
DataFactory/
├── main.py              # 唯一入口
├── README.md            # 门户
├── CHANGELOG.md         # 版本记录
├── requirements.txt     # 运行依赖
├── requirements-dev.txt # 开发/测试依赖
├── pyproject.toml       # black/isort/mypy/pytest 配置
├── .env / .env.example
├── .gitignore
├── ROOT_LAYOUT.md       # 本说明
├── config/              # 配置
├── core/                # 流程
├── engines/             # 工具
├── dashboard/           # 厂长中控台
├── storage/             # 数据（程序写入）
├── db/                  # 数据库（factory_admin.db、mlflow.db）
├── models/              # YOLO 模型
├── docs/                # 文档
├── templates/           # 邮件等模板
├── scripts/             # 运维脚本
├── tests/               # 测试套件
├── legacy/              # 旧脚本
└── logs/                # 日志（程序写入）
```

更细的架构与配置说明见 `docs/architecture.md`、`docs/settings_guide.md`。
