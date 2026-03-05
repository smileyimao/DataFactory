# DataFactory 配置参数说明

配置集中在 `config/settings.yaml`，由 `config/config_loader.py` 加载；路径为相对项目根目录，启动时会被解析为绝对路径。敏感信息（如邮箱授权码）放在根目录 `.env`，不写入 YAML。

---

## 0. modality（v2.9 多模态解耦）

| 键 | 说明 | 默认 |
|----|------|------|
| `modality` | 信号类型：`video`、`image`（v2.10）、`audio`、`vibration`（v3 扩展） | `video` |

流程与信号类型解耦。切换 modality 时，Ingest decode_check、Funnel QC、Archive 按 `engines/modality_handlers` 分发。

**v2.10 image 通路**：`ingest.image_mode: "auto"` 时根据 raw 目录内容自动判定 image/video/both；`true` 强制图片、`false` 强制视频、`"both"` 混合（v2.10.1）。详见 **docs/image_mode.md**。

**v3 演进**：将引入 `modality_filter`（按文件自动识别后过滤）；旧 `modality: "video"` 等价 `modality_filter: ["video"]`，零改动迁移。详见 **docs/Roadmap.md** Auto-modality Routing。

---

## 1. paths（路径）

| 键 | 说明 | 默认/示例 |
|----|------|-----------|
| `raw_video` | 原材料目录，单次/Guard 均从此**递归**扫描（支持子目录、深层嵌套） | `storage/raw` |
| `test_source` | 测试源目录：`main.py --test` 从此复制到 raw，pipeline 不改动此目录 | `storage/test/original` |
| `data_warehouse` | 合格成品归档目录（按 Batch 建子目录） | `storage/archive` |
| `rejected_material` | 不合格废片归档目录 | `storage/rejected` |
| `redundant_archives` | 重复件归档目录 | `storage/redundant` |
| `reports` | 历史报表存档（每批 HTML/PNG 副本） | `storage/reports` |
| `labeling_export` | 可选：待标注清单导出目录（`scripts/export_for_labeling.py`） | `storage/for_labeling` |
| `labeled_return` | 标注回传落盘目录（`scripts/import_labeled_return.py`） | `storage/labeled_return` |
| `training` | 达标数据并入的训练集根目录 | `storage/training` |
| `dashboard_port` | 厂长中控台端口（`python -m dashboard.app`） | `8765` |
| `golden` | 黄金库：开机自检时真跑 QC 用的参考视频目录；边缘部署可改为挂载点如 `/opt/factory/golden` | `storage/golden` |
| `logs` | 日志目录 | `logs` |
| `db_file` | 生产数据库文件路径 | `db/factory_admin.db` |
| `batch_prefix` | 批次目录前缀 | `Batch_` |
| `batch_fails_suffix` | 废片目录后缀 | `_Fails` |
| `batch_subdirs` | 批次内子目录名（reports/source/refinery/inspection/labeled） | 见 path_decoupling.md |
| `pending_review` | 待复核队列目录（中控台） | `storage/pending_review` |
| `quarantine` | Ingest 预检：重复/解码失败视频移入此目录 | `storage/quarantine` |

**Path decoupling**：批次目录名、前缀、后缀均在 paths 配置，改名只改此处。支持 `DATAFACTORY_RAW_VIDEO` 等环境变量覆盖。详见 **docs/path_decoupling.md**。

说明：启动时 `init_storage_from_config(cfg)` 会根据 `paths.ensure_dirs` 创建目录。

---

## 2. ingest（准入与凑批）

| 键 | 说明 | 默认 |
|----|------|------|
| `batch_wait_seconds` | Guard 模式下，新文件落地后等待多少秒再凑批（期间新文件会重置计时） | `8` |
| `poll_interval_seconds` | 轮询兜底间隔（秒）：定期扫 raw 目录，Watchdog 漏检时仍能发现；`0` 表示不轮询 | `30` |
| `image_mode` | 内容通路：`"auto"` 自动判定（有图+有视频→both），`true` 强制图片，`false` 强制视频，`"both"` 混合 | `"auto"` |
| `image_extensions` | 视为图片的文件扩展名（image 通路时递归扫描） | `[".jpg", ".jpeg", ".png"]` |
| `video_extensions` | 视为视频的文件扩展名 | `[".mp4", ".mov", ".avi", ".mkv"]` |
| `file_stable_check_interval` | 文件稳定性检测：轮询间隔（秒） | `1` |
| `file_stable_min_seconds` | 文件大小不变持续多少秒视为稳定 | `2` |
| `pre_filter_enabled` | Ingest 预检：在送入 pipeline 前做 dedup + 首帧解码，失败项移入 quarantine | `true` |
| `dedup_at_ingest` | 预检时查重（fingerprint + DB），重复移入 quarantine/duplicate | `true` |
| `decode_check_at_ingest` | 预检时首帧解码检查，失败移入 quarantine/decode_failed | `true` |

