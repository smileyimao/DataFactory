# DataFactory

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-brightgreen)

Industrial video data pipeline: **raw material → Ingest → Funnel QC → Admission → Archive → CVAT → Train**. Production-hardened for edge sites; designed for traceability and MLOps.

> **Built for the Unpredictable Edge** — *Reliability as a First-Class Citizen.* Bridging the gap between AI and industrial reality; minimizing technical debt through strict decoupling.

**Why this matters.** LLMs scaled fast because language data is already curated by human use. Robotics and autonomy don't have that: data must be collected, cleaned, and labeled at great cost, across many modalities. The real bottleneck for the industry is **data quality and supply**. DataFactory is one piece of that infrastructure — a reusable, edge-ready data pipe so that "robot brains" get clean, structured input instead of raw, unlabeled streams.

### System overview

![DataFactory Architecture](docs/DataFactory.png)

*Automated data flow from ingest to archive, with reliability and continuous model evolution built in.*

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Features](#features)
- [Scripts Reference](#scripts-reference)
- [Configuration](#configuration)
- [Roadmap](#roadmap)
- [Edge Deployment](#edge-deployment)
- [Design Philosophy](#design-philosophy)
- [Contributing](#contributing)
- [License](#license)

---

## Prerequisites


| Requirement     | Notes                                                                |
| --------------- | -------------------------------------------------------------------- |
| **Python 3.9+** | No Conda — standard venv only                                        |
| **OpenCV**      | Installed via `pip install .`                                        |
| **ffprobe**     | Optional; required for I-frame mode (`vision.use_i_frame_only=true`) |
| **Docker**      | Required for local CVAT and PostgreSQL (production mode)             |
| **NVIDIA GPU**  | Optional; YOLO inference falls back to CPU automatically             |


---

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .                    # Production deps from pyproject.toml
pip install ".[dev]"             # + test deps (pytest, hypothesis, etc.)
cp .env.example .env             # Add email / CVAT credentials (optional)

# Single run: scan storage/raw/ and execute full pipeline
python main.py

# Common flags
python main.py --gate 85         # Set pass-rate gate to 85%
python main.py --guard           # Daemon mode: Watchdog + polling fallback
python main.py --auto-cvat       # Auto-create CVAT labeling task after archive

# Ops / debug tools (non-pipeline)
python tools.py --probe          # Hardware detection and auto-config summary
# 测试：pytest tests/ --unit（单元） 或 pytest tests/ --e2e（E2E）
python tools.py --usage-report   # Feature usage report (last 30 days)

# Dashboards
python -m dashboard.app          # Review dashboard    http://127.0.0.1:8765
python dashboard/sentinel.py     # SENTINEL-1 telemetry http://127.0.0.1:8766
python dashboard/hq.py           # HQ Command Center   http://127.0.0.1:8767
```

First run creates `storage/` directories automatically. Database: set `DATABASE_URL=postgresql://...` in `.env` for PostgreSQL (production); without it the pipeline exits with an error prompting you to configure the URL — use the SQLite fallback (`db_file` path) only for `--test` / dev isolation.

**Run tests**（统一用 pytest；两条命令都会在终端输出进度，不会误以为卡死）：

```bash
pytest tests/ --unit    # 单元测试（等价 -m "not slow"）
pytest tests/ --e2e    # 全链路 E2E，等价 python tools.py --test（用 storage/test/original 跑整条 pipeline）
```

**CVAT local setup** (one-time):

```bash
git clone --depth 1 https://github.com/opencv/cvat ~/Developer/cvat
cd ~/Developer/cvat && docker compose up -d
docker exec -it cvat_server bash -c "python manage.py createsuperuser"
# Add to .env:
# CVAT_LOCAL_URL=http://localhost:8080
# CVAT_LOCAL_USERNAME=admin
# CVAT_LOCAL_PASSWORD=yourpassword
```

**PostgreSQL mode** (production):

```bash
docker compose up -d
# Add to .env: DATABASE_URL=postgresql://datafactory:datafactory@localhost:5432/datafactory
python -c "from db import db_tools; db_tools.init_db('postgresql://...')"
python scripts/db/migrate_sqlite_to_pg.py
```

---

## Architecture


| Layer     | Path              | Description                                                                                                                       |
| --------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Entry     | `main.py`         | Single run or guard mode (`--guard`: Watchdog + polling + `/health` endpoint)                                                     |
| Ops       | `tools.py`        | Ops CLI: `--probe` hardware detect; `--test` full-pipeline in temp env; `--usage-report/reset`                                    |
| Flow      | `core/`           | `pipeline` → `ingest` → `qc_engine` (SRP) → `reviewer` → `archiver`; `guard` (Watchdog)                                           |
| Database  | `db/`             | `db_connection.py` (SQLite/PG thin adapter + ThreadedConnectionPool); `db_tools.py`                                               |
| Vision    | `vision/`         | `vision_detector`, `quality_tools`, `motion_filter`, `frame_io`, `production_tools`; `foundation_models` (CLIP/SAM, opt-in)       |
| Labeling  | `labeling/`       | `labeling_export`, `labeled_return`, `annotation_upload`                                                                          |
| Dashboard | `dashboard/`      | `app.py` (review :8765); `sentinel.py` (frame telemetry :8766); `hq.py` (command center :8767)                                    |
| Utils     | `utils/`          | logging (+ JsonFormatter), startup, fingerprinter, retry_utils, file_tools, notifier, time_utils, `system_probe`, `usage_tracker` |
| Config    | `config/`         | `settings.yaml`; env override: `DATAFACTORY_*`, `DATAFACTORY_QT__*`, `DATAFACTORY_PS__*`                                          |
| Storage   | `storage/`        | raw, archive, rejected, redundant, quarantine, reports, for_labeling, labeled_return, training                                    |
| DB files  | `db/` (data)      | PostgreSQL (prod) or `factory_admin.db` SQLite (dev)                                                                              |
| Scripts   | `scripts/cvat/`   | `cvat_api`, `cvat_pull_annotations`, `cvat_setup_labels`, `cvat_upload_annotations`                                               |
| Scripts   | `scripts/mlflow/` | `train_model`, `compare_models`, `register_model`, `download_models`                                                              |
| Scripts   | `scripts/db/`     | `migrate_sqlite_to_pg`                                                                                                            |
| Scripts   | `scripts/`        | `reset_factory`, `query_lineage`, `import_labeled_return`                                                                         |
| Tests     | `tests/`          | 统一 pytest：`pytest tests/ --unit`（单元）、`pytest tests/ --e2e`（E2E）                                                          |


DB tables: `production_history`, `batch_metrics`, `batch_lineage`, `label_import`, `model_train`.

See **docs/architecture.md** and **docs/Roadmap.md** for full directory layout and evolution plan.

---

## Features


| Version          | Highlights                                                                                                                                                                                                                                               | Status      |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| **v1.x – v1.6**  | Funnel QC, Admission gate (HITL), physical archive, structured logging, modular engine layer                                                                                                                                                             | ✅           |
| **v2.x**         | YOLO integration, dual gate, confidence-tiered output (refinery / inspection), MLflow, HTML reports                                                                                                                                                      | ✅           |
| **v2.5**         | Inspection flattening, labeling pool auto-update, model A/B comparison, web dashboard, pseudo-label IoU validation                                                                                                                                       | ✅           |
| **v2.6**         | Smart Ingest: I-frame, motion wake-up, cascade detection                                                                                                                                                                                                 | ✅           |
| **v2.7**         | Industrial hardening: path decoupling, Poka-Yoke config validation, backoff retry, `/api/health`, `/api/metrics`                                                                                                                                         | ✅           |
| **v2.8 – v2.10** | Ingest pre-filter (dedup + decode check), modality decoupling, image pipeline, auto-modality                                                                                                                                                             | ✅           |
| **v3.0**         | Model-ready lineage: `batch_lineage`, `label_import` tables, `query_lineage.py`, MLflow Registry URI                                                                                                                                                     | ✅           |
| **v3.1**         | Full closed loop: local CVAT → `cvat_pull_annotations.py` → `train_model.py` → MLflow Registry                                                                                                                                                           | ✅           |
| **v3.2**         | SQLite → PostgreSQL: thin adapter, `DATABASE_URL` env, Docker Compose PG16, migration script                                                                                                                                                             | ✅           |
| **v3.3 – v3.4**  | Package cleanup: `utils/`, domain-driven split: `db/`, `vision/`, `labeling/`                                                                                                                                                                            | ✅           |
| **v3.5**         | P0–P3 hardening: PG connection pool, section-level env override, JSON logging, `/health` in guard mode                                                                                                                                                   | ✅           |
| **v3.6**         | Refinery labeling pool stratified sampling by video; IoU consistency alert with threshold tuning advice                                                                                                                                                  | ✅           |
| **v3.8**         | Mining augmentation: `--augment mining` preset (blur, erasing, rotation, brightness); MLflow tracking                                                                                                                                                    | ✅           |
| **v3.9**         | CLIP/SAM foundation models (opt-in, graceful degrade): semantic dedup, diversity sampling, scene-adaptive QC thresholds, SAM polygon pre-annotation; hardware auto-detect (`system_probe`); feature usage tracking (`usage_tracker`); `tools.py` ops CLI | ✅           |
| **v4.x**         | Multimodal, FFT, Edge multi-node, access control, federated augmentation                                                                                                                                                                                 | Design done |


See **[CHANGELOG.md](CHANGELOG.md)** for full per-version details.

---

## Scripts Reference


| Script                                                                             | Purpose                                                                     |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `python scripts/reset_factory.py`                                                  | Clean all storage directories                                               |
| `python scripts/import_labeled_return.py --dir /path`                              | Receive labeled return, compare IoU vs pseudo-labels, merge to training     |
| `python scripts/query_lineage.py`                                                  | List recent batches; `--batch ID` batch detail; `--trains` training history |
| `python scripts/cvat/cvat_pull_annotations.py --task-id N`                         | Pull CVAT annotations → YOLO format → trigger label merge                   |
| `python scripts/mlflow/train_model.py`                                             | Train YOLOv8 on `storage/training/`, register to MLflow Registry            |
| `python scripts/mlflow/train_model.py --augment mining`                            | Train with mining-specific augmentation preset                              |
| `python scripts/mlflow/compare_models.py --new X.pt --baseline Y.pt --data DIR`    | A/B model comparison                                                        |
| `python scripts/mlflow/register_model.py path/to/model.pt --name vehicle_detector` | Register model to Registry                                                  |
| `python scripts/db/migrate_sqlite_to_pg.py`                                        | Idempotent SQLite → PostgreSQL migration                                    |
| `python tools.py --probe`                                                          | Hardware detection: device, RAM/VRAM, auto-configured model sizes           |
| `python tools.py --test [--gate N]`                                                | 临时环境跑全链路（与 `pytest tests/ --e2e` 等价，可互换）                    |
| `python tools.py --usage-report [--days N]`                                        | Feature usage report for the last N days (default 30)                       |
| `python tools.py --usage-reset FEATURE|all`                                        | Reset usage counter for one feature or all                                  |


---

## Configuration

All settings live in `config/settings.yaml`. Key sections:


| Section              | What it controls                                                                               |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| `paths`              | All storage directories (no hardcoded paths in code)                                           |
| `ingest`             | File stability wait, extensions, dedup, decode check, health port                              |
| `quality_thresholds` | Brightness, blur, contrast, jitter limits                                                      |
| `production_setting` | Pass-rate gate, dual gate, confidence tiers, YOLO params                                       |
| `vision`             | Model path, sample interval, inference device, augmentation cascade                            |
| `mlflow`             | Tracking URI, experiment name                                                                  |
| `labeled_return`     | IoU consistency threshold, alert email                                                         |
| `rolling_cleanup`    | Log and report retention (days)                                                                |
| `foundation_models`  | CLIP/SAM opt-in flags (all `false` by default); `override: true` disables hardware auto-config |


**Environment overrides** — no need to edit YAML for deployment:

```bash
DATAFACTORY_QT__MIN_BRIGHTNESS=60    # quality_thresholds.min_brightness
DATAFACTORY_PS__PASS_RATE_GATE=90    # production_setting.pass_rate_gate
DATAFACTORY_LOG_FORMAT=json          # enable JSON structured logging
DATABASE_URL=postgresql://...        # switch to PostgreSQL
```

See **docs/settings_guide.md** for the full reference.

---

## Roadmap

- **v3.6**: Refinery labeling pool stratified sampling + IoU consistency alert — done (shipped in v3.4 label)
- **v3.x → v4**: Offline augmentation (Albumentations), synthetic data (game engine / Omniverse), generative AI augmentation (Diffusion/ControlNet), federated augmentation
- **v4.x**: Multimodal, Temporal Sync, Resource Locking (Edge), FFT, multi-node, access control

See **[docs/Roadmap.md](docs/Roadmap.md)** for the full roadmap and industry perspective.

---

## Edge Deployment

This pipeline is designed so that raw data stays on site; only small outputs leave.


| Benefit                      | Detail                                                                                                                                                                |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Data sovereignty**         | Video and sensor data processed at the edge. Only batch reports (JSON/HTML), fingerprints, and optionally curated key frames are transmitted — no full video streams. |
| **Cost-controlled transfer** | Output drops from GB to KB (metadata + reports) or a small image set. No dedicated lines or physical disk handoffs needed.                                            |
| **Easy site acceptance**     | Sites run the pipeline locally; only agreed summaries go out. Compliance stays clear.                                                                                 |
| **Small model updates**      | A new YOLO model is one `.pt` file (tens of MB). Hot-push or scheduled model updates are bandwidth-friendly.                                                          |
| **Full traceability**        | Fingerprint, `batch_id`, archive path, and `version_info.json` ensure every file's provenance is traceable end-to-end.                                                |


See **[docs/Roadmap.md](docs/Roadmap.md)** → v4 Edge Deployment section for the full design.

---

## Design Philosophy


| Pillar                    | Keywords                                                                           | Where in DataFactory                                                                                     |
| ------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **Core Workflow**         | Automated pipeline, Batch-centric, HITL, Traceability                              | `core/pipeline` → Ingest → Funnel QC → Admission → Archive                                               |
| **Defensive Engineering** | Poka-Yoke, Fault-tolerant I/O, Backoff retry, Path sanitization, Failing fast      | `retry_utils`, `db_tools` error handling, `validate_config`, `init_db` exit(1)                           |
| **Scalability**           | Path decoupling, Modular components, Env-agnostic deployment, Plugin registry      | `config/` env override; domain packages `db/`, `vision/`, `labeling/`, `utils/`; `_EXTRA_CHECK_REGISTRY` |
| **Observability**         | Structured logging, Health endpoints, Batch metrics, Data lineage, Version mapping | `JsonFormatter`; `GET /api/health`; `GET /api/metrics`; `batch_lineage` table; `version_info.json`       |


---

## Contributing

Bug reports and feature requests: [open an issue](https://github.com/smileyimao/DataFactory/issues).

This project is designed as a portfolio of industrial MLOps patterns. Pull requests that stay true to the design philosophy (strict decoupling, no over-engineering, raw SQL over ORM) are welcome.

---

## License

[MIT](LICENSE) © 2025 DataFactory Contributors