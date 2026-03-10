# Changelog

All notable changes to DataFactory are documented here.

---

## [2026-03-09] Local-Mode Demo Hardening + Real Frame Count

- **TYPE**: UX / RELIABILITY / DATA ACCURACY
- **CHANGE**: Full local-mode support (SQLite fallback, one-command startup), real frame count tracking in DB, Sentinel stability fixes, CVAT confidence annotation fix.

**Local mode**:
- **`config/config_loader.py`**: `DATABASE_URL` unset → auto-fallback to `storage/factory_admin.db` (SQLite); all three injection sites updated.
- **`scripts/start_local.sh`** (new): One-command `datafactory` alias launcher via osascript; opens Review/Sentinel/HQ/MLflow/Pipeline in separate Terminal tabs.
- **`scripts/reset_factory.py`**: SQLite cleanup support — deletes `factory_admin.db` and `db/mlflow.db` when `DATABASE_URL` is not PostgreSQL.

**Sentinel stability**:
- **`dashboard/sensor_module.py`**: `ArchiveDataSource` no longer raises `FileNotFoundError` when archive is empty; polls every 5s until pipeline produces frames.
- **`dashboard/sentinel.py`**: `--fps` defaults to `2` for `--source archive`, `30` for mock/live — no manual flag needed.

**Real frame count**:
- **`db/db_tools.py`**: `batch_metrics` table gains `frame_count INTEGER` column; `ALTER TABLE` migration for existing DBs; `record_batch_metrics()` accepts `frame_count` parameter.
- **`core/archiver.py`**: `_run_produce_chunk()` and `archive_produced()` return actual frame count written.
- **`core/pipeline.py`**: `frame_count` collected from `archive_produced()` and stored via `_batch_summary()`.
- **`dashboard/hq.py`**: Gold Assets reads `SUM(frame_count)` (real frames, no base offset, no estimation scale factor).

**CVAT / annotation**:
- **`scripts/cvat/cvat_api.py`**: Confidence attribute `values` fixed to `["0","1","0.0001"]` (number type requires min/max/step).
- **`scripts/export_for_cvat_native.py`**: XML number values use `\n`-separated format (`0.0\n1.0\n0.0001`).
- **`dashboard/inference_module.py`**: Proportional font sizing (`H//30`), RGB-safe label backgrounds, COCO class name lookup, amber/green confidence color coding.

---

## [2026-03-06] P0 Compliance: Atomic Writes + Observability + Schema Validation

- **TYPE**: RELIABILITY / OBSERVABILITY / INTEGRITY / SECURITY
- **CHANGE**: Full audit against `.cursor/rules/compliance.mdc`; fix all P0 violations.
- **IMPACT**: Ingest → QC → Admission → Archive; all manifest/config/report writes; pipeline and guard logging.
- **PROTOCOL**: P0 Reliability (temp → fsync → replace); P0 Observability (structured logger, batch_id context); P0 Integrity (manifest schema check); P0 Security (no hardcoded secrets).

**Atomic writes (P0 Reliability)**:
- **`utils/file_tools.py`**: New `atomic_write_text()` and `atomic_write_json()` (temp file → flush → fsync → replace).
- **`utils/usage_tracker.py`**: `_save()` now uses `file_tools.atomic_write_json()` (with fsync).
- **`core/qc_engine.py`**: `version_info.json`, QC manifest writes (2 处) via `file_tools.atomic_write_json()`.
- **`core/pending_queue.py`**: Queue JSON (add_items, _save_queue) via `file_tools.atomic_write_json()`.
- **`labeling/labeling_export.py`**: `manifest_for_labeling.json` and pool manifest via `atomic_write_json()`.
- **`utils/report_tools.py`**: All report outputs (JSON manifest, quality_report.html, batch_industrial_report.html, vision_report.html) via `atomic_write_text` / `atomic_write_json`.
- **`labeling/labeled_return.py`**: `comparison_report.json` via `atomic_write_json()`.
- **`vision/production_tools.py`**: Pseudo-label `.txt` files via `atomic_write_text()`.
- **`labeling/annotation_upload.py`**: SAM polygon `.poly.json` via `atomic_write_json()`.
- **`dashboard/sentinel.py`**: CSV session log header via `atomic_write_text()`.