**Guard 巡逻逻辑**（详见下方「Guard 模式巡逻逻辑」）：Watchdog 事件 + 轮询兜底双通道；产线加工期间新视频会登记，本批结束后自动再扫。

---

## 3. quality_thresholds（质检阈值）

用于 `engines/quality_tools` 与决策层判断环境标签（Normal / Too Dark / Blurry 等）。

| 键 | 说明 | 默认 |
|----|------|------|
| `min_brightness` | 亮度下限，低于则 Too Dark | `55.0` |
| `max_brightness` | 亮度上限，高于则 Too Bright | `225.0` |
| `min_blur_score` | 模糊分数下限，低于则 Blurry | `20.0` |
| `min_contrast` | 对比度下限 | `15.0` |
| `max_contrast` | 对比度上限 | `100.0` |
| `max_jitter` | 抖动上限，超过则 Jitter | `35.0` |

---

## 4. production_setting（质检与准入）

| 键 | 说明 | 默认 |
|----|------|------|
| `qc_sample_seconds` | 每视频抽检秒数，用于质量判定（重复+不合格检测） | `10` |
| `pass_rate_gate` | 准入通过率门槛（%），用于整批是否达标 | `85.0` |
| `save_normal` | 是否保存 Normal 帧样本 | `true` |
| `save_warning` | 是否保存 Warning 帧样本 | `true` |
| `save_only_screened` | 为 true 时只落盘「质量异常(Warning) 或 该帧有 YOLO 检测」的帧，减少全量切片 | `false` |
| `human_review_flat` | 为 true 时 inspection 精简：Normal/Warning 合并，只保留 manifest+图+txt 便于 for_labeling 导入 | `true` |
| `approved_split_confidence_threshold` | 放行项按 YOLO 置信度分流：max_conf≥此值→refinery，否则→inspection；vision 未开启时全部→refinery | `0.6` |

详见 **docs/smart_slicing.md**（YOLO 筛查与只落盘关键帧）。

**四板斧（vision 段）**：`use_i_frame_only` 只解 I-帧；`motion_threshold` 运动唤醒（0=关闭）；`cascade_light_model_path` 级联轻量模型；`cascade_light_conf` 级联置信度。详见 **docs/Roadmap.md** 高效筛查技术线。

**v3.0 Model Registry**：`vision.model_path`、`cascade_light_model_path` 支持 `models:/name/version`（MLflow Model Registry URI）；自动解析并下载到 `models/registry_cache/`。注册本地 .pt：`python scripts/mlflow/register_model.py path/to/model.pt --name vehicle_detector`。

命令行 `--gate 90` 可覆盖 `pass_rate_gate`。

---

## 5. review（人工复核）

| 键 | 说明 | 默认 |
|----|------|------|
| `mode` | `terminal`=终端逐项 y/n；`dashboard`=入队由厂长中控台 Web 复核（无超时丢料） | `terminal` |
| `timeout_seconds` | 单条复核等待输入超时（秒），仅 `mode=terminal` 时生效 | `600` |
| `valid_inputs` | 合法输入 | `["y", "n", "all", "none"]` |

**厂长中控台**：`review.mode=dashboard` 时，blocked 项入队 `storage/pending_review/`，厂长打开 `python -m dashboard.app` 即可 Web 复核。详见 `docs/dashboard_design.md`。

---

## 6. email_setting（邮件）

用于批次质检报告发送（发件人、收件人、SMTP）。

| 键 | 说明 | 示例 |
|----|------|------|
| `smtp_server` | SMTP 服务器 | `smtp.mail.me.com` |
| `smtp_port` | 端口 | `587` |
| `sender` | 发件人邮箱 | 必填 |
| `receiver` | 收件人邮箱 | 必填 |
| `max_retries` | P2 邮件发送失败重试次数 | `3` |
| `retry_delay_seconds` | 重试间隔（秒） | `5` |

