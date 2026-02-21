# 🏭 DataFactory 生产版本日志 (Version Log)

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