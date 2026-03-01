# DataFactory

Industrial video pipeline: **raw material → Ingest (pre-filter) → Funnel QC (rule + vision) → Admission (auto-pass + HITL) → archive** (passed / rejected / redundant). Designed for traceability and MLOps; extensible toward v3+ edge and multimodal.

**Why this matters.** LLMs scaled fast because language data is already "curated" by human use. Robotics and autonomy don't have that: data must be collected, cleaned, and labeled at great cost, across many modalities. Human perception works because our senses are effectively **edge pipelines**—they preprocess before feeding the brain. The real bottleneck for the industry is **data quality and supply**. This pipeline aims to be one piece of that infrastructure: a reusable, edge-ready data pipe so that "robot brains" get clean, structured input instead of raw, expensive, unlabeled streams. See **docs/Roadmap.md** (vision / industry perspective) for the full picture.

> **Built for the Unpredictable Edge** — *Reliability as a First-Class Citizen.* Bridging the gap between AI and industrial reality; minimizing technical debt through strict decoupling.

### System overview

![DataFactory Architecture](docs/DataFactory.png)

*Pipeline • System Guarantees • MLOps — automated data flow from ingest to archive, with reliability and continuous evolution built in.*

### Current system status

| Item | Status |
|------|--------|
| **Version** | v3.0 (数据血缘、Model Registry、MLflow 追溯) |
| **Main flow** | Ingest (pre-filter: dedup + decode) → Funnel QC (rule + vision) → Admission (auto-pass + HITL) → Archive |
| **Archive structure** | `Batch_xxx/` with reports, source, refinery, inspection, labeled (labeled return write-back) |
| **Storage** | raw, archive, rejected, redundant, quarantine, reports, for_labeling, labeled_return, training |
| **Next target** | v3.x: Auto-modality routing (audio/lidar/vibration) + 全自动标注闭环 |

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
python main.py --guard               # Guard mode: Watchdog + polling fallback; see docs/architecture.md "Guard mode patrol logic"