密码/授权码不写在 YAML 中，需在 `.env` 中设置 `EMAIL_PASSWORD`（或通过 notifier 的 `password_env_key` 指定其它 key）。

---

## 7. labeling_pool（待标池自动更新）

| 键 | 说明 | 默认 |
|----|------|------|
| `auto_update_after_batch` | 每批归档后是否自动将 inspection 追加到 for_labeling | `true` |

---

## 8. labeled_return（标注回传与伪标签一致性）

| 键 | 说明 | 默认 |
|----|------|------|
| `consistency_threshold` | 一致率低于此值报警，要求差异部分复核 | `0.95` |
| `alert_via_email` | 是否发邮件报警（使用 `email_setting`） | `true` |

用于 `scripts/import_labeled_return.py`：回传与伪标签对比后，低于门槛则发邮件，达标则并入 `paths.training`，并按 batch_id 写回 `archive/Batch_xxx/labeled/`（使用 `retry_utils.safe_copy_with_retry` 防静默失败）。

**MLflow**（`config mlflow`）：`tracking_uri` 默认 `null` 时自动设为 `sqlite:///db/mlflow.db`，与 factory_admin.db 同目录；`enabled` 控制是否记录批次实验。**v3.0 血缘**：run params 含 refinery_dir、inspection_dir、source_archive_dir，便于追溯数据来源。

**v3.0 数据血缘**：`paths.db_file` 指向的 DB 含 `batch_lineage`、`label_import` 表；pipeline 归档后自动写入；`python scripts/query_lineage.py` 查询。

---

## 9. 工业级配置（timezone、logging、retry）

| 键 | 说明 | 默认 |
|----|------|------|
| `timezone` | 日志、邮件、batch_id 时区 | `America/Toronto` |
| `logging.max_bytes` | 单日志文件最大字节，超则轮转 | `10485760`（10MB） |
| `logging.backup_count` | 轮转后保留历史文件数 | `5` |
| `retry.max_attempts` | 文件移动/拷贝失败重试次数（move、copy_to_batch_labeled、merge_to_training） | `3` |
| `retry.backoff_seconds` | 重试间隔基数（秒） | `1.0` |

---

## 10. 开机自检与滚动清零（Edge 部署稳定性）

| 键 | 说明 | 默认 |
|----|------|------|
| `startup_self_check` | 启动时是否校验配置与关键目录可写，失败则退出 | `true` |
| `startup_golden_run` | 是否用 `paths.golden` 下视频真跑一遍 QC，失败则退出（边缘/生产建议 `true`） | `false` |
| `rolling_cleanup.logs_retention_days` | 日志保留天数，超期删除（0=不删） | `30` |
| `rolling_cleanup.reports_retention_days` | 报表保留天数，超期删除（0=不删） | `30` |
| `rolling_cleanup.archive_retention_days` | 成品库 Batch 目录保留天数（0=不自动删） | `0` |

全球/边缘部署时可按存储环境覆盖：例如边缘小盘将 `logs_retention_days`、`reports_retention_days` 改为 `7`；黄金库可设 `paths.golden: "/opt/factory/golden"` 指向挂载点；关闭自检可设 `startup_self_check: false`（不推荐）。

---

## 11. 默认配置与无 YAML 时行为

若未找到 `config/settings.yaml`，`config_loader.load_config()` 会使用 `_default_config(base_dir)`，其路径与上述默认值一致（paths 指向 `storage/` 与 `db/`）。因此即使没有 YAML，启动也会使用合理默认值。

---

## 12. 在代码中读取配置

- **路径**：`config_loader.get_paths(cfg)` 得到已解析为绝对路径的 `paths` 字典。
- **质检相关**：`config_loader.get_quality_thresholds(cfg)` 得到 `quality_thresholds` 与 `production_setting` 的合并字典，供质检与报告使用。
- **批次路径**：`config_loader.get_batch_paths(cfg, batch_base)` 得到 qc_dir、source_archive_dir、fuel_dir、human_dir 等。
- **配置校验**：`config_loader.validate_config(cfg)` 返回错误列表，空表示通过。
