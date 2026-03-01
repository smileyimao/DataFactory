# 🏭 DataFactory 生产版本日志 (Version Log)

## [v3.0] - 2026-02-20
### 📝 版本概览
**数据血缘与 Model Registry**：批次级 Transform Log、标注回写关联、MLflow 血缘参数、`models:/` URI 支持。

#### 数据血缘（Phase 3）
* **batch_lineage**：每批归档后写入 `batch_id`、`batch_base`、`source_dir`、`refinery_dir`、`inspection_dir`、`transform_params`（gate、algorithm_version、vision_model_version）。
* **label_import**：标注回传达标并入训练集后，记录 `import_id`、`batch_ids`、`training_dir`、`consistency_rate`、`merged_count`。
* **scripts/query_lineage.py**：血缘查询 CLI，`--batch`、`--import-id` 或默认列出最近批次。

#### MLflow 血缘（Phase 4）
* **pipeline._maybe_log_mlflow**：新增 `refinery_dir`、`inspection_dir`、`source_archive_dir` 参数，便于 run 追溯数据来源。
* **engines/model_registry.py**：`resolve_model_uri()` 解析 `models:/name/version`，从 MLflow 下载到 `models/registry_cache/` 并返回本地 .pt 路径。
* **vision_detector**：`model_path`、`cascade_light_model_path` 支持 `models:/` URI，自动解析后加载。
* **scripts/register_model.py**：将本地 .pt 注册到 MLflow Model Registry，供 config 使用 `models:/vehicle_detector/1`。

#### 配置
* `vision.model_path` 可填 `models:/vehicle_detector/2` 或本地路径；`cascade_light_model_path` 同理。
* `.gitignore` 新增 `models/registry_cache/`。

#### 修复
* **CVAT 导入失败**：`production_tools` 源头输出帧时对媒体名去空格；`export_for_cvat` 二次兜底；`labeled_return` 支持 sanitized 回传；`scripts/demo_prepare.sh` 预演练验证 zip 可导入。
* **CVAT 伪标签上传**：统一用 CVAT for images 1.1 原生格式。`export_for_cvat.py` 仅生成图片 zip；`export_for_cvat_native.py` 生成标注 zip；删除 LabelMe/COCO/Ultralytics 等格式。