# Dashboard (when review.mode=dashboard, blocked items queue for Web review)
python -m dashboard.app              # Start dashboard at http://127.0.0.1:8765
```

First run creates `storage/` and `db/`. Report copies go to `storage/reports/`.

**Scripts**: `python scripts/reset_factory.py` — clean storage; `python scripts/export_for_labeling.py` — export to `storage/for_labeling`; `python scripts/import_labeled_return.py --dir /path` — receive labeled return, compare to pseudo-labels, merge to training; `python scripts/compare_models.py --new X.pt --baseline Y.pt --data DIR` — compare models, log to MLflow/DB; `python scripts/query_lineage.py` — v3 血缘查询; `python scripts/register_model.py path/to/model.pt --name vehicle_detector` — 注册模型到 MLflow Registry.

**Optimization log**: `docs/optimization_log.md` — 产线 IE（持续优化）记录：瓶颈、根因、方案、教训。Auto pipeline 需持续迭代，优化即财富。

**Tests**: After `pip install -r requirements-dev.txt`, run `pytest tests/ -v -m "not e2e"`; e2e requires test videos in `paths.test_source` (default `storage/test/original/`). Full pipeline: `python main.py --test`. See `tests/README.md`.

---

## Design philosophy (industry vocabulary)

For readers familiar with industrial / MLOps terminology, the design maps as follows:

| Pillar | Keywords | Where in DataFactory |
|--------|----------|----------------------|
| **Core Workflow & Orchestration** | Automated Data Pipeline, End-to-End Life Cycle Management, Smart Ingestion (v2.6), Batch-Centric Processing, Human-in-the-Loop (HITL), Production-Ready Archives | pipeline → Ingest → Funnel QC → Admission → Archive；reports/source/refinery/inspection |
| **Defensive Engineering & Robustness** | Poka-Yoke Design, Fault-Tolerant I/O, Backoff Retry Logic, Path Traversal Sanitization, Sanity Checks & Config Validation, Graceful Degradation / Failing Fast | retry_utils, db_tools error handling, get_thumbnail Path.resolve(), validate_config, init_db exit(1) |
| **Scalability & Extensibility** | Path Decoupling / Hardware Abstraction, Modular Component Architecture, Environment-Agnostic Deployment, Scalable Plugin Registry (extra QC checks), Headless & Guard Mode | config paths + DATAFACTORY_* env override；engines/ modular；quality_tools._EXTRA_CHECK_REGISTRY；main.py --guard |
| **Observability & Quality Assurance** | Structured Industry Logging, Health Check Endpoints, Real-time Batch Metrics, Data Lineage Tracking, Version Mapping (Data-Model-Code) | RotatingFileHandler；GET /api/health；GET /api/metrics；fingerprint + batch_id + archive path；version_info.json |

---

## Implemented features (summary)

| Phase | Features | Status |
|-------|----------|--------|
| **v1 / v1.5 / v1.6** | Funnel QC, Admission, archive, Logging, physical isolation, config-driven, engine layering | ✅ |
| **v2.x** | YOLO, dual gate, MLflow, confidence-tiered output, pseudo-labels, industrial/vision reports | ✅ |
| **v2.5** | Inspection flattening, labeling pool auto-update, model comparison, dashboard, labeled return vs pseudo-label validation | ✅ |
| **v2.6** | Smart Ingest: I-frame, motion wake-up, cascade detection (4 optimizations) | ✅ |
| **v2.7** | Industrial hardening: Path decoupling, P0/P1/P2/P3 (retry, DB error handling, health check, configurable timezone/log/email, metrics, config validation) — **critical for Edge deployment** | ✅ |
| **v2.8** | Ingest pre-filter: dedup + first-frame decode, failed items to quarantine — **flow modularization** | ✅ |
| **v2.9** | Modality decoupling: config modality, abstraction layer, reserved for audio/vibration | ✅ |
| **v2.10** | Image 通路、auto-modality、raw 递归扫描、qualified 置信度分流、YOLO 复用 | ✅ |
| **v3.0** | **Model-ready**: batch_lineage、label_import 血缘表；query_lineage.py；MLflow run params 含 refinery/inspection 路径；vision.model_path 支持 models:/name/version；register_model.py | ✅ |
| **v4** | Multimodal, FFT, Edge, multi-node, access control | Design done, pending implementation |

---

## Version overview

Current code covers **v1.x** through **v3.0** (数据血缘、Model Registry、MLflow 追溯). Next target: **v3.x** (Auto-modality routing: audio/lidar/vibration; 全自动标注闭环).

### v1.x — Production pipeline

| Feature | Description |
|--------|-------------|
| **Env-based secrets** | Email password etc. in `.env`, not in config or code. |
| **Admission (auto-pass + HITL)** | One batch fully QC'd ; qualified auto-pass; blocked items get y/n/all/none or dashboard review. |
| **Toronto timezone** | Logs, email, DB, batch_id use America/Toronto. |
| **Structured logging** | `logs/factory_YYYY-MM-DD.log`; fingerprint, duplicate, scores, decisions, moves, timeouts. |
| **Physical archive** | Rejected → `storage/rejected/Batch_xxx_Fails/` (`name_scorepts.ext`); redundant → `storage/redundant/`; passed → `storage/archive/` and DB. |
| **Labeling export** | Optional: `scripts/export_for_labeling.py` writes `storage/for_labeling/manifest_for_labeling.json` for Label Studio / CVAT. |

### v1.5 — Architecture

| Feature | Description |
|--------|-------------|
| **Modular component architecture** | `engines/`: quality_tools, fingerprinter, db_tools, report_tools, production_tools, notifier, file_tools; tools return values only, no pass/fail decision. |
| **Central config** | Paths, thresholds, batch params, email in `config/settings.yaml`; `config_loader` resolves to absolute paths. |
| **Flow vs decision** | Funnel QC in `core/qc_engine`, Admission in `core/reviewer`, archive in `core/archiver`; orchestration in `core/pipeline`. |
| **Single entry** | `main.py` single run or `--guard`; legacy scripts in `legacy/`. |
| **Batch metrics** | Per-batch: file count, size (GB), duration, stage timings (Ingest/Funnel QC/Admission/Archive), throughput; stored in DB `batch_metrics`. |

### v1.6 — Storage and DB

| Feature | Description |
|--------|-------------|
| **Unified storage** | All data under `storage/` (raw, archive, rejected, redundant, test, reports, for_labeling); DB in `db/factory_admin.db`; `init_storage_structure()` on startup. |
| **Report archive** | QC report and chart copied to `storage/reports/` (`{batch_id}_quality_report.html`, `{batch_id}_chart.png`). |

### v2.x — Model and experiments

| Feature | Description |
|--------|-------------|
| **Vision (YOLO)** | Optional AI scan in Funnel QC; config-driven (model path, sample interval, inference params); thumbnails for vision report. |
| **Dual gate** | Configurable high/low thresholds: auto-pass, auto-reject, middle band for human review. |
| **Version mapping (Data-Model-Code)** | Algorithm and vision model version in logs and reports; `version_info.json` per batch; data lineage traceable. |
| **Scalable plugin registry** | `quality_tools._EXTRA_CHECK_REGISTRY`; register extra QC checks without modifying core. |
| **MLflow** | Optional batch-level runs: params, metrics, artifacts (industrial report, vision report). |
| **Industrial / Vision report** | Per-batch HTML; attached to email and MLflow. |

### v2.5 — Data loop and efficiency

| Feature | Description |
|--------|-------------|
| **Inspection flattening** | `human_review_flat=true`: Normal/Warning merged, only manifest+images+txt kept for for_labeling import. |
| **Labeling pool auto-update** | `labeling_pool.auto_update_after_batch=true`: After each batch archive, inspection is auto-appended to for_labeling. |
| **Model comparison** | `scripts/compare_models.py`: Run two models on same data, compare detections, write to MLflow/DB. |
| **Dashboard** | `review.mode=dashboard`: Web review, single/batch approve/reject, no timeout data loss. |
| **Labeled return vs pseudo-label validation** | `scripts/import_labeled_return.py`: Return vs pseudo-label IoU matching, consistency threshold alert, merge to training when compliant; write back to `archive/Batch_xxx/labeled/` by batch_id (safe_copy retry prevents silent failure). |

### v2.6 — Smart Ingest / efficient screening

| Feature | Description |
|--------|-------------|
| **Smart ingestion** | I-frame, motion wake-up, cascade detection; reduce unnecessary decoding and YOLO inference. |
| **I-frame** | `vision.use_i_frame_only=true`: Decode I-frames only (requires ffprobe), reduce decode load; `engines/frame_io.py`. |
| **Motion wake-up** | `vision.motion_threshold`: Skip YOLO when frame diff below threshold; static frames filtered; `engines/motion_filter.py`. |
| **Cascade detection** | `vision.cascade_light_model_path`: Light model pre-screening, main model only when something detected; empty frames filtered. |
| **Embedding/Re-ID** | TODO: vector retrieval, "who-where" reports. |

### v2.7 — Industrial hardening (Path decoupling + Poka yoke)

| Category | Points |
|----------|--------|
| **Path decoupling / Hardware abstraction** | Batch dir names (reports/source/refinery/inspection), batch_prefix, batch_fails_suffix all in `config/settings.yaml`; change names via config only. Supports `DATAFACTORY_*` env override; **environment-agnostic deployment**. |
| **Poka-yoke design** | `validate_config` pre-start validation; `init_db` returns False → exit(1) on DB failure (**failing fast**); thumbnail **path traversal sanitization** (Path.resolve + relative_to). |
| **Fault-tolerant I/O** | `retry_utils.safe_move_with_retry`, `safe_copy_with_retry`: **backoff retry** (attempt × backoff_seconds); move/copy failure logs warning, increments metrics; DB ops catch sqlite3.Error, log and return None/False (**graceful degradation**). |
| **Health check endpoints** | `GET /api/health` checks DB, dir writability, config validation; 503 on failure. |
| **Real-time batch metrics** | `GET /api/metrics`; `engines/metrics.py` counters; qc_engine TemporaryDirectory auto-cleanup; email send retry. |
| **P3 standards** | `pyproject.toml` black + isort + mypy config. |

**Dashboard API** (after `python -m dashboard.app`):
- `GET /api/health` — Health check (DB connectivity, dir writability, config validation); 503 on failure.
- `GET /api/metrics` — Simple counters snapshot (batch_processed_total, file_move_errors_total, file_copy_errors_total, etc.) for monitoring/alerts.

**New modules**: `core/time_utils.py` (timezone), `engines/metrics.py` (counters), `engines/retry_utils.py` (file move/copy retry).

See **docs/path_decoupling.md**, **docs/industrial_standards.md**; CHANGELOG: **CHANGELOG.md**; roadmap: **docs/Roadmap.md**; settings: **docs/settings_guide.md**.

---

## Architecture index

| Layer | Path | Description |
|-------|------|-------------|
| Entry | `main.py` | Single run or **Headless & Guard mode** (`--guard`: Watchdog + polling fallback) |
| Modality | `engines/modality_handlers.py` | decode_check dispatched by modality; v2.9 decoupled, v3 extends audio/vibration |
| Flow | `core/` | pipeline → ingest → qc_engine → reviewer → archiver; time_utils (timezone) |
| Engines | `engines/` | quality_tools, fingerprinter, db_tools, report_tools, production_tools, notifier, vision_detector, motion_filter, frame_io, retry_utils, metrics, labeling_export, labeled_return |
| Config | `config/` | settings.yaml, config_loader; paths and thresholds |
| Models | `models/` | YOLO and cascade .pt; vision.model_path config |
| Storage | `storage/` | raw, archive, rejected, redundant, quarantine, test, reports, for_labeling, labeled_return, training |
| DB | `db/` | factory_admin.db (production_history, batch_metrics), mlflow.db (MLflow experiments, default tracking_uri) |
| Docs | `docs/` | Roadmap, architecture, settings, smart_slicing, **architecture_mindmap** |
| Scripts | `scripts/` | reset_factory, export_for_labeling, import_labeled_return, compare_models |
| Tests | `tests/` | unit, integration, e2e (smoke, main --test, guard), api |
| Legacy | `legacy/` | Old entry scripts, kept for reference |

See **docs/architecture.md**, **docs/architecture_mindmap.md** (architecture skeleton), **docs/settings_guide.md**; **ROOT_LAYOUT.md** for directory layout.

---

## Roadmap (short)

- **v1 / v1.5 / v1.6**: Done. Funnel QC, Admission, archive, metrics, labeling export.
- **v2.x**: Done. Vision, dual gate, MLflow, industrial + vision reports.
- **v2.5**: Done. Inspection flattening, labeling pool auto-update, model comparison, dashboard, labeled return vs pseudo-label validation.
- **v2.6**: Done. Smart Ingest — I-frame, motion wake-up, cascade detection.
- **v2.7**: Done. Industrial hardening — P0/P1/P2/P3, Path decoupling, Batch rename (critical for Edge deployment).
- **v2.8**: Done. Ingest pre-filter — dedup + first-frame decode, quarantine, flow modularization.
- **v2.9**: Done. Modality decoupling — config modality, modality_handlers, reserved for audio/vibration.
- **v2.10**: Done. Image 通路、auto-modality、raw 递归扫描、qualified 按 YOLO 置信度分流、YOLO 复用消除二次推理。
- **v3.x**: Design done, pending implementation. **Model-ready**: data lineage, Transform Log, MLflow data→model traceability; **Auto-modality routing**: auto-detect and route by file; Backward Compatibility.
- **v4.x**: Design done, pending implementation. **Scale & extension**: multimodal, Temporal Sync (observed_at), Resource Locking (Edge), FFT, Edge, multi-node, access control.

See **docs/Roadmap.md**.

---

## Edge deployment: why it fits remote / mining sites

**Built for the Unpredictable Edge.** This pipeline is designed so that **v4-style edge deployment** keeps raw data on site and only sends small outputs out. That makes it a good fit for mines and other remote sites where bandwidth is expensive and data sovereignty matters.

| Benefit | What it means |
|--------|----------------|
| **Raw data stays on site** | Video and sensor data are processed at the edge (mine/field). Only **results** leave: batch IDs, scores, fingerprints, Funnel QC reports (JSON/HTML), and optionally **curated outputs** (e.g. key frames, bbox crops) for training. No need to ship full video streams or disks. |
| **Cost controllable** | Transfer drops from GB to KB (metadata + reports) or to a small set of images (key frames / training samples). Cheaper and more predictable than dedicated lines or frequent physical handoffs. |
| **Easier for the site to accept** | The site does not have to "open a data pipe" for raw access. They run the pipeline locally; only summaries and agreed outputs are sent. Responsibility and compliance stay clear. |
| **Cheaper than sending people** | No need for routine trips to collect disks. Deploy once at the edge; sync results on a schedule or on demand. Operational and training data (curated images) remain small. |
| **Remote model updates are small** | Pushing a new model to the edge is a single download (e.g. one `.pt` file, on the order of MB). Much smaller than raw video; hot-push or scheduled model/config updates are bandwidth-friendly. |

**In short**: the mine keeps the raw data; the pipeline runs there and only "finished products" (reports, metrics, and optionally key frames / training samples) go out. That keeps cost down and makes edge deployment something sites can accept. **Data lineage tracking** (fingerprint, batch_id, archive path, version_info) ensures each file's provenance is traceable. See **docs/Roadmap.md** (v4 Edge Deployment, multi-node deployment) for the full design.

---

## Verification checklist (per-module)

| Module | Verification |
|--------|--------------|
| Inspection flattening | When `human_review_flat=true`, inspection has no Normal/Warning subdirs, for_labeling import works |
| Labeling pool auto-update | After archive, for_labeling auto-appends batch inspection, manifest merge correct |
| Model comparison | `compare_models.py` runs, MLflow/DB has records |
| I-frame | `use_i_frame_only=true` + ffprobe present: decode I-frames only; fallback to per-second when no ffprobe |
| Motion wake-up | When `motion_threshold>0`, static frames skip YOLO, log shows "4 optimizations filter" |
| Cascade detection | When `cascade_light_model_path` configured, empty frames filtered by light model |
| **v2.7 Industrial hardening** | `GET /api/health` returns 200; `GET /api/metrics` has counters; timezone config change affects log timezone; `validate_config` returns error on invalid config |

See **docs/testing_and_audit.md** (dry run, flow tracing, legacy audit).
