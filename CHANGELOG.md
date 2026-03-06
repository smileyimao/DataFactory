# Changelog

All notable changes to DataFactory are documented here.

---

## v3.8 — Mining Data Augmentation

- `train_model.py --augment mining/default/off` CLI flag
- Mining preset: brightness variation, blur (dust simulation), random erasing (occlusion), rotation (rough terrain)
- `augment_preset` logged to MLflow params

---

## v3.5 — P0–P3 Production Hardening

- Pipeline top-level exception capture; atomic manifest write
- Guard recursion → loop; SQLite guard; `threading.Lock` on global config
- `qc_engine` SRP refactor (8 sub-functions)
- PostgreSQL `ThreadedConnectionPool` (zero call-site changes via `_PooledConn` proxy)
- `DATAFACTORY_QT__*` / `DATAFACTORY_PS__*` per-section env override with type preservation
- JSON structured logging (`JsonFormatter`; enabled via `DATAFACTORY_LOG_FORMAT=json`)
- `/health` endpoint in guard mode (`ingest.health_port`)

---

## v3.4 — Domain-Driven Package Structure

- `engines/` split into `db/` (db_connection, db_tools), `vision/` (detector, quality, motion, frame_io, production_tools), `labeling/` (export, return, upload)

---

## v3.3 — Package Cleanup

- `utils/` extracted: logging, startup, fingerprinter, retry_utils, file_tools, notifier, time_utils
- `scripts/` reorganized into `cvat/`, `mlflow/`, `db/`
- P0 disk protection

---

## v3.2 — SQLite → PostgreSQL

- Thin adapter layer (`db/db_connection.py`): `is_postgres`, `ph`, `upsert_sql`, `connect`
- `DATABASE_URL` env var selects backend; SQLite fallback for local dev
- `docker-compose.yml` PostgreSQL 16-alpine
- Idempotent `migrate_sqlite_to_pg.py`

---

## v3.1 — Full Closed Loop

- Local CVAT Docker deployment (one-time setup)
- `cvat_pull_annotations.py`: CVAT XML → YOLO format, IoU consistency check, merge to training set
- `train_model.py`: YOLOv8 train, MLflow pyfunc register, `model_train` lineage record
- `main.py --auto-cvat`: end-to-end from archive to CVAT task creation

---

## v3.0 — Model-Ready Lineage

- `batch_lineage`, `label_import` DB tables
- `query_lineage.py`: CLI for batch, import, and training history
- MLflow run params include refinery/inspection paths
- `vision.model_path` supports `models:/name/version` URI
- `register_model.py`

---

## v2.10 — Image Pipeline

- Full image modality path (`image_mode: auto/true/false/both`)
- Auto-modality detection; recursive scan of `raw/`
- Confidence-tiered output for image batches; YOLO inference reuse

---

## v2.9 — Modality Decoupling

- `config.modality` field; abstraction layer for video/image/audio
- Reserved extension points for audio and vibration modalities

---

## v2.8 — Ingest Pre-Filter

- MD5 dedup at ingest; first-frame decode check
- Failed items moved to `quarantine/` with reason logged
- Flow modularization: `core/ingest.py` extracted

---

## v2.7 — Industrial Hardening (Path Decoupling + Poka-Yoke)

- All batch subdirectory names (reports/source/refinery/inspection) configurable in YAML
- `DATAFACTORY_*` env override for all config keys
- `validate_config` pre-start check; `init_db` failing fast on DB error
- `retry_utils`: backoff retry for file move/copy (NFS resilience)
- `GET /api/health`, `GET /api/metrics` dashboard endpoints
- Email retry; TemporaryDirectory auto-cleanup in qc_engine

---

## v2.6 — Smart Ingest

- I-frame decode (`vision.use_i_frame_only=true`, requires ffprobe)
- Motion wake-up: skip YOLO when frame diff below threshold
- Cascade detection: light model pre-screens; main model only when triggered

---

## v2.5 — Data Loop and Efficiency

- Inspection flattening (`human_review_flat=true`): Normal/Warning merged
- Labeling pool auto-update: inspection auto-appended to `for_labeling/` after each batch
- `compare_models.py`: A/B model comparison, logged to MLflow and DB
- Dashboard web review (`review.mode=dashboard`)
- `import_labeled_return.py`: IoU matching vs pseudo-labels, consistency threshold alert, merge to training

---

## v2.x — Model and Experiments

- YOLO integration: optional AI scan in Funnel QC; confidence-tiered output (refinery / inspection)
- Dual gate: high/low thresholds → auto-pass / human review / auto-reject
- Version mapping: algorithm version + vision model version in logs, reports, and `version_info.json`
- Scalable plugin registry: `quality_tools._EXTRA_CHECK_REGISTRY`
- MLflow: batch-level runs with params, metrics, HTML report artifacts
- Industrial and vision HTML reports per batch

---

## v1.6 — Storage and DB

- Unified storage layout: all data under `storage/`; DB at `db/factory_admin.db`
- `init_storage_structure()` on startup; QC report and chart copied to `storage/reports/`

---

## v1.5 — Architecture

- Modular component architecture: `engines/` layer (tools return values, no pass/fail)
- Central config: `config/settings.yaml`, resolved to absolute paths by `config_loader`
- Flow separation: Funnel QC → Admission → Archive; orchestration in `core/pipeline`
- Batch metrics: per-batch file count, size, duration, stage timings; stored in `batch_metrics` table

---

## v1.x — Production Pipeline

- Funnel QC: brightness, blur, contrast, jitter checks; per-frame scoring
- Admission: auto-pass gate + HITL terminal/dashboard review
- Physical archive: rejected → `Batch_xxx_Fails/`; redundant → `redundant/`; passed → `archive/` + DB
- Env-based secrets: email credentials in `.env`, never in config or code
- Structured logging: `logs/factory_YYYY-MM-DD.log`; fingerprint, dedup, scores, decisions, moves
