# 🗺️ DataFactory Digital Factory — MLOps Evolution Roadmap (v2026.02)

> **Positioning**: This pipeline targets end-to-end **data ingestion & QC, admission decisions, and traceable archiving**. It can be reused directly for video QC, safety inspection, and perception data curation in mining/industrial scenarios, aligned with AI-driven safety, efficiency, and asset utilization.

---

## 💡 Vision: Connecting AI Brains to High-Quality Data Pipelines

The human brain excels at multimodal processing—touch, vision, hearing—but only when **correct data** flows **steadily and continuously** into it. Then the brain learns the environment and makes better decisions. Our work is the same: feeding high-quality data (QC'd, deduplicated, filtered) continuously to the "brain" to drive its growth.

Edge computing is like the **eye**: the retina does heavy preprocessing locally (brightness adaptation, edge enhancement, motion detection) before sending structured signals to the brain, not raw pixels. The edge nodes in this pipeline (on-site QC, golden run self-check, summary-only upload to center) play a similar role: ensuring what reaches the "brain" is clean, usable, and stable data.

**Industry perspective**: LLMs scaled fast because language data is effectively "labeled" by human use. Robotics and autonomy are different: companies must invest heavily in collection, cleaning, and labeling across more modalities. The real bottleneck is **data quality and supply**. This pipeline's mission is to address that.

*(2026.02 design rationale and analogies recorded here for future multimodal and edge deployment.)*

---

## 📐 System Architecture (Target)

*Main data flow: raw data enters QC, QC splits into two categories, then flows to review and archive.*

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Ingest                                                                          │
│  raw_video/  [done]     raw_lidar/  [v4 extension]                               │
│  Auto-modality routing  [v3]: auto-detect by format/content → video/audio/lidar/vibration routing │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Funnel QC — Two categories, extensible                                          │
│  (1) Duplicate detection [done]  MD5/fingerprint → DB lookup → hits to redundant_archives │
│  (1a) Ingest pre-filter [v2.8] dedup + first-frame decode → failures to quarantine/duplicate, quarantine/decode_failed │
│  (1b) Corrupted video [v2.8 partial] first-frame decode fail → quarantine/decode_failed; full QC still in pipeline │
│  (2) Quality check [done] blur/brightness/jitter + extensible (register_extra_check)     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Admission [done]  Auto-pass + HITL; email summary → Terminal y/n or Dashboard Web review (no timeout loss)  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Archive [done]                                                                  │
│  Batch_xxx/source  source video  |  Batch_xxx/reports  quality reports          │
│  refinery (with pseudo-label .txt)  |  inspection (batch-copyable)                │
│  rejected_material/  failed  |  redundant_archives/  duplicates                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Edge (v4)**: Run full pipeline on-site, send only result summaries to center (with **feature extraction upfront**: vectors + metadata; key frames/segments stored locally, **on-demand return**); **Edge auto-cleanup (v4)**: duplicates configurable delete or rolling cleanup; corrupted videos moved or deleted after readability check.

---

## 🧭 Architecture Principles & Version Overview

**Unified architecture**: Flow (Ingest → Funnel QC → Admission → Archive) + tools (engines/) + decisions in core/ + config (config/). Tools return values only; decision layer reads config and judges.

**Version overview** (framework unchanged, progress only):

| Version | Status | Core content |
|---------|--------|--------------|
| **v1.x** | ✅ Done | Flow working, human-in-the-loop, traceable, industrial logging, physical archive |
| **v1.5** | ✅ Done | Architecture refactor: config + engines + core, no new business |
| **v2.x** | ✅ Mostly done | YOLO, version mapping, dual gate, MLflow, confidence-tiered output, pseudo-labels, extensible QC; TODO: model registry & reproducibility |
| **v2.5** | ✅ Done | Confidence split, dashboard, inspection flattening, labeling pool auto-update, model comparison |
| **v2.6** | ✅ Done | Smart Ingest / efficient screening: I-frame, motion wake-up, cascade detection |
| **v2.7** | ✅ Done | Industrial hardening: P0/P1/P2/P3, Path decoupling, Batch rename — **critical for Edge deployment** |
| **v2.8** | ✅ Done | Ingest pre-filter: dedup + first-frame decode, failures to quarantine — **flow modularization** |
| **v2.9** | ✅ Done | Modality decoupling; hardening: MLflow→db/mlflow.db, labeled subdir, safe_copy anti-silent-fail, pytest suite; root cleanup |
| **v3.x** | ⬜ TODO | **Model-ready**: data lineage, Transform Log, MLflow data→model traceability; **Auto-modality routing**: auto-detect and route by file |
| **v4.x** | ⬜ TODO | **Scale & extension**: multimodal (audio/vibration), FFT, predictive maintenance, Edge, multi-node |

---

## 🚗 Role & Collaboration Boundary (Vehicle vs Engine)

We build the **vehicle**; the model team builds the **engine**. We own the pipeline (Ingest → Funnel QC → Admission → Archive), config, deployment, and observability; they own model training and release. We **provide interfaces** (e.g. `run_vision_scan(cfg, video_paths)`); model team supplies `.pt` or implements the interface. Same pipeline + same config when deployed to Edge; responsibility is clear.

---

## 🔄 CI/CD & Deployability

| Dimension | Current | Notes |
|-----------|---------|-------|
| Config vs code separation | settings.yaml + .env | Change config to switch env, no code change |
| Single entry | main.py (single run / --guard) | Easy to test and deploy |
| Startup self-check | startup_self_check | Path and writability validation |
| Golden run (optional) | startup_golden_run | Real QC smoke run |
| Smoke / full-pipeline test | pytest tests/e2e/, main.py --test | QC smoke, full pipeline, Guard mode |
| Unit / integration test | pytest tests/ -v -m "not e2e" | unit/integration/api layers; requirements-dev.txt |
| Env reset | scripts/reset_factory.py, reset_config.py | dry-run / for-test / db; reset_config restores settings.default.yaml |
| Version traceability | version_mapping, version_info.json, path_info | Per-batch rule/model version auditable |
| **TODO** | CI auto-run pytest, main.py --test, v3 Docker | Design supports it, pipeline pending |

---

## 📈 Scale & Multi-Node (Design ready, implementation in v4)

**Positioning**: The system is the company's "senses"—Ingest → QC at the edge, send only summaries to the "brain", control bandwidth and cost.

**Extension forms**: Single node (current) → multi-Worker (v4 message queue + parallel) → Edge+center (v4 run four steps on-site, summaries only). Four-step skeleton unchanged; added are node count and topology.

**Multi-node design points** (details in later sections, implementation in v4):
- **Conflict avoidance**: node_id + global batch_id, no DB/dir collision.
- **Coordination**: Partition by source (each node local raw) or center-assigned tasks.
- **Center consolidation**: Receive summaries, cross-node dedup, distribute to labeling/training/ops.

---

## 🔀 Multi-Node Deployment: Conflict, Coordination & Center Summary

| Conflict type | Mitigation |
|---------------|------------|
| Batch ID / DB / dir collision | node_id + local timestamp (or UUID) as global batch_id |
| Duplicate processing of same data | Source partitioning (each node consumes specified dir only) or center-assigned tasks |

**Center**: Receive summaries from nodes → store in DB, dedup, distribute by batch/node/time. **Implementation** see Phase 3 "Multi-node deployment".

---

## 🏗️ Phase 1: Standardization & Refined Production (v1.x) — ✅ Done

*Core: Industrial admission, human-in-the-loop, traceable*

- [x] Env variable management (.env for secrets)
- [x] Batch review pipeline (centralized approval, one email, y/n/all/none)
- [x] Toronto timezone localization (logs, email, DB)
- [x] Industrial logging (`logs/factory_YYYY-MM-DD.log`)
- [x] Physical archive (rejected_material/Batch_ID_Fails, redundant_archives, failed items `name_scorepts`)
- [ ] Data cleaning & labeling pipeline extension (for ML integration)

---

## 🔧 Phase 1.5: Architecture Refactor (v1.5) — ✅ Done

*Core: Flow + tools + decisions + config split, foundation for v2*

- [x] Centralized config (config/settings.yaml, config_loader)
- [x] Tool extraction (engines/: quality_tools, fingerprinter, db_tools, notifier, file_tools, report_tools, production_tools)
- [x] Decision separation (qc_engine, reviewer, archiver)
- [x] Flow refactor (core/ingest, qc_engine, reviewer, archiver, pipeline, guard)
- [x] Entry & compatibility (main.py single run / --guard)
- [x] Basic metrics (batch file count, size, duration, throughput, etc.)

---

## 🧠 Phase 2: Vision & Automated Admission (v2.x) — ✅ Mostly Done

*Core: YOLO, version mapping, dual gate, MLflow, confidence-tiered output, extensible QC*

**Done**

- [x] **Computer vision QC**: YOLO singleton, config-driven sampling & inference (conf/iou/device etc.), decisions in qc_engine
- [x] **Version mapping**: Batch_xxx/reports/version_info.json, path_info.version_mapping, for lineage & audit
- [x] **Dual gate admission**: dual_gate_high / dual_gate_low; high auto-pass, low auto-reject, middle human review
- [x] **MLflow tracking**: mlflow.enabled; batch-level params/metrics
- [x] **Confidence-tiered output**: refinery, inspection (manifest, pseudo-label .txt), quality reports in Batch_xxx/reports
- [x] **Extensible QC**: quality_tools.register_extra_check, decide_env unified dispatch

**TODO**

- [ ] **Model registry & reproducibility**: model registry + training/eval pipeline integration

**Planned (no main flow change)**

- **Multi-model**: Config/registry + unified inference interface, select by task after registration
- **Model param UI**: Per-model config or small Web/API; model owners edit only their params; can integrate with MLflow

---

## 🔄 Phase 2.5: Data Loop & Continuous Learning (v2.5) — 🔶 Partially Done

*Core: Confidence split → labeling pool / pseudo-labels → training trigger → model comparison*

**Done**

- [x] **Confidence split**: Integrates with dual gate; high auto-pass, low auto-reject, middle to inspection
- [x] **Confidence-tiered output**: refinery, inspection, with manifest and pseudo-label .txt
- [x] **High-confidence pseudo-labels**: Fuel and human-review write YOLO-format .txt (empty when no detection), for labeling tool alignment
- [x] **YOLO screening output**: `production_setting.save_only_screened=true` outputs only "Warning or detected" frames, reduces full slicing (see docs/smart_slicing.md)

**TODO**

- [x] **Inspection flattening**: Normal/Warning merged, only manifest.json + images + txt, for for_labeling import (`production_setting.human_review_flat=true`)
- [x] **Labeling pool auto-update**: Low-confidence/uncertain samples auto-write to for_labeling + manifest, filter by batch or threshold (`labeling_pool.auto_update_after_batch=true`, auto-append after archive)
- [x] **Model comparison**: New vs online/registered model offline or online comparison, results to MLflow/DB, supports release decision (`scripts/compare_models.py --new X --baseline Y --data DIR`)

### Labeled Return & Pseudo-Label Consistency Validation (Multi-Stage Purification)

*Goal: Establish labeling team return path, use pseudo-label sampling for consistency check, iterate for purer AI fuel.*

**Flow**

1. **Pseudo-label sampling**: Sample from refinery (e.g. 5%–10%) to for_labeling for labeling team.
2. **Return path**: After labeling, team returns in one batch (YOLO/COCO etc.), lands in specified dir (e.g. `storage/labeled_return/`).
3. **Consistency comparison**: Return labels vs pseudo-labels per-image (IoU, class, box count), compute consistency rate.
4. **Threshold & alert**: Set diff threshold (e.g. consistency < 95% auto-alert), require re-review of diffs.
5. **Iterative purification**: Update labels after review → compare again → merge to training when compliant; continue review if not. Multi-round iteration for purer AI fuel.

**Implementation**

- [x] **Return receive**: Labeled data one-shot import (dir/zip), write to `storage/labeled_return/` and create Import_YYYYMMDD_HHMMSS
- [x] **Pseudo-label comparison**: Return vs pseudo-label consistency (IoU 0.5 + class match), output `comparison_report.json` diff report
- [x] **Threshold & alert**: Config consistency threshold (e.g. 95%), below triggers email alert (`labeled_return.alert_via_email`), mark diff samples for review
- [x] **Training trigger**: Compliant data merged to `storage/training/Import_xxx/`, linked to import_id
- [x] **Label write-back to batch**: After compliant, write back to `archive/Batch_xxx/labeled/` by batch_id, safe_copy prevents silent failure
- [ ] **API upload**: Optional HTTP upload for return zip (reserved)

**Done criteria**: Return path working; pseudo-label sampling and consistency check runnable; threshold alert active; training trigger has clear entry.

---

## 🖥️ Dashboard & Remote Access (Done + Reserved Interfaces)

*Core: Web review replaces Terminal blocking, extension points for remote ops*

**Done**

- [x] **Dashboard**: When `review.mode=dashboard`, blocked items queue; `python -m dashboard.app` starts Web UI
- [x] **Queue review**: Thumbnails, scores, rule breakdown, single/batch approve or reject, no 600s timeout data loss
- [x] **LAN access**: `host=0.0.0.0`, same-network devices can access `http://<machine-IP>:8765`

**Remote access reserved (v3 or later)**

| Capability | Current | Reserved / TODO |
|------------|---------|-----------------|
| Listen address | `0.0.0.0` (LAN supported) | Config `paths.dashboard_host` for extension |
| Port | `paths.dashboard_port` | Configurable |
| WAN access | Manual port forward / VPN | Reserved: reverse proxy docs, tunnel example |
| Auth | None | Reserved: API middleware or Basic Auth, frontend login |
| Multi-user / access control | None | Reserved: align with v4 access control |

**Implementation note**: Dashboard is FastAPI; add auth middleware, `/api/` prefix, CORS in `dashboard/app.py` later without changing main flow.

---

## ⚡ Efficient Screening (Industry Four Optimizations)

*Goal: Reduce compute in "decode + detect" phase, not just output filtering. All four can plug into current pipeline for "coarse then fine" wake-up chain.*

### 1. Key-Frame / I-Frame Extraction

- **Principle**: Video = I-frames (full image) + P/B-frames (pixel diff). Scan only I-frames (e.g. 1–2/sec); if I-frame has no target, skip P/B decode.
- **Integration**: In `production_tools` or `engines/frame_io`, use OpenCV/FFmpeg to read I-frames only, run quality + YOLO on I-frames; decode P/B for fine-grained only when hits.
- **Effect**: Compute can drop ~90% (depends on GOP).
- [x] **Done**: `engines/frame_io.py`, config `vision.use_i_frame_only`; production_tools and vision_detector support; needs ffprobe, fallback to per-second sampling.

### 2. Motion Vector / Optical Flow Wake-Up

- **Principle**: Use optical flow or frame diff for motion gradient; when scene is static (no vehicle/person), **don't run YOLO**; only when motion exceeds threshold (e.g. vehicle enters) wake detection.
- **Integration**: In sampling loop, compute OpenCV optical flow or simple frame diff first; below threshold skip detection and output, only mark manifest as "static".
- **Effect**: Fewer GPU wake-ups, lower power and latency.
- [x] **Done**: `engines/motion_filter.py`, config `vision.motion_threshold` (0=off); used with `save_only_screened`.

### 3. Embedding & Re-ID (Vector Index)

- **Principle**: Small model converts image/person to 128/512-dim vector, write to vector DB (Milvus/Faiss); query by "search numbers" not "scan video", millisecond "who appeared in which segment".
- **Integration**: In production or separate indexing task, extract embedding from output key frames (or I-frames), write to vector DB with `batch_id + timestamp`; retrieval API returns (video_id, start_ts, end_ts).
- **Effect**: Supports "who-where" retrieval and reports, parallel to QC/archive, not replacing YOLO.
- [ ] **TODO**: Embedding model, vector DB selection & write, retrieval API; optional Re-ID model integration.

### 4. Cascaded Detectors

- **Principle**: Tiny, low-precision model (hundreds KB) for **pre-screening**; only when it says "something" run YOLO or larger model.
- **Integration**: Add "light detection" layer before `vision_detector` or sampling loop; only when light output exceeds conf threshold call existing `run_vision_scan`.
- **Effect**: Empty frames filtered by light model, large model only on candidate frames; throughput and cost optimized.
- [x] **Done**: Config `vision.cascade_light_model_path`, `cascade_light_conf`; combined with I-frame and motion wake-up.

### Summary

| Tech | Stage | Dependency | Relation to pipeline |
|------|-------|-------------|----------------------|
| I-frame | Decode | OpenCV/FFmpeg | Replace or supplement "per-second full decode" ✅ |
| Motion wake-up | Pre-sample/detect | OpenCV flow/diff | Add check in sampling loop ✅ |
| Embedding/Re-ID | Post-output / separate task | Vector DB, small model | Parallel to QC, retrieval & "who-where" |
| Cascade | Detect | Light .pt / ONNX | Add stage before vision_detector ✅ |

All four combinable: e.g. **I-frame + motion wake-up** reduce decode and wake-ups, **cascade** reduce large-model calls, **Embedding/Re-ID** for retrieval and reports. See **docs/smart_slicing.md** and future "efficient screening" docs.

---

## 🍭 Auto-Modality Routing (Auto-Detect & Route by File) — ⬜ v3 TODO

*Core: Ingest auto-detects modality from format and content, no manual config; mixed data (video+audio+LiDAR+vibration) one scan, auto-routed.*

### Design Goals

| Current | Target |
|---------|--------|
| `config modality: video` manual | Auto-detect: extension + optional content probe → route to channel |
| Single modality per batch | Group by modality, each batch uses own QC/Archive handler |
| Change data type requires config edit | Zero-config: raw dir mixed, auto-route |

### Implementation Steps

#### 1. Detection (Not Fingerprint)

**Not fingerprint**: Fingerprint (MD5) is for dedup (content identity), not format. Modality detection uses:

| Level | Method | Notes |
|-------|--------|------|
| **Extension** | Primary, O(1) | .mp4→video, .wav→audio, .pcd→lidar, .csv→vibration |
| **Magic bytes** | Optional, read header | .bin distinguish lidar point cloud vs vibration binary |
| **Content probe** | Optional | .mp4 ffprobe stream type (video vs audio-only); .csv header for columns |

**Priority**: Extension → hit registry then return; miss or ambiguous (e.g. .bin) → Magic bytes; still unknown → `unknown`.

#### 2. Format→Modality Registry

| Format/Extension | Modality | Notes |
|------------------|----------|-------|
| .mp4, .mov, .avi, .mkv | video | Video container; ffprobe for audio-only |
| .wav, .mp3, .flac, .m4a | audio | Audio |
| .pcd, .las, .ply | lidar | LiDAR point cloud |
| .bin (point cloud) | lidar | Needs Magic bytes or config |
| .csv, .bin (vibration) | vibration | Vibration; .csv header, .bin Magic bytes |
| Unregistered / unknown | unknown | **To quarantine/unknown_format/**, not silently drop |

#### 3. Ingest Changes

```
get_video_paths() / get_raw_paths()
    → Extend to scan_raw(cfg, paths)
    → Per file: detect_modality(path) → "video" | "audio" | "lidar" | "vibration" | "unknown"
    → Group by modality: {video: [p1,p2], audio: [p3], ...}
    → Return groups, or flat with modality tag per item
```

**pre_filter**: Before or after dedup/decode_check, call `modality_handlers.decode_check` by modality.

#### 4. Pipeline Routing

- **Option A**: Batch by modality, each batch runs pipeline (batch_id can have modality suffix, e.g. `Batch_20260224_video`)
- **Option B**: Single mixed batch, pipeline dispatches by file modality to different QC/Archive logic

Recommend **Option A**: Clear batch semantics, simple DB/archive structure.

#### 5. Config Role

| Config | Meaning |
|--------|---------|
| `modality_filter: null` | Process all detected modalities (default) |
| `modality_filter: "video"` | Only video, others skip or quarantine |
| `modality_filter: ["video", "audio"]` | Whitelist, only listed modalities |

#### 6. Unknown Type Handling

- **Default**: Move to `quarantine/unknown_format/`, same level as duplicate, decode_failed; WARNING log.
- **Configurable**: `unknown_format_action: "quarantine"` (default) or `"skip"` (log only, no move).
- **Principle**: No silent drop; human can periodically check quarantine/unknown_format/ and decide to add to registry or delete.

### Relation to Current Architecture

- **modality_handlers** (v2.9): Already has `decode_check(path, cfg)` by modality; entry changes from config to `detect_modality(path)` return
- **Ingest pre_filter** (v2.8): Add modality detection in or before pre_filter
- **Extension**: New modality only needs format→modality registration + handler, no main flow change

### Done Criteria

- [ ] `engines/modality_detector.py`: `detect_modality(path) -> str`, based on extension + optional ffprobe
- [ ] Ingest: `scan_raw` returns grouped by modality; pre_filter calls decode_check per group
- [ ] Pipeline: Support batch by modality or dispatch within single batch
- [ ] Config: `modality_filter` replaces `modality`, backward compatible (modality: video treated as filter)
- [ ] Unknown format: Default to `quarantine/unknown_format/`, config `unknown_format_action`
- [ ] **Backward Compatibility**: Old `modality: "video"` equals `modality_filter: ["video"]`, zero-change migration

### Config Backward Compatibility — v3 Required

**Scenario**: Smooth migration for large deployments; old config `modality: "video"` must not break on update.

**Design**:

- **Keep** `modality: "video"` semantics: Treat as `modality_filter: "video"`, only process video, others skip.
- **Compatible** `modality: "audio"`, `modality: "lidar"` etc.: Equals `modality_filter: ["audio"]`.
- **New config** `modality_filter: null` or `["video","audio"]`: Explicit control.
- **Migration**: config_loader reads; if `modality` exists and no `modality_filter`, set `modality_filter = [modality]`; old config works with zero change.

---

## 🧬 Phase 3: Model-Ready & Deep Lineage (v3.x) — ⬜ TODO

*Core: Data→model traceable, team can run models directly; Deep lineage closes MLflow loop*

**Goal**: After v3, model team can train directly from pipeline output and trace "which model used which data".

### Data Lineage & Transform Log

- [ ] **Transform Log**: Sampling rate, codec, resolution etc. auditable
- [ ] **Lineage visualization**: Per Batch_ID view end-to-end flow (raw → QC → refinery/inspection → labeled → training)
- [ ] **Label write-back link**: After labeling, write back to DB, link to batch/model version

### MLflow Data→Model Traceability

- [ ] **Dataset link**: MLflow run links to training data source (batch_id, refinery/inspection paths)
- [ ] **Model lineage**: Model version traceable to training data batches and transform chain
- [ ] **Reproducibility**: Given model version, trace back training data and QC params

### Labeling Workflow

- [ ] Label Studio/CVAT integration; inspection organized by Batch, batch-copyable
- [ ] After labeling, write back to DB, link to batch/model version

---

## 🐳 Phase 4: Scale & Extension (v4.x) — ⬜ TODO

*Core: High throughput, multimodal, Edge, multi-node, access control*

### Task Orchestration & Monitoring

- [ ] Task state machine (Pending/Processing/Reviewing/Done/Fail)
- [ ] Multi-process / distributed Worker (message queue + parallel QC)
- [ ] Container deployment (Docker) + Prometheus (throughput, latency, pass rate) + Grafana

### Edge Deployment

- [ ] **Scenario**: Run full pipeline on-site, send only result summaries (KB); center consolidates, reviews, archives
- [ ] **Vehicle→site transfer**: Data lands as Ingest input when vehicle returns to hub, connects to existing guard
- [ ] **Tech**: Model lightweighting, edge↔center sync (result upload, config/model download), model hot-update, local data short retention
- [ ] **Privacy & security**: Raw data stays local; center receives summaries/key frames/features only; Edge auto-cleanup duplicates and corrupted (see framework above)

#### Feature Extraction Upfront + On-Demand Return (Mining Bandwidth Scenario)

*Goal: In bandwidth-limited scenarios, Edge returns only light vectors and summaries; key frames/segments stored locally, center pulls on demand.*

| Role | Behavior |
|------|----------|
| **Edge (mine)** | Run full pipeline (can use four optimizations) → key frames/segments local; extract embedding from key frames → **return only**: vectors + manifest/summary (time, camera, targets, etc.) |
| **Center** | Receive vectors, store, retrieval/reports/review; **on demand** request "camera X, time range Y" key frames or short clips from Edge → pull back for labeling/training/archive |

**TODO**

- [ ] **Return protocol**: Edge payload (vectors + metadata + optional thumbnail URL/ID), align with or extend existing summary format
- [ ] **Vector–key-frame link**: Edge writes vectors with `(node_id, batch_id, timestamp, camera)`, center retrieval maps to "requestable segments"
- [ ] **On-demand pull API**: Center → Edge request "node, time range, camera" key frames or segments; Edge returns packed file or stream, lands in center `storage/` then existing Ingest/QC
- [ ] **Deployment**: Edge per **site/hub** (one node per mine or per room), not per camera; same pipeline code at center and Edge, config distinguishes "summary upload only" vs "full local output"

**Relation to four optimizations**: I-frame, motion wake-up, cascade on Edge further reduce compute and bandwidth; Embedding is "feature upfront", vectors returned for center retrieval then trigger on-demand return.

### Multi-Node Deployment

- [ ] node_id and global batch_id (MAC/hostname when unconfigured)
- [ ] Node: Report summaries (HTTP/queue), offline retry (Store-and-Forward)
- [ ] Center: Receive, store, cross-node dedup, distribute (labeling pool manifest / API)
- [ ] Config & deployment docs (main vs node params)

### Multimodal (audio/vibration, LiDAR)

- [ ] **audio/vibration**: modality_handlers extension, FFT spectrum, predictive maintenance
- [ ] **raw_lidar/**: Ingest (.pcd/.las/.ply), point cloud QC, timestamp alignment with video
- [ ] Unified duplicate+quality policy, Batch_xxx/video and Batch_xxx/lidar aligned

#### Cross-Modal Temporal Sync — v4

**Scenario**: Mining vehicle has strong vibration at 10:00; need video and vibration at 10:00 for multimodal fusion.

**Design**: `detect_modality` also extracts **Timestamp**. All modalities must have unified field `observed_at` (or `timestamp`) on storage.

| Modality | Timestamp source |
|----------|------------------|
| video | File metadata (creation_time), or first-frame PTS, or filename |
| audio | Same |
| lidar | Point cloud frame header, or filename |
| vibration | CSV first column/time column, or filename |

**Storage**: DB, manifest, MLflow all have `observed_at`; MLOps can do cross-modal correlation by time window (e.g. "10:00±5s video+vibration").

#### Resource Locking — v4 Edge

**Scenario**: Video uses GPU, vibration uses CPU/memory; multimodal concurrency can overload Edge box.

**Design**: Add **resource declaration** in `modality_handlers`. Check before starting handler.

| Handler | Resources | Check |
|---------|-----------|-------|
| VideoHandler | gpu | GPU utilization/memory; queue or skip if over threshold |
| LidarHandler | memory | Available memory; point cloud needs reserve |
| VibrationHandler | cpu | Optional: lower freq or queue when CPU high |
| AudioHandler | cpu | Usually light, can run with other CPU types |

**Implementation**: `modality_handlers` register `required_resources: ["gpu"]`; scheduler calls `resource_guard.acquire(resources)` before starting handler, `release` when done. Edge single-node can serialize: only one "heavy" modality at a time.

### Access Control & Multi-Tenant

- [ ] **Model group & accounts**: Each group can only use and hot-update its own model assets
- [ ] **Fuel & data ownership**: Groups can only access/copy fuel for their models (by batch or business line)
- [ ] **Copy & op audit**: Who, when, copied what (batch ID, dir, account) stored and queryable
- [ ] **Goal**: Clear access control, each gets own fuel, each updates own models, copies traceable

### QC Extension

- [ ] LiDAR quality rules (density, range, spatial_consistency), keep "duplicate+quality" two categories clear
- [ ] **Optional**: Sensor fusion, SLAM/localization, 3D detection aligned with mining/autonomy

---

## 🚛 Scenario Extension: Mining Vehicle Key Frame & Material Recognition (Future)

*Discussion notes for future reference.*

**Goal**: Top-down fixed camera, capture frame when "vehicle center crosses frame center" for Lidar volume alignment (yield) and material classification (sand/ore/coal). **Key frame**: Frame with minimum bbox-center-to-frame-center distance in continuous vehicle segment. **bbox**: Math first (background subtract + contour) → initial labeling for YOLO → model outputs bbox for key frame selection.

---

## 🛠️ Tech & Tool Stack

| Area | Current / Planned |
|------|-------------------|
| Programming & data | Python, SQL, data structures, batch processing |
| ML/CV | Rule engine + YOLO (v2), PyTorch/NumPy planned |
| Experiment & delivery | MLflow (v2), version mapping, data loop (v2.5) |
| Ops & deployment | Logging, YAML, .env, Docker (v3), on-edge |
| Collaboration & docs | Git, README/CHANGELOG/Roadmap, email & human review loop |

---

## 📎 Related Docs

| Doc | Purpose |
|-----|---------|
| **docs/v3_dev_plan.md** | V3 dev plan: steps, schedule, acceptance criteria |
| docs/architecture_thinking.md | DI, interfaces, state machine, etc. |
| docs/batch_output_confidence_tiers.md | refinery, inspection naming and output logic |

---

*Doc version: v2026.02 | Version line: v1 → v1.5 → v2 → v2.5 → v2.6 → v2.7 → v2.8 → v2.9 → v3 → v4 | Aligned with industrial/mining AI safety, efficiency & data quality*

**V3 dev plan**: See [docs/v3_dev_plan.md](v3_dev_plan.md) (steps, schedule, acceptance criteria).