**Observability (P0)**:
- **`core/qc_engine.py`**, **`core/archiver.py`**, **`core/guard.py`**, **`core/pipeline.py`**, **`core/ingest.py`**: All `print()` replaced with `logger.info` / `logger.warning` / `logger.exception` (batch_id / context preserved).
- **`vision/production_tools.py`**, **`labeling/labeled_return.py`**, **`labeling/annotation_upload.py`**: Same; `logger` added where missing.
- **`vision/vision_detector.py`**: YOLO scan status `print()` → `logger.info`.
- **`utils/notifier.py`**: Redundant `print()` removed (already has `logger.warning`).
- **`utils/logging.py`**: `console=True` parameter on all production entry points (`main.py`, `tools.py`), so structured logs appear on terminal in real time.

**Schema validation (P0 Integrity)**:
- **`core/qc_engine.py`**: Manifest items validated for required fields (`file`, `score`) after JSON load; malformed entries logged and skipped.

**Security (P0)**:
- **`docker-compose.yml`**: `POSTGRES_DB/USER/PASSWORD` now read from environment variables with safe defaults (`${POSTGRES_PASSWORD:-datafactory}`), eliminating hardcoded credentials.

---

## v3.9 — Foundation Models + Ops Tooling

- **`vision/foundation_models.py`** (new): `ClipEmbedder` (semantic dedup, FPS diversity sampling, scene classification) + `SamRefiner` (bbox→polygon); lazy-loaded, gracefully degrade to `None` when packages absent
- **Feature 1 — CLIP semantic dedup** (`core/ingest.py`): cosine-similarity gate after MD5 dedup; near-duplicates move to `quarantine/semantic_dup/`; opt-in via `clip_semantic_dedup_enabled`
- **Feature 2 — CLIP diversity sampling** (`labeling/labeling_export.py`): farthest-point sampling replaces stratified-by-video in refinery export; opt-in via `clip_diversity_sampling_enabled`; fallback to stratified on error
- **Feature 3 — CLIP scene classification** (`core/qc_engine.py`): per-video scene label (e.g. `underground_tunnel`); `scene_thresholds` in config auto-overrides `quality_thresholds`; opt-in via `clip_scene_classify_enabled`
- **Feature 4 — SAM polygon pre-annotation** (`labeling/annotation_upload.py`, `scripts/export_for_cvat_native.py`): YOLO bbox → SAM mask → `{base}.poly.json` sidecar → `<polygon>` in CVAT native XML; opt-in via `sam_cvat_enabled`
- **`utils/system_probe.py`** (new): `detect_capabilities()` (CPU/GPU/RAM/VRAM/device/Apple Silicon); `auto_configure()` 6-tier decision tree; `print_system_info()`; runs at `load_config()` time, respects `foundation_models.override: true`
- **`utils/usage_tracker.py`** (new): `track(feature)` / `report(days)` / `reset(feature|None)`; atomic JSON persistence; daily bucketing; 3-tier suggestion (✅ / ⚠️ / ❌)
- **`tools.py`** (new, project root): ops CLI — `--probe`, `--test [--gate N]`, `--usage-report [--days N]`, `--usage-reset FEATURE|all`; full-pipeline test runs in `tempfile.TemporaryDirectory`, never touches real storage
- **`main.py`** cleanup: `--test`, `--usage-report`, `--usage-reset` removed (now in `tools.py`); pipeline-only flags remain
- **`config/settings.yaml`**: new `§10 foundation_models:` section (all flags `false`; `override: false`; `scene_thresholds` presets for underground/dusty/open-pit)
- **`pyproject.toml`**: version `3.9`; `slow` pytest marker registered

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
