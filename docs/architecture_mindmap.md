# DataFactory 架构思维导图骨架

> 完整复盘：系统骨架一览。Flowchart 版本可导入 [mermaid-to-excalidraw.vercel.app](https://mermaid-to-excalidraw.vercel.app/) 后导出为 `.excalidraw`，在 Excalidraw 中打开编辑。

```mermaid
flowchart TD
    subgraph Root
        DF[DataFactory]
    end

    subgraph CI[1. Core Infrastructure]
        PD[Path Decoupling]
        CM[Configuration Management]
        MOD[Modality Decoupling]
        MOD --> MOD1[video/audio/vibration]
        MOD --> MOD2[modality_handlers]
        SH[Storage Hierarchy]
        PF[Ingest Pre-Filter]
        PF --> PF1[dedup at ingest]
        PF --> PF2[decode check]
        PF --> PF3[quarantine]
        PD --> PD1[Hardware Abstraction]
        PD --> PD2[settings.yaml SSOT]
        PD --> PD3[Env-agnostic pathing]
        CM --> CM1[Dynamic Overrides]
        CM --> CM2[DATAFACTORY_* env]
        CM --> CM3[Validation Layer]
        CM --> CM4[Pre-flight checks]
        SH --> SH1[Raw]
        SH --> SH2[Refinery]
        SH --> SH3[Inspection]
        SH --> SH4[Archive]
    end

    subgraph DE[2. Defensive Engineering]
        PM[Poka-yoke Mechanisms]
        FT[Fault Tolerance]
        SI[System Integrity]
        PM --> PM1[SQL Parameterization]
        PM --> PM2[Path Traversal Guard]
        PM --> PM3[Path.resolve sandboxing]
        FT --> FT1[Backoff Retry]
        FT --> FT2[File I/O retries: move + copy]
        FT --> FT3[DB Exception Shielding]
        FT --> FT4[Graceful handling]
        SI --> SI1[Atomic Operations]
        SI --> SI2[MD5 Fingerprinting]
        SI --> SI3[Deduplication]
    end

    subgraph DRP[3. Data Refinery Pipeline]
        SI26[Smart Ingestion v2.6]
        QC[Funnel QC]
        HITL[Human-in-the-Loop]
        SI26 --> SI26a[Motion Filtering]
        SI26 --> SI26b[I-Frame Sampling]
        SI26 --> SI26c[Cascade Detection]
        QC --> QC1[Dual-Gate Admission]
        QC --> QC2[Vision-Assisted QA]
        QC --> QC3[YOLO metadata]
        HITL --> HITL1[Admission Dashboard]
        HITL --> HITL2[Admission Timeout Guard]
        HITL --> HITL3[No pipeline stalls]
    end

    subgraph MLOps[4. MLOps Ecosystem]
        OBS[Observability]
        CL[Continuous Learning]
        OBS --> OBS1[Structured Logging]
        OBS --> OBS2[Health Check API]
        OBS --> OBS3[Batch Metrics]
        CL --> CL1[Labeling Export]
        CL --> CL2[CVAT / Label Studio]
        CL --> CL3[Consistency Validation]
        CL --> CL4[Pseudo-label vs human]
        CL --> CL5[Version Mapping]
        CL --> CL6[Data-Code-Model lineage]
    end

    DF --> CI
    DF --> DE
    DF --> DRP
    DF --> MLOps
```



---

## 1. Core Infrastructure（骨架/底座）


| 概念                       | 实现                                                                                         |
| ------------------------ | ------------------------------------------------------------------------------------------ |
| **Path Decoupling**      | `config/settings.yaml` paths；`get_batch_paths()`、`get_batch_media_subdirs()`               |
| **Hardware Abstraction** | 路径集中配置；`DATAFACTORY_RAW_VIDEO` 等 env 覆盖                                                    |
| **Modality 解耦**           | `config modality`；`modality_handlers.decode_check` 按 modality 分发；v3 扩展 audio/vibration |
| **Ingest 预检**            | dedup + decode_check（按 modality）；失败项移入 `quarantine/duplicate`、`quarantine/decode_failed` |
| **SSOT**                 | 批次目录名、前缀、后缀均在 settings.yaml                                                                |
| **Validation Layer**     | `validate_config()`：min<max、gate 范围、双门槛一致性                                                 |
| **Storage Hierarchy**    | raw → archive/rejected/redundant；quarantine（预检）；Batch 内 reports/source/refinery/inspection/labeled（标注回传写回） |


---

## 2. Defensive Engineering（防错/加固）


| 概念                         | 实现                                                             |
| -------------------------- | -------------------------------------------------------------- |
| **SQL Parameterization**   | db_tools 使用参数化查询                                               |
| **Path Traversal Guard**   | dashboard `get_thumbnail`：`Path.resolve()` + `relative_to()`   |
| **Backoff Retry**          | `retry_utils.safe_move_with_retry`、`safe_copy_with_retry`；move/copy 失败打 warning、计入 metrics |
| **DB Exception Shielding** | 捕获 `sqlite3.Error`，记录日志，返回 None/False                          |
| **MD5 Fingerprinting**     | fingerprinter；production_history 去重                            |


---

## 3. Data Refinery Pipeline（生产/提纯）


| 概念                          | 实现                                                                   |
| --------------------------- | -------------------------------------------------------------------- |
| **Motion Filtering**        | `motion_filter.py`；`vision.motion_threshold`                         |
| **I-Frame Sampling**        | `frame_io.py`；`vision.use_i_frame_only`                              |
| **Cascade Detection**       | vision_detector 轻量模型初筛                                               |
| **Dual-Gate Admission**     | `dual_gate_high` / `dual_gate_low`；auto-pass / blocked / auto-reject |
| **Vision-Assisted QA**      | YOLO 抽帧推理；工业/智能报告                                                    |
| **Admission Dashboard**     | `dashboard/app.py`；`/api/pending`；approve/reject                     |
| **Admission Timeout Guard** | `mode=terminal` 时 600s 超时；`mode=dashboard` 无超时丢料                     |


---

## 4. MLOps Ecosystem（闭环/观测）


| 概念                         | 实现                                                           |
| -------------------------- | ------------------------------------------------------------ |
| **Structured Logging**     | RotatingFileHandler；`logs/factory_YYYY-MM-DD.log`            |
| **Health Check API**       | `GET /api/health`                                            |
| **Batch Metrics**          | `GET /api/metrics`；`engines/metrics.py`；file_move_errors_total、file_copy_errors_total |
| **Labeling Export**        | `scripts/export_for_labeling.py`；`storage/for_labeling`      |
| **Consistency Validation** | `import_labeled_return.py`；IoU 匹配；一致率门槛；达标后 copy_to_batch_labeled 写回 Batch_xxx/labeled（safe_copy 防静默失败） |
| **Version Mapping**        | `version_info.json`；algorithm_version / vision_model_version |
| **MLflow 存储**            | `tracking_uri` 默认 `sqlite:///db/mlflow.db`，与 factory_admin.db 同目录 |

---

*文档版本：v2.9 | 与 README Design philosophy 对应*