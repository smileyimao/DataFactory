# DataFactory 配置参数说明

配置集中在 `config/settings.yaml`，由 `config/config_loader.py` 加载；路径为相对项目根目录，启动时会被解析为绝对路径。敏感信息（如邮箱授权码）放在根目录 `.env`，不写入 YAML。

---

## 1. paths（路径）

| 键 | 说明 | 默认/示例 |
|----|------|-----------|
| `raw_video` | 原材料视频目录，单次/Guard 均从此扫描 | `storage/raw` |
| `data_warehouse` | 合格成品归档目录（按 Batch 建子目录） | `storage/archive` |
| `rejected_material` | 不合格废片归档目录 | `storage/rejected` |
| `redundant_archives` | 重复件归档目录 | `storage/redundant` |
| `reports` | 历史报表存档（每批 HTML/PNG 副本） | `storage/reports` |
| `labeling_export` | 可选：待标注清单导出目录（`scripts/export_for_labeling.py`） | `storage/for_labeling` |
| `golden` | 黄金库：开机自检时真跑 QC 用的参考视频目录；边缘部署可改为挂载点如 `/opt/factory/golden` | `storage/golden` |
| `logs` | 日志目录 | `logs` |
| `db_file` | 生产数据库文件路径 | `db/factory_admin.db` |

说明：启动时 `init_storage_structure()` 会创建 `storage/raw`、`storage/archive`、`storage/rejected`、`storage/redundant`、`storage/test`、`storage/reports`、`storage/for_labeling`、`storage/golden` 和 `db/`，无需手动建目录。

---

## 2. ingest（准入与凑批）

| 键 | 说明 | 默认 |
|----|------|------|
| `batch_wait_seconds` | Guard 模式下，新文件落地后等待多少秒再凑批（期间新文件会重置计时） | `8` |
| `video_extensions` | 视为视频的文件扩展名 | `[".mp4", ".mov", ".avi", ".mkv"]` |
| `file_stable_check_interval` | 文件稳定性检测：轮询间隔（秒） | `1` |
| `file_stable_min_seconds` | 文件大小不变持续多少秒视为稳定 | `2` |

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

命令行 `--gate 90` 可覆盖 `pass_rate_gate`。

---

## 5. review（人工复核）

| 键 | 说明 | 默认 |
|----|------|------|
| `timeout_seconds` | 单条复核等待输入超时（秒），超时按 none 处理 | `600` |
| `valid_inputs` | 合法输入 | `["y", "n", "all", "none"]` |

---

## 6. email_setting（邮件）

用于批次质检报告发送（发件人、收件人、SMTP）。

| 键 | 说明 | 示例 |
|----|------|------|
| `smtp_server` | SMTP 服务器 | `smtp.mail.me.com` |
| `smtp_port` | 端口 | `587` |
| `sender` | 发件人邮箱 | 必填 |
| `receiver` | 收件人邮箱 | 必填 |

密码/授权码不写在 YAML 中，需在 `.env` 中设置 `EMAIL_PASSWORD`（或通过 notifier 的 `password_env_key` 指定其它 key）。

---

## 7. 开机自检与滚动清零（Edge 部署稳定性）

| 键 | 说明 | 默认 |
|----|------|------|
| `startup_self_check` | 启动时是否校验配置与关键目录可写，失败则退出 | `true` |
| `startup_golden_run` | 是否用 `paths.golden` 下视频真跑一遍 QC，失败则退出（边缘/生产建议 `true`） | `false` |
| `rolling_cleanup.logs_retention_days` | 日志保留天数，超期删除（0=不删） | `30` |
| `rolling_cleanup.reports_retention_days` | 报表保留天数，超期删除（0=不删） | `30` |
| `rolling_cleanup.archive_retention_days` | 成品库 Batch 目录保留天数（0=不自动删） | `0` |

全球/边缘部署时可按存储环境覆盖：例如边缘小盘将 `logs_retention_days`、`reports_retention_days` 改为 `7`；黄金库可设 `paths.golden: "/opt/factory/golden"` 指向挂载点；关闭自检可设 `startup_self_check: false`（不推荐）。

---

## 8. 默认配置与无 YAML 时行为

若未找到 `config/settings.yaml`，`config_loader.load_config()` 会使用 `_default_config(base_dir)`，其路径与上述默认值一致（paths 指向 `storage/` 与 `db/`）。因此即使没有 YAML，启动也会使用合理默认值。

---

## 9. 在代码中读取配置

- **路径**：`config_loader.get_paths(cfg)` 得到已解析为绝对路径的 `paths` 字典。
- **质检相关**：`config_loader.get_quality_thresholds(cfg)` 得到 `quality_thresholds` 与 `production_setting` 的合并字典，供质检与报告使用。
