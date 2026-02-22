# DataFactory

Industrial video QC pipeline: **raw material → QC (duplicate + quality + optional AI) → human review → archive** (passed / rejected / redundant). Designed for traceability and MLOps; extensible toward v3+ edge and multimodal.

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
python main.py --guard               # Guard mode: watch storage/raw and run QC when new videos land (Watchdog)
```

First run creates `storage/` and `db/`. Report copies go to `storage/reports/`.

**Scripts**: `python scripts/reset_factory.py` — clean storage dirs (default dry-run; `--target archive/rejected/redundant/db` requires `--confirm-dangerous`; `--target db` clears MD5 history so the same videos are not treated as duplicates); `python scripts/reset_config.py` — restore `config/settings.yaml` to factory default (backs up current); `python scripts/export_for_labeling.py` — export passed batches for labeling; `python tests/smoke_test.py` — smoke test (test data + QC + assertions); `python tests/test_dual_gate_mlflow.py` — dual-gate + email + MLflow test.

---

## Version overview

Current code covers **v1.x**, **v1.5**, **v1.6**, and **v2.x** (model + experiments). Next target: **v2.5** (data loop, pseudo-labels, training trigger).

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

### v2.x — Model and experiments (current)

| Feature | Description |
|--------|-------------|
| **Vision (YOLO)** | Optional AI scan in QC; config-driven (model path, sample interval, inference params); thumbnails for vision report. |
| **Dual gate** | Configurable high/low thresholds: auto-pass, auto-reject, middle band for human review. |
| **Version mapping** | Algorithm and vision model version in logs and reports; `version_info.json` per batch. |
| **MLflow** | Optional batch-level runs: params, metrics, artifacts (industrial report, vision report). |
| **Industrial report** | Per-batch HTML: pass/review/reject/duplicate counts and per-item table; attached to email and MLflow. |
| **Vision report** | Smart-detection HTML with per-video stats and detection thumbnails; attached to email and MLflow. |
| **Extensible QC** | Quality checks pluggable; rule-based blur/brightness/jitter plus optional model. |

Details: **CHANGELOG.md**; roadmap and checklist: **docs/Roadmap.md**, **docs/implementation_checklist.md**.

---

## Architecture index

| Layer | Path | Description |
|-------|------|-------------|
| Entry | `main.py` | Single run or Guard |
| Flow | `core/` | pipeline → ingest → qc_engine → reviewer → archiver |
| Engines | `engines/` | quality_tools, fingerprinter, db_tools, report_tools, production_tools, notifier, vision_detector, report_tools |
| Config | `config/` | settings.yaml, config_loader; paths and thresholds |
| Storage | `storage/` | raw, archive, rejected, redundant, test, reports, for_labeling |
| DB | `db/` | factory_admin.db (production_history, batch_metrics) |
| Docs | `docs/` | Roadmap, architecture, settings, checklist |
| Scripts | `scripts/` | reset_factory, reset_config, export_for_labeling |
| Tests | `tests/` | smoke_test, test_dual_gate_mlflow |
| Legacy | `legacy/` | Old entry scripts, kept for reference |

See **docs/architecture.md**, **docs/settings_guide.md**; **ROOT_LAYOUT.md** for directory layout.

---

## Roadmap (short)

- **v1 / v1.5 / v1.6**: Done. QC, review, archive, metrics, labeling export.
- **v2.x**: Done. Vision, dual gate, MLflow, industrial + vision reports, email attachments.
- **v2.5** (next): Data loop — to-be-labeled pool, pseudo-labels, training trigger.
- **v3.x**: Concurrency, multimodal, cloud/edge (Docker, Prometheus, LiDAR).
- **v4.x**: Deep lineage (transform log, data lineage graph).

See **docs/Roadmap.md** and **docs/v2_kickoff.md**.