#### 审计与重构（2026-02-20）
* **删除 legacy/**：移除 5 个废弃模块（main_factory、factory_guard、core_engine、db_manager、factory_config.yaml）。
* **删除 6 个死函数**：`init_storage_structure`、`get_paths`、`upload_images`、`list_video_paths`、`metrics.get`、`metrics.reset`。
* **公共函数抽取**：`engines/file_tools.sanitize_filename()` 替换 4 处重复；`config_loader.get_config_and_paths()` 替换 9 个脚本的配置加载。
* **本地 CVAT 对接**：`scripts/cvat_api.py` 封装 create_project、create_task、upload_images_from_zip、upload_annotations；main.py 支持 `--input`、`--auto-cvat`，pipeline 结束后自动创建 Task、上传图片与伪标签、打印报告。
* **新增脚本**：`export_for_cvat`、`export_for_cvat_native`、`cvat_api`、`query_lineage`、`register_model`、`count_vehicles_track`、`test_email`、`cvat_upload_annotations`、`cvat_setup_labels`、`run_demo_a.sh`、`demo_prepare.sh`。
* **修复**：`run_demo_a.sh` 删除无效的 `--format coco` 参数。
* **docs/AUDIT_REPORT.md**：项目全面审计报告（死代码、重复、废弃、配置、脚本清单）。

---

## [v2.10.1] - 2026-02-27
### 📝 版本概览
**混合模式（image + video both）**：raw 目录同时有图片和视频时，自动走 both 通路，两类媒体均被处理，不再忽略其中一类。

#### 混合模式
* **file_tools.detect_content_mode()**：当 raw 同时有图片和视频时，返回 `"both"`；仅一种时按数量多者；空目录默认 video。
* **file_tools.list_media_paths_recursive()**：新增，递归扫描图片+视频，返回合并排序的路径列表。
* **config_loader.get_content_mode()**：支持 `image_mode: "both"` 显式指定；`"auto"` 时 raw 有图+有视频则自动返回 both。
* **core/ingest.py**：mode 为 both 时调用 `list_media_paths_recursive`，图片和视频一并进入 pipeline。
* **modality_handlers**：`decode_check` 在 both 模式下按**文件扩展名**选择 image/video handler（`get_modality_for_path`），每文件独立解码检查。

#### 配置
* `ingest.image_mode`：新增可选值 `"both"`（混合）；`"auto"` 时两者都有自动走 both。
* 详见 **docs/image_mode.md**、**docs/quick_validation_guide.md**。

---

## [v2.10] - 2026-02-26
### 📝 版本概览
**Image 通路与自动模式判定**：支持 YOLOv8 图片数据集全流程，raw 目录按内容自动选择 image/video 通路，无需手动改 config。

#### Image 通路
* **ingest**：`image_mode` 为 `true` 或 `"auto"` 且 raw 以图片为主时，递归扫描 `image_extensions`（.jpg/.jpeg/.png），替代视频扫描。
* **modality_handlers**：`decode_check_image` 用 `cv2.imread` 做可读性检查；`get_modality()` 按 `config_loader.get_content_mode()` 返回 `"image"` 或 `"video"`。
* **qc_engine**：image 时跳过视频专用 QC（帧率、时长、I-frame）；保留 blur、brightness、dedup（MD5）。
* **production_tools**：按扩展名识别图片，用 `cv2.imread` 单帧处理；输出保持原名；存在 YOLO 标签时一并复制到 refinery/inspection。
* **archiver**：移动/复制图片时同步移动对应 `labels/xxx.txt`（YOLO 格式：`.../images/xxx.jpg` ↔ `.../labels/xxx.txt`）。

#### 自动模式判定（image_mode: "auto"）
* **file_tools.detect_content_mode()**：递归扫描 raw 目录，统计图片/视频数量，数量多者决定通路；空目录默认 video。
* **config_loader.get_content_mode()**：统一解析 `image_mode`（true/false/auto），供 ingest、modality_handlers 共用。
* **config 默认**：`ingest.image_mode: "auto"`，`ingest.image_extensions: [".jpg", ".jpeg", ".png"]`。

#### 技术说明
* 详见 **docs/image_mode.md**、**docs/settings_guide.md** ingest 节。

#### 产线优化（IE）
* **YOLO 复用**：QC 阶段 `return_detections=True`，`qc_detections_by_video` 传入 archiver，消除二次推理。
* **qualified 置信度分流**：`archive_produced` 对 qualified 按 `approved_split_confidence_threshold` 分流，高置信 → refinery，低置信/无检测 → inspection。
* **进度可见**：vision_scan tqdm；production_tools 单条整体进度条。
* **raw 递归扫描**：image/video 均递归扫描 raw 及子目录；guard Watchdog `recursive=True`；支持深层嵌套、按文件夹分类的投放方式。
* **docs/optimization_log.md**：产线优化日志，记录瓶颈、根因、方案与设计原则。

---

## [v2.9] - 2026-02-24
### 📝 版本概览
**Modality 解耦（YAGNI）**：流程与信号类型解耦，为 v3 多模态（audio/vibration、predictive maintenance）预留接口。config 切换 modality 即可，未来只需加 handler。

#### 加固与测试（2026-02-20 补充）
* **MLflow 存储**：`tracking_uri` 默认 `sqlite:///db/mlflow.db`，与 factory_admin.db 同目录，便于备份与部署。
* **labeled 子目录**：`batch_subdirs.labeled` 新增；`import_labeled_return` 达标后将人工标注按 batch_id 写回 `archive/Batch_xxx/labeled/`，保持批次血缘。
* **数据一致性防静默失败**：`copy_to_batch_labeled`、`merge_to_training` 使用 `retry_utils.safe_copy_with_retry`；磁盘满/权限不足时重试后打 warning、计入 `file_copy_errors_total`，不静默。
* **单元测试**：db_tools 异常测试用 `sqlite3.OperationalError`；quality_tools、integration、api 在 macOS 上因 cv2/numpy Floating-point exception 自动 skip。
* **requirements-dev.txt**：新增 hypothesis、httpx（FastAPI TestClient）。
* **根目录清理**：删除旧配置产物 `mlflow.db`（根目录）、`mlruns/`、`.hypothesis/`、`.pytest_cache/`；`.gitignore` 补充 `.pytest_cache/`、`.hypothesis/`；`settings.default.yaml` 与当前结构 sync（labeled、quarantine、retry 等），`reset_config.py` 恢复后配置完整。

#### Modality 抽象层
* **config**：`modality: video`（默认）；预留 `audio`、`vibration`。
* **engines/modality_handlers.py**：`decode_check(path, cfg)` 按 modality 分发；video 用 cv2，audio/vibration 占位返回 True。
* **core/ingest.py**：pre_filter 使用 `modality_handlers.decode_check`，不再硬编码 cv2。
* **core/pipeline.py**：入口检查 modality，非 video 时提示「v3 实现」并跳过。
* **预留接口**：sample、quality_check、produce 注释占位，v3 扩展时注册 handler。

#### 扩展方式
* v3 加 audio：实现 `_decode_check_audio`，config `modality: audio`，加 ingest 路径与 QC/Archive handler。
* 无需改 pipeline 主流程。

---

## [v2.8] - 2026-02-20
### 📝 版本概览
**Ingest 预检与流程模块化**：在 Watchdog + 轮询凑批之后、送入 pipeline 之前，增加 dedup + 首帧解码预检。失败项移入 quarantine，流程更清晰、更模块化。

#### Ingest 预检（门卫）
* **dedup_at_ingest**：fingerprint + DB 查重，重复视频移入 `quarantine/duplicate/`，不进入 pipeline。
* **decode_check_at_ingest**：轻量首帧解码（cv2.VideoCapture 读一帧），失败移入 `quarantine/decode_failed/`。
* **pre_filter_enabled**：可配置开关；`ingest.pre_filter_enabled`、`dedup_at_ingest`、`decode_check_at_ingest` 独立控制。
* **core/ingest.py**：新增 `pre_filter(cfg, paths)`，返回通过预检的路径与统计；`_decode_check()`、`_move_to_quarantine()`。
* **core/pipeline.py**：`get_video_paths` 之后调用 `pre_filter`，仅通过项进入 Funnel QC。
* **paths.quarantine**：`storage/quarantine`，支持 env 覆盖；ensure_dirs 含 quarantine。
* **guard**：启动时 `init_storage_from_config` 创建 quarantine 目录。

#### 流程与文档
* 流程命名：QC → Funnel QC，Review → Admission；流程更清晰：发现 → 预检（门卫）→ 合格进厂 → Funnel QC → Admission → Archive。
* **docs/settings_guide.md**：quarantine、pre_filter 配置说明。
* **docs/architecture_mindmap.md**：Ingest Pre-Filter 节点。

---

## [v2.7] - 2026-02-20
### 📝 版本概览
**Edge 部署前最关键一步**：工业级加固（P0/P1/P2/P3）、路径解耦、Batch 目录重命名。为边缘部署提供：重试、DB 容错、健康检查、metrics、配置校验、路径可覆盖，确保产线在无人值守环境下稳定运行。

#### P0 稳定性（poka yoke）
* **文件操作重试**：engines/retry_utils.py，safe_move_with_retry；config retry.max_attempts/backoff_seconds；qc_engine、archiver 使用。
* **数据库错误处理**：db_tools 所有操作捕获 sqlite3.Error，记录日志，init_db/record_* 返回 bool；main/guard 启动时 init_db 失败则 exit(1)。
* **健康检查**：GET /api/health 检查 DB 连通性、关键目录可写、config 校验；异常时 503。
* **路径遍历防护**：dashboard get_thumbnail 用 Path.resolve() 严格校验，拒绝 ..、/、\\。

#### P1 可维护性
* **时区**：core/time_utils.py，config timezone；qc_engine、archiver、db_tools、report_tools、pending_queue、labeled_return 统一使用。
* **视频扩展名**：startup._get_video_extensions(cfg) 从 config 读取。
* **异常日志**：fingerprinter 失败时打 warning，不吞异常。
* **配置校验**：validate_config 校验 min<max、gate∈[0,100]、双门槛一致性。
* **日志轮转**：RotatingFileHandler，config logging.max_bytes/backup_count；main 先 load_config 再 setup_logging(cfg)。

#### P2 可观测性
* **metrics**：engines/metrics.py 简单 counters；retry 失败时 inc(file_move_errors_total)；pipeline 完成时 inc(batch_processed_total)；GET /api/metrics。
* **临时目录**：qc_engine 用 TemporaryDirectory 上下文管理器，异常时自动清理。
* **邮件重试**：notifier 支持 max_retries、retry_delay_seconds，失败时按配置重试。

#### P3 代码规范
* **pyproject.toml**：black + isort + mypy 配置。

#### Path Decoupling 路径解耦
* **config/settings.yaml**：paths.batch_subdirs、batch_prefix、batch_fails_suffix 集中配置；改名只改此处。
* **config_loader**：get_batch_paths()、get_batch_media_subdirs()、get_batch_prefix()、get_pending_queue_path() 等 API。
* **环境变量覆盖**：DATAFACTORY_RAW_VIDEO、DATAFACTORY_DATA_WAREHOUSE 等可覆盖 paths。
* **validate_config()**：启动前配置校验；init_storage_from_config() 按配置创建目录。
* **docs/path_decoupling.md**：路径解耦设计文档。

#### Batch 目录重命名
* **reports**：质量报告、工业报表、智能检测报告、version_info（原 _reports）。
* **source**：本批源视频归档（原 0_Source_Video）。
* **refinery**：高置信燃料，manifest+图+txt 直接反哺模型（原 2_高置信_燃料）。
* **inspection**：待人工，供复核/抽检（原 3_待人工）。
* **labeling_export**：扫描 refinery、inspection、source，兼容旧版目录名。

---

## [v2.6] - 2026-02-20
### 📝 版本概览
**Smart Ingest / 高效筛查**：在 Ingest 前增加四板斧（I-帧、运动唤醒、级联检测），减少无效解码与 YOLO 推理量。主流程 Ingest → QC → Review → Archive 不变，仅优化「解码 + 检测」阶段的算力与带宽消耗。

### 🚀 新增 / 变更

#### 1. I-帧抽取 (engines/frame_io.py)
* **get_i_frame_timestamps()**：用 ffprobe 获取 I-帧时间戳，只读取这些帧，减少解码量。
* **sample_i_frames()**：按 sample_seconds 间隔筛选 I-帧，支持 max_duration_seconds；ffprobe 不可用时回退到按秒抽帧。
* **配置**：`vision.use_i_frame_only=true` 启用；production_tools 与 vision_detector 均支持。

#### 2. 运动唤醒 (engines/motion_filter.py)
* **compute_motion_score()**：帧差 / 光流计算运动量，返回 [0,255] 标量。
* **should_run_detection()**：运动量低于阈值时返回 False，跳过 YOLO。
* **配置**：`vision.motion_threshold`（0=关闭）；在 vision_detector 抽帧循环内调用。

#### 3. 级联检测 (vision_detector)
* **get_cascade_model()**：加载轻量模型，用于初筛；与主模型相同时自动关闭。
* **_cascade_has_detection()**：轻量模型有检测再跑主 YOLO，空画面被过滤。
* **配置**：`vision.cascade_light_model_path`、`vision.cascade_light_conf`。

#### 4. 配置与文档
* **settings.yaml**：vision 段新增 use_i_frame_only、motion_threshold、cascade_light_model_path、cascade_light_conf。
* **docs/Roadmap.md**：四板斧标记为已实现（3/4）；Embedding/Re-ID 待做。
* **docs/smart_slicing.md**：更新四板斧说明。

---

## [v2.5] - 2026-02-23
### 📝 版本概览
**数据闭环与持续学习**：3_待人工精简、待标池自动更新、新旧模型对比、厂长中控台 Web 复核、标注回传与伪标签一致性校验。形成「待标 → 回传 → 校验 → 并入训练」的闭环。

### 🚀 新增 / 变更

#### 1. 3_待人工精简
* **production_setting.human_review_flat=true**：Normal/Warning 合并，只保留 manifest.json + 图片 + txt，便于 for_labeling 直接导入。
* **production_tools**：新增 `use_flat_output` 参数；archiver 对 to_human 传入时启用。
* **labeling_export**：list_batch_media 用 os.walk 支持平铺与 Normal/Warning 两种结构。

#### 2. 待标池自动更新
* **labeling_export.auto_update_after_batch()**：每批归档后自动将本批 3_待人工 追加到 for_labeling，合并 manifest。
* **配置**：`labeling_pool.auto_update_after_batch=true`；pipeline 调用。

#### 3. 新旧模型对比
* **scripts/compare_models.py**：--new、--baseline、--data；在相同数据上跑两模型，比较检测数量、一致率（IoU 匹配），写入 MLflow 与 DB 表 model_comparison。

#### 4. 厂长中控台
* **dashboard/app.py**：FastAPI，/api/pending、单项/批量 approve/reject、/thumbs。
* **core/pending_queue.py**：队列、缩略图、复核决策调用 archiver。
* **review.mode=dashboard**：blocked 入队，无 600s 超时丢料；轮询兜底、产线期间新视频入队后自动再扫。

#### 5. 标注回传与伪标签校验
* **engines/labeled_return.py**：回传接收（目录/压缩包）、伪标签对比（IoU 0.5 贪婪匹配）、一致率门槛报警、达标并入 training。
* **scripts/import_labeled_return.py**：--dir/--zip、--no-merge、--dry-run。
* **配置**：`labeled_return.consistency_threshold`、`alert_via_email`；paths 新增 labeled_return、training。

#### 6. 配置与依赖
* **settings.yaml**：human_review_flat、labeling_pool、labeled_return 段。
* **config_loader**：对上述段做 setdefault。

---

## [v2.0] - 2026-02-20
### 📝 版本概览
在 v1.5 架构之上引入**视觉感知与自动化准入**：YOLO 单例抽帧推理、版本映射、双门槛（自动放行/拦截 + 人工复核中间态）、MLflow 批次级记录、不合格检测可扩展接口。程序与配置保持向后兼容，未开启 vision/mlflow/双门槛时行为与 v1.6 一致。

### 🚀 相对 v1.5 的升级点

#### 1. 计算机视觉质检 (#13 + #14)
* **engines/vision_detector.py**：YOLO 单例加载，从 config `vision` 段读 `model_path`；按 `sample_seconds` 抽帧、`model.predict` 推理，仅返回检测结果，不决策。
* **推理参数全配置化**：conf、iou、classes、device、max_det、imgsz、half、verbose 等全部从 `config/settings.yaml` 的 `vision` 段读取，无硬编码；默认值在 config_loader 中填入。
* **core/qc_engine**：规则质检后调用 `vision_detector.run_vision_scan(cfg, 归档路径列表)`，视觉结果汇总日志；传入路径为归档后的 `archive_path`，保证文件可读。
* **Edge 预留**：vision 段预留 `edge_lightweight` 等，便于 v3 配置下发与轻量化。

#### 2. 版本映射 (#15)
* **config**：新增 `version_mapping.algorithm_version`、`vision_model_version`；未配置时由 config_loader 填默认值。
* **运行时**：每批 QC 结束后写入 `Batch_xxx/1_QC/version_info.json`，并写入 `path_info["version_mapping"]`；日志输出「版本映射: algorithm_version=... vision_model_version=...」。
* **vision_detector.get_vision_model_version(cfg)**：返回当前生效的视觉模型版本（已加载路径或 config 值），供版本映射使用。

#### 3. 双门槛自适应准入 (#16)
* **config**：`production_setting` 新增 `dual_gate_high`、`dual_gate_low`（均为可选，默认 null 表示单门槛）。
* **逻辑**：若两者均配置则启用双门槛：score ≥ high → 自动放行（qualified）；score < low → 自动拦截（auto_reject，直接进废片）；low ≤ score < high 或重复 → 人工复核（blocked）。
* **qc_engine**：返回值由 4 个改为 5 个：`(qc_archive, qualified, blocked, auto_reject, path_info)`；pipeline 将 `auto_reject` 与 review 产生的 to_reject 合并后归档。
* **startup / smoke_test**：已适配 run_qc 五元组返回值。

#### 4. MLflow 批次级记录 (#17)
* **config**：新增 `mlflow` 段：`enabled`、`experiment_name`、`tracking_uri`；默认关闭，不影响现有流程。
* **core/pipeline._maybe_log_mlflow()**：批次结束后若 `mlflow.enabled` 为 true，则记录当前 run 的 params（batch_id、algorithm_version、vision_model_version、gate）与 metrics（file_count、size_gb、elapsed_sec、throughput_gb_per_h、各阶段耗时）；记录失败仅打 warning，不中断流水线。
* **requirements.txt**：新增 `mlflow>=2.0`（v2.0 新增依赖）。

#### 5. 不合格检测可扩展 (#19)
* **engines/quality_tools**：新增 `_EXTRA_CHECK_REGISTRY` 与 `register_extra_check(fn)`；`decide_env()` 在现有规则判断后依次调用注册的 `fn(raw, cfg)`，若返回非空字符串则覆盖 env。便于后续接入黑帧、分辨率异常、YOLO 输出等，由 qc_engine 统一调度。

#### 6. 配置与依赖
* **settings.yaml**：新增/扩展 `vision`（enabled、model_path、sample_seconds、推理参数）、`version_mapping`、`mlflow`、`production_setting.dual_gate_high/dual_gate_low`。
* **config_loader**：对上述段做 setdefault，保证缺省时也有合理默认；`_default_config()` 中同步默认值。
* **依赖**：ultralytics>=8.0（YOLO）、mlflow>=2.0（可选，仅 mlflow.enabled 时生效）。

### 📌 未在本版完成的 v2 项
* **#18 模型注册与复现**：model registry 与训练/评估 pipeline 打通，留待 v2.5 或后续。

---

## [v1.6] - 2026-02-20
### 📝 版本概览
地基加固：存储与 DB 归拢到 `storage/`、`db/`，报表持久化到 `storage/reports/`，为 v2.x 预埋 sync_id 与 Conflict 扩展点，启动时自建目录并初始化 DB。

### 🚀 新增 / 变更

#### 1. 存储与运维 (storage/ & db/)
* **storage/**：raw、archive、rejected、redundant、test、reports；配置 paths 的 value 指向上述子目录（key 仍为 raw_video、data_warehouse 等）。
* **db/**：数据库路径改为 `db/factory_admin.db`；若根目录曾有 `factory_admin.db`，已迁到 `db/`。
* **报表持久化**：每批 QC 生成的 HTML 报告和图表额外写入 `storage/reports/`（`{batch_id}_quality_report.html`、`{batch_id}_chart.png`）。
* **文档**：Roadmap.md 已移至 `docs/`。

#### 2. 数据协议预埋 (v2.x)
* **db_tools**：`production_history` 表新增 `sync_id VARCHAR(64) NULL`；`record_production` 增加可选参数 `sync_id`，用于后续对齐外部传感器时间戳。
* **quality_tools**：在 `decide_env` 里预留 Conflict 标签的注释/扩展点，为人机冲突检测做准备。

#### 3. 健壮性
* **config/settings.yaml**：paths 全部指向 `storage/` 与 `db/`（key 不变）。
* **config/config_loader.py**：新增 `init_storage_structure()`，启动时创建 `storage/*` 和 `db/`；默认路径已同步为新结构。
* **main.py**：启动时调用 `init_storage_structure()`，若有 db_file 则调用 `db_tools.init_db(db_path)`，保证表与 sync_id 列存在。
* **requirements.txt**：根目录已添加（PyYAML、opencv-python-headless、tqdm、pandas、matplotlib、python-dotenv、watchdog、inputimeout）。

#### 4. 门户与流程
* **README.md**：项目定位、架构索引、快速启动、v1.x/v2.x 说明，指向 docs/ 与 CHANGELOG。
* **流程闭环**：`python main.py` → set_base_dir → init_storage_structure → load_config → init_db → pipeline.run_smart_factory 或 guard.run_guard；从 storage/raw 取视频 → QC（报告写 Batch 下并复制到 storage/reports/）→ 复核 → 归档到 storage/archive | rejected | redundant，并写 DB（可传 sync_id）。

### 📌 备注
* 根目录可能仍存在旧文件夹（raw_video、data_warehouse、rejected_material、redundant_archives、test_videos），内容尚未迁入 storage/ 对应子目录；可按需做一次迁移并清理旧目录。

#### 5. 2.0 前可选收尾（已完成）
* **基础指标完整化**：各阶段耗时（Ingest/QC/Review/Archive）、吞吐量（GB/h、文件/h）在批次结束时输出并写入 DB 表 `batch_metrics`；`db_tools.init_db` 增加 `batch_metrics` 表创建，`db_tools.record_batch_metrics` 写入每批指标。
* **数据清洗与标注管道扩展**：`engines/labeling_export.py` 扫描 `storage/archive` 生成待标注清单；`scripts/export_for_labeling.py` 导出至 `storage/for_labeling/manifest_for_labeling.json`，供 Label Studio / CVAT 等导入；配置增加可选 `paths.labeling_export`，启动时创建 `storage/for_labeling`。

---

## [v1.5] - 2026-02-20
### 📝 版本概览
架构重构：按「流程 + 工具 + 决策 + 配置」拆分，新增 `config/`、`core/`、`engines/`，入口统一为 `main.py`。行为与 v1.3 一致，便于后续 v2 扩展。

### 🚀 新增 / 变更

#### 1. 配置集中化 (config/)
* **config/settings.yaml**：路径、ingest（batch_wait_seconds、video_extensions）、quality_thresholds、production_setting、review、email_setting。
* **config/config_loader.py**：统一加载，路径解析为绝对路径；`get_quality_thresholds()` 供质检使用。

#### 2. 工具类 (engines/)
* **quality_tools**：`analyze_frame()` 只返回数值；`decide_env()` 为决策层，根据配置返回 Normal/Too Dark/Blurry 等。
* **fingerprinter**：MD5 计算。
* **db_tools**：init_db、get_reproduce_info、record_production（接受 db_path）。
* **notifier**：send_mail(email_cfg, subject, body, report_path)。
* **file_tools**：wait_file_stable、list_video_paths。
* **report_tools**：generate_json_manifest、generate_html_report。
* **production_tools**：run_production（视频试制/量产，调用 quality_tools + report_tools）。

#### 3. 流程与决策 (core/)
* **ingest**：get_video_paths(cfg, video_paths=None)。
* **qc_engine**：run_qc(cfg, video_paths) → 指纹、试制、源归档、建 qc_archive、发邮件；返回 qualified/blocked/path_info。
* **reviewer**：review_blocked(blocked, gate, timeout_seconds) → to_produce, to_reject。
* **archiver**：archive_rejected、archive_produced。
* **pipeline**：run_smart_factory(video_paths=None, limit_val=None, gate_val=None)。
* **guard**：run_guard() — 开机扫描 + watchdog 凑批，调用 pipeline。

#### 4. 入口
* **main.py**：`python main.py` 单次运行；`python main.py --guard` 监控模式；`--limit` / `--gate` 覆盖配置。
* 原 `main_factory.py`、`factory_guard.py` 保留，推荐使用 `main.py`。

#### 5. 基础指标
* 批次结束输出：处理文件数、总大小 (GB)、耗时 (秒)；日志记录批次摘要。

---

## [v1.3] - 2026-02-20
### 📝 版本概览
本版本完成**集中质检复核**与**批处理审批**逻辑重构：先整批检测（质量+重复），再统一发一封汇总邮件，最后逐项交互复核 (y/n/all/none)。同时引入专业 Logging、多伦多时区、废片/冗余分目录与路径加固。

---

### 🚀 新增特性 (Features)

#### 1. 📋 集中质检复核模式 (Batch QC & Review)
* **批处理流**：工厂接收一批物料后，连续完成该 Batch 内所有视频的检测（质量 + 重复），不中断、不按单文件弹窗。
* **质检档案**：每文件记录文件名、指纹、得分、是否达标、是否重复（及曾于哪批、时间），仅作内存清单与邮件/复核用。
* **一封汇总邮件**：整批检测完成后只发一封【批次质检报告】待处理物料清单 - Batch:[ID]，正文列表展示：合格 / 不合格（得分/准入）/ 重复（曾于批次）。
* **Poka-Yoke 交互**：仅对「被拦」项（不合格或重复）在控制台逐项询问；支持 y/n/all/none，无效输入循环重问，600 秒超时自动执行 none 并记 Timeout Emergency Stop 日志。

#### 2. 📂 废片与冗余分目录
* **废片**：不合格且厂长选择丢弃 → `rejected_material/Batch_[ID]_Fails/`，重命名为 `原名_得分pts.后缀`。
* **冗余**：重复且厂长选择丢弃 → `redundant_archives/`（保持原名）。合格且不重复自动放行量产。

#### 3. 📝 专业 Logging 系统
* **日志目录**：项目根目录下自动创建 `logs/`，按日写入 `logs/factory_[日期].log`（多伦多日期）。
* **格式**：`[时间] [级别] [模块] - 消息内容`，时间为 America/Toronto。
* **关键记录点**：指纹采集、数据库查重命中、质量得分、厂长决策指令 (y/n/all/none)、文件移动路径 (Moving [File] to [Target] due to [Reason])、开机自检、超时熔断。

#### 4. 🕐 时区与路径
* **多伦多时区**：全局时间戳统一为 America/Toronto（batch_id、邮件、日志、DB 记录）。
* **路径加固**：开机扫描与实时监控传入工厂的均为 `os.path.abspath`；工厂仅处理传入列表，不扫描 raw_video 其他文件。

#### 5. 🧹 Guard 批处理触发
* **凑批**：新文件落地 → 等待该文件写入稳定 → 再等 8 秒（期间若有新文件则重置）→ 将当前 raw_video 下全部视频作为一批送入工厂。
* **开机大扫除**：startup_scan 将存量视频作为一批送入工厂，逻辑与上述一致；不再按单文件发重复邮件或单文件询问。

---

### 🔧 技术参数
* **批等待**: 8s (BATCH_WAIT_SECONDS)
* **复核超时**: 600s，默认 none
* **日志**: INFO+ → logs/factory_YYYY-MM-DD.log

---

## [v1.2] - 2026-02-19
### 📝 版本概览
本版本正式引入了**数字化指纹存储**与**人工决策回路**，标志着产线具备了永久记忆与智能防御能力，彻底解决了重复生产导致的资源浪费问题。

---

### 🚀 新增特性 (Features)

#### 1. 🧬 数字指纹识别 (Digital Fingerprinting)
* **核心实现**：集成 `hashlib` 模块，保安在物料进场时自动计算 **MD5 唯一指纹**。
* **算法优化**：采用“头尾采样法”处理超大视频文件，在保证指纹唯一性的同时，实现秒级扫描，确保产线感应零延迟。

#### 2. 🏛️ 永久档案馆 (SQLite Database Manager)
* **数据持久化**：引入 SQLite 数据库 (`factory_admin.db`)，将生产记录从不稳定的内存提升至**工业级硬盘存储**。
* **防重复机制**：系统自动比对新进物料指纹。若检测到历史状态为 `SUCCESS`，将立即触发拦截告警，防止无效增量。

#### 3. ⚖️ 智能拦截与人工放行 (Human-in-the-Loop)
* **逻辑分级**：系统现可精准区分“质量不达标”与“历史重复物料”两种预警类型。
* **决策引擎**：集成 `inputimeout` 模块，为厂长提供 **10 分钟**的最高指挥窗口。
* **自动熔断**：若超时未响应，系统将执行安全熔断（默认放弃），保护产线在无人值守时的绝对安全。

#### 4. 📦 闭环归档系统 (Automated Archiving)
* **物理溯源**：在 Batch 目录下新增 `0_Source_Video` 文件夹，实现“试产图、量产图、原始视频”的**三位一体**物理存储。
* **稳定性增强**：重构了保安的动态稳定性检查逻辑，彻底解决大文件写入过程中因文件句柄未释放导致的冲突报错。

---

### 🔧 技术参数
* **存储后端**: SQLite 3
* **哈希算法**: MD5 (Buffering Read)
* **决策超时**: 600s