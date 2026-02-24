# DataFactory

Industrial video QC pipeline: **raw material → QC (duplicate + quality + optional AI) → human review → archive** (passed / rejected / redundant). Designed for traceability and MLOps; extensible toward v3+ edge and multimodal.

**Why this matters.** LLMs scaled fast because language data is already “curated” by human use. Robotics and autonomy don’t have that: data must be collected, cleaned, and labeled at great cost, across many modalities. Human perception works because our senses are effectively **edge pipelines**—they preprocess before feeding the brain. The real bottleneck for the industry is **data quality and supply**. This pipeline aims to be one piece of that infrastructure: a reusable, edge-ready data pipe so that “robot brains” get clean, structured input instead of raw, expensive, unlabeled streams. See **docs/Roadmap.md** (愿景 / 产业视角) for the full picture.

---

## Quick start

**Environment**: Python 3.9+ and pip only (no Conda). Use a venv:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # Edit .env for email and other secrets (optional)

# Single run: scan storage/raw and run full pipeline
python main.py

# Optional args
python main.py --gate 85             # Pass gate 85%
python main.py --guard               # Guard mode: Watchdog + 轮询兜底，详见 docs/architecture.md「Guard 模式巡逻逻辑」

# 厂长中控台（review.mode=dashboard 时，blocked 入队，Web 复核）
python -m dashboard.app              # 启动中控台 http://127.0.0.1:8765
```

First run creates `storage/` and `db/`. Report copies go to `storage/reports/`.

**Scripts**: `python scripts/reset_factory.py` — clean storage; `python scripts/export_for_labeling.py` — export to `storage/for_labeling`; `python scripts/import_labeled_return.py --dir /path` — receive labeled return, compare to pseudo-labels, merge to training; `python scripts/compare_models.py --new X.pt --baseline Y.pt --data DIR` — compare models, log to MLflow/DB; `python tests/smoke_test.py` — smoke test.

---

## Implemented features (summary)

| 阶段 | 功能 | 状态 |
|------|------|------|
| **v1 / v1.5 / v1.6** | QC、复核、归档、Logging、物理隔离、配置化、引擎分层 | ✅ |
| **v2.x** | YOLO、双门槛、MLflow、按置信分层落盘、伪标签、工业/智能报告 | ✅ |
| **v2.5** | 3_待人工精简、待标池自动更新、新旧模型对比、厂长中控台、标注回传与伪标签校验 | ✅ |
| **v2.6** | Smart Ingest：I-帧、运动唤醒、级联检测（四板斧 3/4） | ✅ |
| **v2.7** | 工业级加固：Path decoupling、P0/P1/P2/P3（重试、DB 错误处理、健康检查、时区/日志/邮件可配置、metrics、配置校验）— **Edge 部署前最关键一步** | ✅ |
| **v3** | Edge、LiDAR、多节点、特征前置+按需回传 | 设计完成，待实现 |

---

## Version overview

Current code covers **v1.x** through **v2.7** (工业级加固，Edge 部署前最关键一步). Next target: **v3** (edge, LiDAR, multi-node).

### v1.x — Production pipeline

| Feature | Description |
|--------|-------------|
| **Env-based secrets** | Email password etc. in `.env`, not in config or code. |
| **Batch review** | One batch fully QC’d and deduplicated, then **one summary email**; only blocked items get y/n/all/none review. |
| **Toronto timezone** | Logs, email, DB, batch_id use America/Toronto. |
| **Structured logging** | `logs/factory_YYYY-MM-DD.log`; fingerprint, duplicate, scores, decisions, moves, timeouts. |
| **Physical archive** | Rejected → `storage/rejected/Batch_xxx_Fails/` (`name_scorepts.ext`); redundant → `storage/redundant/`; passed → `storage/archive/` and DB. |
| **Labeling export** | Optional: `scripts/export_for_labeling.py` writes `storage/for_labeling/manifest_for_labeling.json` for Label Studio / CVAT. |

### v1.5 — Architecture

| Feature | Description |
|--------|-------------|
| **Central config** | Paths, thresholds, batch params, email in `config/settings.yaml`; `config_loader` resolves to absolute paths. |
| **Engine layer** | `engines/`: quality_tools, fingerprinter, db_tools, report_tools, production_tools, notifier, file_tools; tools return values only, no pass/fail decision. |
| **Flow vs decision** | QC in `core/qc_engine`, review in `core/reviewer`, archive in `core/archiver`; orchestration in `core/pipeline`. |
| **Single entry** | `main.py` single run or `--guard`; legacy scripts in `legacy/`. |
| **Batch metrics** | Per-batch: file count, size (GB), duration, stage timings (Ingest/QC/Review/Archive), throughput; stored in DB `batch_metrics`. |

### v1.6 — Storage and DB

| Feature | Description |
|--------|-------------|
| **Unified storage** | All data under `storage/` (raw, archive, rejected, redundant, test, reports, for_labeling); DB in `db/factory_admin.db`; `init_storage_structure()` on startup. |
| **Report archive** | QC report and chart copied to `storage/reports/` (`{batch_id}_quality_report.html`, `{batch_id}_chart.png`). |

### v2.x — Model and experiments

| Feature | Description |
|--------|-------------|
| **Vision (YOLO)** | Optional AI scan in QC; config-driven (model path, sample interval, inference params); thumbnails for vision report. |
| **Dual gate** | Configurable high/low thresholds: auto-pass, auto-reject, middle band for human review. |
| **Version mapping** | Algorithm and vision model version in logs and reports; `version_info.json` per batch. |
| **MLflow** | Optional batch-level runs: params, metrics, artifacts (industrial report, vision report). |
| **Industrial / Vision report** | Per-batch HTML; attached to email and MLflow. |
| **Extensible QC** | Quality checks pluggable; rule-based blur/brightness/jitter plus optional model. |

### v2.5 — Data loop and efficiency

| Feature | Description |
|--------|-------------|
| **inspection 精简** | `human_review_flat=true`: Normal/Warning 合并，只保留 manifest+图+txt，便于 for_labeling 导入。 |
| **待标池自动更新** | `labeling_pool.auto_update_after_batch=true`: 每批归档后自动将 inspection 追加到 for_labeling。 |
| **新旧模型对比** | `scripts/compare_models.py`: 在相同数据上跑两模型，比较检测结果，写入 MLflow/DB。 |
| **厂长中控台** | `review.mode=dashboard`: Web 复核，单项/批量放行拒绝，无超时丢料。 |
| **标注回传与伪标签校验** | `scripts/import_labeled_return.py`: 回传 vs 伪标签 IoU 匹配，一致率门槛报警，达标并入 training。 |

### v2.6 — Smart Ingest / 高效筛查（四板斧）

| Feature | Description |
|--------|-------------|
| **I-帧** | `vision.use_i_frame_only=true`: 只解 I-帧（需 ffprobe），减少解码量；`engines/frame_io.py`。 |
| **运动唤醒** | `vision.motion_threshold`: 帧差低于阈值不跑 YOLO，静止画面跳过；`engines/motion_filter.py`。 |
| **级联检测** | `vision.cascade_light_model_path`: 轻量模型初筛，有东西才上主模型；空画面被过滤。 |
| **Embedding/Re-ID** | 待做：向量库检索、“谁在哪儿”报表。 |

### v2.7 — 工业级加固（Path decoupling + Poka yoke）

| 类别 | 要点 |
|------|------|
| **Path decoupling** | 批次目录名（reports/source/refinery/inspection）、batch_prefix、batch_fails_suffix 均在 `config/settings.yaml`；改名只改配置。支持 `DATAFACTORY_*` 环境变量覆盖。 |
| **P0 稳定性** | 文件操作重试（`retry.max_attempts/backoff_seconds`）；DB 异常捕获与日志；`GET /api/health` 健康检查；缩略图路径严格校验防 traversal。 |
| **P1 可维护性** | 时区配置（`timezone`）；视频扩展名从 config 读取；fingerprinter 异常打日志；`validate_config` 校验 min&lt;max、gate 范围、双门槛；日志 RotatingFileHandler 轮转。 |
| **P2 可观测性** | `engines/metrics.py` 简单 counters；`GET /api/metrics`；qc_engine 用 TemporaryDirectory 自动清理；邮件发送重试（`max_retries/retry_delay_seconds`）。 |
| **P3 规范** | `pyproject.toml` black + isort + mypy 配置。 |

**Dashboard API**（中控台 `python -m dashboard.app` 后可用）：
- `GET /api/health` — 健康检查（DB 连通性、目录可写、配置校验）；异常时 503。
- `GET /api/metrics` — 简单 counters 快照（batch_processed_total、file_move_errors_total 等），便于监控告警。

**新增模块**：`core/time_utils.py`（时区）、`engines/metrics.py`（counters）、`engines/retry_utils.py`（文件重试）。

详见 **docs/path_decoupling.md**、**docs/industrial_standards.md**；CHANGELOG: **CHANGELOG.md**；roadmap: **docs/Roadmap.md**；settings: **docs/settings_guide.md**.

---

## Architecture index

| Layer | Path | Description |
|-------|------|-------------|
| Entry | `main.py` | Single run or Guard |
| Flow | `core/` | pipeline → ingest → qc_engine → reviewer → archiver；time_utils（时区） |
| Engines | `engines/` | quality_tools, fingerprinter, db_tools, report_tools, production_tools, notifier, vision_detector, motion_filter, frame_io, retry_utils, metrics, labeling_export, labeled_return |
| Config | `config/` | settings.yaml, config_loader; paths and thresholds |
| Storage | `storage/` | raw, archive, rejected, redundant, test, reports, for_labeling, labeled_return, training |
| DB | `db/` | factory_admin.db (production_history, batch_metrics, model_comparison) |
| Docs | `docs/` | Roadmap, architecture, settings, smart_slicing |
| Scripts | `scripts/` | reset_factory, export_for_labeling, import_labeled_return, compare_models |
| Tests | `tests/` | smoke_test, test_dual_gate_mlflow |
| Legacy | `legacy/` | Old entry scripts, kept for reference |

See **docs/architecture.md**, **docs/settings_guide.md**; **ROOT_LAYOUT.md** for directory layout.

---

## Roadmap (short)

- **v1 / v1.5 / v1.6**: Done. QC, review, archive, metrics, labeling export.
- **v2.x**: Done. Vision, dual gate, MLflow, industrial + vision reports.
- **v2.5**: Done. 3_待人工精简, 待标池自动更新, 新旧模型对比, 厂长中控台, 标注回传与伪标签校验.
- **v2.6**: Done. Smart Ingest — I-帧, 运动唤醒, 级联检测 (四板斧 3/4).
- **v2.7**: Done. 工业级加固 — P0/P1/P2/P3, Path decoupling, Batch 重命名 (Edge 部署前最关键一步).
- **v3.x**: 设计完成，待实现。Edge, LiDAR, 多节点, 特征前置+按需回传金矿.
- **v4.x**: Deep lineage (transform log, data lineage graph).

See **docs/Roadmap.md**.

---

## Edge deployment: why it fits remote / mining sites

This pipeline is designed so that **v3-style edge deployment** keeps raw data on site and only sends small outputs out. That makes it a good fit for mines and other remote sites where bandwidth is expensive and data sovereignty matters.

| Benefit | What it means |
|--------|----------------|
| **Raw data stays on site** | Video and sensor data are processed at the edge (mine/field). Only **results** leave: batch IDs, scores, fingerprints, QC reports (JSON/HTML), and optionally **curated outputs** (e.g. key frames, bbox crops) for training. No need to ship full video streams or disks. |
| **Cost controllable** | Transfer drops from GB to KB (metadata + reports) or to a small set of images (key frames / training samples). Cheaper and more predictable than dedicated lines or frequent physical handoffs. |
| **Easier for the site to accept** | The site does not have to “open a data pipe” for raw access. They run the pipeline locally; only summaries and agreed outputs are sent. Responsibility and compliance stay clear. |
| **Cheaper than sending people** | No need for routine trips to collect disks. Deploy once at the edge; sync results on a schedule or on demand. Operational and training data (curated images) remain small. |
| **Remote model updates are small** | Pushing a new model to the edge is a single download (e.g. one `.pt` file, on the order of MB). Much smaller than raw video; hot-push or scheduled model/config updates are bandwidth-friendly. |

**In short**: the mine keeps the raw data; the pipeline runs there and only “finished products” (reports, metrics, and optionally key frames / training samples) go out. That keeps cost down and makes edge deployment something sites can accept. See **docs/Roadmap.md** (v3 Edge Deployment, 多节点部署) for the full design.

---

## 验证清单（待逐块验证）

| 模块 | 验证项 |
|------|--------|
| inspection 精简 | `human_review_flat=true` 时 inspection 无 Normal/Warning 子目录，for_labeling 可导入 |
| 待标池自动更新 | 归档后 for_labeling 自动追加本批 inspection，manifest 合并正确 |
| 新旧模型对比 | `compare_models.py` 跑通，MLflow/DB 有记录 |
| I-帧 | `use_i_frame_only=true` + 有 ffprobe 时只解 I-帧；无 ffprobe 时回退按秒 |
| 运动唤醒 | `motion_threshold>0` 时静止画面不跑 YOLO，日志有「四板斧过滤」 |
| 级联检测 | `cascade_light_model_path` 配置时，空画面被轻量模型过滤 |
| **v2.7 工业级加固** | `GET /api/health` 返回 200；`GET /api/metrics` 有 counters；`timezone` 改配置后日志时区变化；`validate_config` 非法配置返回错误 |

详见 **docs/testing_and_audit.md**（dry run 说明、流程追踪、阑尾审计）。
