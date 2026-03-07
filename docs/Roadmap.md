# 🗺️ DataFactory — MLOps Evolution Roadmap (v2026.03)

> **定位**：端到端数据采集 & 质检 → 录入决策 → 可追溯归档的 Pipeline。可直接复用于视频 QC、安全巡检、矿山/工业场景感知数据精炼，对齐 AI 驱动的安全、效率与资产利用率。

---

## 💡 Vision

人脑擅长多模态处理——触觉、视觉、听觉——但前提是**正确的数据**持续稳定地流入。我们的工作是同一件事：把高质量数据（质检通过、去重、过滤）持续喂给"大脑"，驱动模型迭代。

边缘计算像**眼睛的视网膜**：在本地做重度预处理（亮度自适应、边缘增强、运动检测），再把结构化信号送往大脑，而不是原始像素。Pipeline 中的边缘节点（现场 QC、黄金测试自检、摘要上传中台）扮演同样角色：确保到达"大脑"的是干净、可用、稳定的数据。

**行业视角**：LLM 快速扩展因为语言数据天然"已标注"。机器人与自动驾驶不同：必须在更多模态下大量投入采集、清洗、标注。真正瓶颈是**数据质量与供给**。这条 Pipeline 的使命就是解决这个问题。

---

## 📐 系统架构

```
┌──────────────────────────────────────────────────────────┐
│  Ingest                                                   │
│  raw_video/ [done]   raw_lidar/ [v4]                     │
│  Auto-modality: image/video/both [v2.10 done]            │
│  audio/lidar/vibration [v3 TODO]                         │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Funnel QC                                               │
│  (1) 指纹去重 [done]  MD5 → DB → 命中归入 redundant      │
│  (1a) Ingest 预检 [v2.8]  dedup + 首帧解码 → quarantine  │
│  (2) 质量检测 [done]  blur/brightness/jitter + 可扩展     │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Admission [done]                                        │
│  自动放行 + HITL；邮件摘要 → Terminal y/n 或 Dashboard   │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Archive [done]                                          │
│  Batch_xxx/source  源视频                                │
│  Batch_xxx/refinery  高置信（含伪标签 .txt）             │
│  Batch_xxx/inspection  低置信（待人工标注）              │
│  Batch_xxx/reports  质检报告                             │
│  rejected_material/  废片   redundant_archives/  重复    │
└──────────────────────────────────────────────────────────┘
```

**Edge (v4)**：现场跑全流程，仅上传摘要到中台；特征向量 + 元数据上传，关键帧本地存储按需回传；边缘自动清理重复与损坏数据。

---

## 🧭 架构原则

**统一架构**：Flow（Ingest → Funnel QC → Admission → Archive）+ 工具（engines/）+ 决策（core/）+ 配置（config/）。工具只返回值，决策层读 config 判断。

---

## 📋 版本线

| 版本 | 状态 | 核心内容 |
|------|------|---------|
| **v1.x** | ✅ 完成 | 流程跑通，HITL，可追溯，工业日志，物理归档 |
| **v1.5** | ✅ 完成 | 架构重构：config + engines + core，无新业务 |
| **v2.x** | ✅ 完成 | YOLO、版本映射、双门槛、MLflow、置信度分流、伪标签、可扩展 QC |
| **v2.5** | ✅ 完成 | 置信度分流、Dashboard、inspection 打平、待标池自动更新、模型对比 |
| **v2.6** | ✅ 完成 | 高效筛选：I-frame、运动唤醒、级联检测 |
| **v2.7** | ✅ 完成 | 工业加固：P0/P1/P2/P3、Path decoupling、批次重命名 |
| **v2.8** | ✅ 完成 | Ingest 预检：dedup + 首帧解码，失败进 quarantine |
| **v2.9** | ✅ 完成 | 模态解耦；MLflow→db/mlflow.db；pytest 套件；根目录清理 |
| **v2.10** | ✅ 完成 | 图片通路；Auto-modality；raw 递归扫描；qualified 置信度分流；YOLO 复用 |
| **v2.10.1** | ✅ 完成 | 混合模式 both：图片+视频同时处理；按扩展名 per-file decode_check |
| **v2.11** | 🔶 设计完成 | 主动学习标注优先级（manifest max_confidence/qc_env 待实现） |
| **v3.0** | ✅ 完成 | 数据血缘（batch_lineage、label_import）；MLflow 血缘；Model Registry |
| **v3.1** | ✅ 完成 | 本地 CVAT 闭环；YOLO 训练全链路；MLflow 注册；model_train 血缘 |
| **v3.2** | ✅ 完成 | **PostgreSQL 多人协作 DB**；docker-compose 一键启动；SQLite 完全移除（仅保留 --test 临时隔离）|
| **v3.3** | ✅ 完成 | 帧级 refinery_min_confidence 绝对下限；视频级三档分流（hit_rate + mean_conf → high/standard/low）|
| **v3.4** | ✅ 完成 | 标注池分层策略：inspection 全量 + refinery 视频分层抽样（refinery_sample_rate）；抽检 IoU 低于门槛自动发邮件 + 阈值调整建议 |
| **v3.5** | ✅ 完成 | 可观测性双看板：SENTINEL-1 帧级遥测（port 8766）+ HQ Global Command Center（port 8767）|
| **v3.6** | ✅ 完成 | HQ 全屏适配 + 白底修复 + 实时天气（Open-Meteo）+ DataFactory 品牌徽标；SENTINEL-1 同步全屏 |
| **v3.7** | ✅ 完成 | Site Status 实时本地时间（pytz）+ OpenWeatherMap 真实天气（API Key）；Flask 端点 `/api/sites/time` `/api/sites/weather`；`engines/site_info.py` 10 分钟缓存 |
| **v3.9** | ✅ 完成 | CLIP/SAM 基础模型集成（opt-in，缺包优雅降级）：语义去重、FPS 多样性采样、场景自适应阈值、SAM polygon 预标注；硬件自动检测（`system_probe`）；功能使用追踪（`usage_tracker`）；`tools.py` 运维 CLI |
| **P0 合规** | ✅ 完成 | 原子写全覆盖（含 qc_engine manifest×2、annotation_upload .poly.json、sentinel CSV）；生产 pipeline 去 `print()` 改 logger（archiver×3、vision_detector×1、notifier×1）；manifest schema 校验（必需字段 file/score）；docker-compose 密码不硬编码；`console=True` 终端实时日志 |
| **v3.x** | 🔶 进行中 | Auto-modality 扩展（audio/lidar/vibration）；v2.11 manifest 字段实现 |
| **v4.x** | ⬜ 待做 | 多模态、FFT、Edge 部署、多节点、访问控制、HQ 真实数据接入 |

---

## 🚗 角色与协作边界

我们造**车**；模型团队造**引擎**。我们负责 Pipeline（Ingest → Funnel QC → Admission → Archive）、配置、部署、可观测性；他们负责模型训练与发布。接口约定：`run_vision_scan(cfg, video_paths)`；模型团队提供 `.pt` 或实现该接口。Edge 部署时同一套 Pipeline + 同一份 config，责任清晰。

---

## 🔄 CI/CD & 可部署性

| 维度 | 当前状态 | 备注 |
|------|---------|------|
| 配置与代码分离 | settings.yaml + .env | 切环境改 config，不改代码 |
| 单一入口 | main.py（单次 / --guard） | 易测试易部署 |
| 启动自检 | startup_self_check | 路径与可写性校验 |
| 黄金测试（可选） | startup_golden_run | 真实 QC 冒烟 |
| 冒烟 / 全链路测试 | `pytest tests/ -m slow`, `tools.py --test` | QC 冒烟、全流程、Guard 模式 |
| 单元 / 集成测试 | `pytest tests/ -v -m "not slow"` | unit/integration/api 层 |
| 环境重置 | scripts/reset_factory.py, reset_config.py | dry-run / for-test / db |
| 版本可追溯 | version_mapping, version_info.json, path_info | 每批次规则/模型版本可审计 |
| **数据库** | **PostgreSQL（docker compose up -d）** | **DATABASE_URL 必须设置，未设置报错退出** |
| **TODO** | CI 自动跑 pytest, main.py --test | 设计支持，pipeline 待建 |

---

## 📈 Scale & 多节点（设计就绪，v4 实现）

**定位**：系统是公司的"感官"——边缘 Ingest+QC，仅摘要上传"大脑"，控制带宽与成本。

**扩展形态**：单节点（当前）→ 多 Worker（v4 消息队列+并行）→ Edge+中台（v4 现场跑四步，仅摘要上传）。四步骨架不变，变的是节点数量与拓扑。

| 冲突类型 | 规避方案 |
|---------|---------|
| Batch ID / DB / 目录冲突 | node_id + 本地时间戳（或 UUID）作全局 batch_id |
| 同数据重复处理 | 源分区（各节点只消费指定目录）或中台分发任务 |

---

## 🏗️ Phase 1：标准化与精益生产（v1.x）— ✅ 完成

- [x] 环境变量管理（.env 存密钥）
- [x] 批次复核 Pipeline（集中审批，一封邮件，y/n/all/none）
- [x] 多伦多时区本地化（日志、邮件、DB）
- [x] 工业日志（logs/factory_YYYY-MM-DD.log）
- [x] 物理归档（rejected_material/Batch_ID_Fails, redundant_archives）

---

## 🔧 Phase 1.5：架构重构（v1.5）— ✅ 完成

- [x] 集中配置（config/settings.yaml, config_loader）
- [x] 工具提取（engines/：quality_tools, fingerprinter, db_tools, notifier…）
- [x] 决策分离（qc_engine, reviewer, archiver）
- [x] 流程重构（core/ingest, qc_engine, reviewer, archiver, pipeline, guard）
- [x] 基础指标（批次文件数、大小、耗时、吞吐量等）

---

## 🧠 Phase 2：视觉与自动录入（v2.x）— ✅ 完成

- [x] 计算机视觉 QC：YOLO 单例，config 驱动采样与推理
- [x] 版本映射：Batch_xxx/reports/version_info.json，路径信息含版本，支持血缘与审计
- [x] 双门槛录入：dual_gate_high / dual_gate_low；高自动放行，低自动拒绝，中间人工复核
- [x] MLflow 跟踪：mlflow.enabled；批次级参数/指标
- [x] 置信度分流输出：refinery、inspection（manifest、伪标签 .txt）、质检报告
- [x] 可扩展 QC：quality_tools.register_extra_check，decide_env 统一调度

---

## 🔄 Phase 2.5：数据闭环与持续学习（v2.5）— ✅ 完成

- [x] 置信度分流：高自动放行，低自动拒绝，中间进 inspection
- [x] 高置信伪标签：refinery + inspection 写 YOLO 格式 .txt
- [x] 智能切片：save_only_screened=true 只输出"Warning 或检测到目标"帧
- [x] Inspection 打平：Normal/Warning 合并，只有 manifest.json + 图片 + txt
- [x] 待标池自动更新：低置信/不确定样本自动写入 for_labeling + manifest
- [x] 模型对比：新模型 vs 在线/注册模型离线或在线对比，结果写 MLflow/DB

### 标注回传 & 伪标签一致性验证

- [x] 回传接收：标注数据一次性导入，写入 storage/labeled_return/，创建 Import_YYYYMMDD_HHMMSS
- [x] 伪标签对比：回传 vs 伪标签一致性（IoU 0.5 + class match），输出 comparison_report.json
- [x] 阈值与告警：config 一致性阈值（默认 95%），低于则邮件告警，标记差异样本待复核
- [x] 指标重命名：「一致率」→「伪标签一致率」，明确为差异监控指标，非标注质量评分
- [x] 训练触发：合规数据并入 storage/training/Import_xxx/，关联 import_id
- [x] 标签写回批次：合规后写回 archive/Batch_xxx/labeled/，safe_copy 防静默失败
- [ ] API 上传：可选 HTTP 上传 return zip（预留）

### 主动学习标注优先级（v2.11）

- [x] skip_empty_labels：并入训练时跳过空 .txt 帧
- [x] 设计文档：docs/active_labeling_priority.md
- [ ] production_tools：写 max_confidence、qc_env 到 manifest
- [ ] labeling_export：manifest 含优先级字段；--sort-by-priority
- [ ] export_for_cvat：可选按优先级排序导出

---

## 🖥️ Dashboard & 远程访问（完成 + 预留接口）

- [x] Dashboard：review.mode=dashboard 时入队；python -m dashboard.app 启动 Web UI
- [x] 队列复核：缩略图、评分、规则明细、单条/批量放行或拒绝，无 600s 超时丢失
- [x] 局域网访问：host=0.0.0.0，同网设备访问 http://<机器IP>:8765

| 能力 | 当前 | 预留 / TODO |
|------|------|------------|
| 监听地址 | 0.0.0.0（局域网） | config paths.dashboard_host 可扩展 |
| 端口 | paths.dashboard_port 可配 | — |
| 公网访问 | 手动端口转发 / VPN | 预留：反向代理文档、隧道示例 |
| 鉴权 | 无 | 预留：API 中间件或 Basic Auth |
| 多用户 / 权限 | 无 | 预留：对齐 v4 访问控制 |

---

## ⚡ 高效筛选（四项优化）

| 技术 | 阶段 | 依赖 | 状态 |
|------|------|------|------|
| I-frame 提取 | 解码 | OpenCV/FFmpeg | ✅ 完成 |
| 运动向量唤醒 | 预采样/检测 | OpenCV flow/diff | ✅ 完成 |
| Embedding/Re-ID | 后输出 / 独立任务 | 向量 DB、小模型 | ⬜ TODO |
| 级联检测 | 检测 | 轻量 .pt / ONNX | ✅ 完成；矿车等领域级联 TODO |

四项可组合：I-frame + 运动唤醒减少解码与唤醒次数，级联减少大模型调用，Embedding 支持"谁在哪里"检索与报告。

---

## 🍭 Auto-Modality 路由（v3 TODO）

自动检测文件格式与内容，无需手动配置；混合数据（视频+音频+LiDAR+振动）一次扫描自动路由。

| 当前 | 目标 |
|------|------|
| config modality: video 手动 | 扩展名 + 可选内容探针 → 自动路由 |
| 每批次单一模态 | 按模态分组，各批次走各自 QC/Archive handler |

- [ ] engines/modality_detector.py：detect_modality(path) -> str
- [ ] Ingest：scan_raw 按模态分组返回；pre_filter 按组调用 decode_check
- [ ] Pipeline：支持按模态分批或单批内按文件模态调度
- [ ] Config：modality_filter 替代 modality，向后兼容（modality: video 等价于 modality_filter: ["video"]）
- [ ] 未知格式：默认到 quarantine/unknown_format/，config unknown_format_action 可配

---

## 🧬 Phase 3：Model-Ready & 深度血缘（v3.x）— 🔶 进行中

**目标**：v3 后，模型团队可直接从 Pipeline 输出训练，并追溯"哪个模型用了哪批数据"。

### 数据血缘（v3.0 ✅）

- [x] Transform Log：batch_lineage 表记录 batch_base、source_dir、refinery_dir、inspection_dir、transform_params
- [x] 血缘可视化：scripts/query_lineage.py — --batch、--import-id 或默认列出最近批次
- [x] 标签写回链路：label_import 表记录 import_id、batch_ids、training_dir、consistency_rate、merged_count

### MLflow 数据→模型追溯（v3.0 ✅）

- [x] 数据集链接：MLflow run params 含 refinery_dir、inspection_dir、source_archive_dir
- [x] 模型血缘：batch_lineage + label_import 元数据；可反查训练数据来源
- [x] 可复现性：query_lineage.py 给定 batch_id 反查 transform_params 与路径

### Model Registry（v3.0 ✅）

- [x] config 引用 Registry：vision.model_path 支持 models:/name/version；engines/model_registry.py 解析；scripts/mlflow/register_model.py 注册

### CVAT 本地闭环（v3.1 ✅）

- [x] 自部署 CVAT：本地 Docker 部署，无 SaaS 费用
- [x] API 全自动：自动创建 Project/Task、上传图片+伪标签（scripts/cvat/cvat_upload_annotations.py）
- [x] 标注拉取：自动导出标注结果、格式转换、并入 labeled_return（scripts/cvat/cvat_pull_annotations.py）
- [x] 闭环打通：for_labeling → CVAT → import_labeled_return → training，全程脚本化
- [x] model_train 血缘表：scripts/mlflow/train_model.py 写入，scripts/query_lineage.py --train-id 查询

### 质量分流增强（v3.3 ✅）

- [x] 帧级 refinery_min_confidence 绝对下限：即使排名靠前，低于此值也进 inspection，防差批次污染 refinery
- [x] 视频级三档分流：hit_rate + mean_conf → high/standard/low；低质视频（low 档）整体进 inspection，不受帧级分流影响
  - 4 个阈值可配置：`video_tier_high_detection_rate`、`video_tier_high_conf`、`video_tier_low_detection_rate`、`video_tier_low_conf`
  - 仅在非 precomputed_detections 路径生效（precomputed 采样帧少，分级不准）
  - 日志摘要示例：`📊 视频分级: 高质 3  标准 2  低质 1（低质 → inspection）`

### 标注池分层策略 + Refinery 抽检报警（v3.4 ✅）

- [x] 标注池分层策略：inspection 全量 + refinery 按视频分层抽样（refinery_sample_rate）；抽检 IoU 低于门槛自动发邮件 + approved_split_confidence_threshold / refinery_top_pct 调整建议

### 可观测性双看板（v3.5 ✅）

**SENTINEL-1 — 帧级遥测（port 8766）**

- [x] DataSource 适配层：`--source mock / archive / live` 三档切换（mock 已完成，archive 接入真实归档帧，live 存根待 v4）
- [x] 实时物理 QC：Jitter（AR-1 + 尖峰检测）/ Clarity 0-100%（Laplacian 归一化）/ Brightness 半圆仪表 + 60 帧趋势图
- [x] 视频主视窗：PIL 叠加检测框 + FPS + 硬件温度，base64 JPEG 500ms 刷新
- [x] Model Audit 面板：Confidence 大数字 + 进度条；IoU Snapshot（labeled_return 历史快照）
- [x] SPC 趋势图：置信度 CL/UCL/LCL 控制线，OOC 点红叉标注，先验 → 20 帧后滚动切换
- [x] 静默 CSV 日志：Type_A（物理）/ Type_B（置信度）/ Type_C（IoU）三类报警自动写入

**HQ Global Command Center — 批次级全局视图（port 8767）**

- [x] 全球网络地图：Scattergeo 暗色地图，Sudbury 双圈高亮，卫星弧线，数据包动画（50s 周期）
- [x] 三站点状态卡：Sudbury / Pilbara / Atacama，状态 / 时区 / 气温 / 任务，脉冲点动效
- [x] 系统拓扑图：Edge → DataLink → HQ-Central，ICE 冰蓝虚线 + 移动数据包
- [x] Gold Assets 里程表：CSS digit-flip 翻转动效，读 `batch_metrics.file_count × 300 + 基数`
- [x] Local Edge HW：psutil 真实 CPU / 内存 / 温度 / 电池，3 秒缓存
- [x] HQ Cloud 指标：存储环形图（1.2PB / 5PB）/ 8× H100 利用率横条（Mock）/ 日合格率
- [x] 核心指标仪表（ROW D）：Confidence / Clarity / IoU Snapshot 三块半圆仪表，30 秒读 DB

### HQ 看板增强 + 全屏适配（v3.6 ✅）

**Bug 修复**

- [x] 世界地图白底：移除 `dp-bg` 与 `backdrop-filter`（与 Plotly SVG 合成层冲突），改用显式 `paper_bgcolor="#0B0B0B"` + `template=None`
- [x] `html, body { background: #050505; overflow: hidden }` 修复白底泄漏；`.main-svg { background: transparent }` 防止 Plotly 内部白框

**实时天气（Open-Meteo，无 API Key）**

- [x] `hq.py _poll_weather()`：10 分钟缓存，拉取 Sudbury / Pilbara / Atacama 实时气温 + WMO 天气码 → emoji
- [x] `_get_phase()`：按 UTC 偏移动态计算 Day / Night / Sunrise / Sunset
- [x] `make_site_tiles(weather=None)`：优先显示实时数据，网络失败时降级到静态默认值
- [x] Callback 新增 `Output("hq-sites", "children")`，站点卡每 tick 同步实时天气

**DataFactory 品牌**

- [x] HQ 和 SENTINEL-1 标题栏均新增 **`DF`** 徽标（黑底冰蓝/绿色圆角方块）

**全屏适配（两个看板）**

- [x] 根容器：`height: 100vh; overflow: hidden; display: flex; flexDirection: column`
- [x] 各行按比例分配 `flex`（3 / 2.2 / 1.9 / 1.7），`minHeight: 0` 防止 flex 溢出
- [x] 所有 `dcc.Graph` 改为 `responsive=True`，移除硬编码 `height=` 参数，由容器 CSS 控制尺寸
- [x] SENTINEL-1 左侧 QC 列：gauge 固定 130px + trend 58px，`overflowY: auto`
- [x] SPC 趋势图：`responsive=True + flex: 1` 自适应剩余高度

---

### Site Status 实时时间 + 真实天气（v3.7 ✅）

- [x] `engines/site_info.py`：`get_site_times()`（pytz，IANA 时区，降级 UTC 偏移）+ `get_site_weather()`（OpenWeatherMap Current Weather API，10 分钟缓存，无 Key 时返回 N/A 占位）
- [x] `config/settings.yaml` / `settings.default.yaml`：新增 `sites:` 节（sudbury/pilbara/atacama → timezone / lat / lon）
- [x] Flask 端点：`GET /api/sites/time` 和 `GET /api/sites/weather`（via `app.server.route()`）
- [x] HQ callback：`get_site_times()` 返回值注入 weather dict（`w["local_time"]`），`make_site_tiles(weather)` 3 行布局：站名 / `Status · HH:MM · emoji°C` / 阶段
- [x] `requirements.txt` 新增 `pytz>=2024.1`、`requests>=2.31.0`
- [x] 降级策略：无 API Key → N/A 占位，不影响 dashboard 启动；pytz 未安装 → UTC 偏移估算

---

### 多人协作数据库（v3.2 ✅）

- [x] PostgreSQL（docker-compose.yml，postgres:16-alpine）
- [x] 薄适配层（engines/db_connection.py）：PostgreSQL 生产 / SQLite 仅限 --test 临时隔离
- [x] DATABASE_URL 必须设置，未设置报错退出；--test 模式使用临时 SQLite 不影响生产
- [x] MLFLOW_BACKEND_URI 切换 MLflow 后端到 PostgreSQL

---

## 🐳 Phase 4：规模化与扩展（v4.x）— ⬜ 待做

### 任务编排与监控

- [ ] 任务状态机（Pending/Processing/Reviewing/Done/Fail）
- [ ] 多进程 / 分布式 Worker（消息队列 + 并行 QC）
- [ ] 容器化部署（Docker）+ Prometheus（吞吐量、延迟、通过率）+ Grafana

### Edge 部署

- [ ] 现场跑全 Pipeline，仅上传结果摘要（KB 级）；中台汇总、复核、归档
- [ ] 车辆返场→数据作为 Ingest 输入，接入现有 guard 模式
- [ ] 模型轻量化，边缘↔中台同步（结果上传、config/模型下载），本地数据短期留存
- [ ] 隐私与安全：原始数据留本地；中台只收摘要/关键帧/特征

### 多节点部署

- [ ] node_id + 全局 batch_id（未配置时用 MAC/hostname）
- [ ] 节点上报摘要（HTTP/队列），离线重试（Store-and-Forward）
- [ ] 中台接收、存储、跨节点去重、分发（待标池 manifest / API）

### 多模态（audio/vibration、LiDAR）

- [ ] audio/vibration：modality_handlers 扩展，FFT 频谱，预测性维护
- [ ] raw_lidar/：Ingest（.pcd/.las/.ply），点云 QC，与视频时间戳对齐
- [ ] 统一去重+质量策略，Batch_xxx/video 与 Batch_xxx/lidar 对齐

### 标注质量控制（QC for Annotation）

- [ ] **IAA（Inter-Annotator Agreement）**：同一批图片由 2 名标注员分别标注，比较一致率作为真实质量信号；差异大的样本自动进入复核队列
- [ ] **黄金集测试**：在日常任务中混入已知正确答案的图片，检测标注员是否认真标注（橡皮图章检测）
- [ ] **伪标签一致率阈值调整**：当前 95% 门槛意义不大（人工修正模型错误时必然低于此值）；改为「异常高（>98%）触发橡皮图章报警」 + 「异常低（<5%）触发标注偏差报警」，中间区间视为正常
- [ ] **标注轮次追踪**：记录每张图被标注的次数与标注员 ID，支持 IAA 计算和审计

### HQ 真实数据接入（v4.x）

| 层次 | 内容 | 前置条件 |
|------|------|---------|
| **近期**（改几行 SQL） | Daily Yield 从 `production_history` 实时计算；Confidence/Clarity 均值写入 `batch_metrics`（加两列） | `qc_engine.py` 写批次尾部均值 |
| **中期**（管道配合） | `batch_metrics` 新增 `avg_confidence` / `avg_clarity`；HQ 每 30s 读最新值替代 mock 漂移 | ALTER TABLE + qc_engine 写入 |
| **长期**（多机部署） | Pilbara / Atacama 边缘机器定时心跳写中央 DB；HQ Storage 对接云存储 API；H100 利用率接 DCGM / nvidia-smi | 多节点部署 + 统一 DB |

- [ ] `batch_metrics` 加 `avg_confidence REAL`、`avg_clarity REAL` 列
- [ ] `qc_engine.py` 批次结束时写入帧级均值
- [ ] `hq.py _poll_db()` 读新列替代 mock Confidence/Clarity
- [ ] Daily Yield：`SELECT COUNT(*) FILTER(status='approved') / COUNT(*)` 实时计算
- [ ] 边缘心跳表（`edge_heartbeat`）：node_id / status / last_seen / task，HQ 站点卡读真实状态
- [ ] `SENTINEL-1 --source live`：轮询 DB ring buffer，接入 main.py --guard 实时输出

### 访问控制与多租户

#### 角色体系（RBAC）

| 角色 | 典型用户 | 允许操作 |
|------|----------|----------|
| `admin` | 系统管理员 | 所有操作 + 用户管理 + 配置变更 |
| `engineer` | ML 工程师 | 触发训练、查看全部指标、调整阈值、导出数据 |
| `annotator` | 标注员 | 进入 Review Dashboard、提交 approve/reject |
| `operator` | 现场操作员 | 触发单次 ingest、查看 Sentinel 遥测（只读） |
| `viewer` | 管理层 | HQ 大屏只读、报表下载，不可写任何数据 |

#### 实现计划

- [ ] **用户表**：`users`（id, username, hashed_password, role, created_at）；PostgreSQL 存储
- [ ] **JWT 认证**：登录接口颁发 access_token（24h）+ refresh_token（30d）；无状态，便于多服务共享
- [ ] **Dashboard 门控**：
  - `app.py` (Review) → 仅 `annotator` / `engineer` / `admin`
  - `sentinel.py` → 仅 `operator` / `engineer` / `admin`
  - `hq.py` → 所有已登录用户（`viewer` 可访问）
- [ ] **API 权限装饰器**：`@require_role("engineer", "admin")` 统一拦截未授权请求，返回 401/403
- [ ] **模型组与账号**：各组只能使用和热更新自己的模型资产
- [ ] **燃料与数据归属**：各组只能访问/复制本组模型的燃料（按批次或业务线）
- [ ] **操作审计日志**：谁、何时、做了什么（approve/reject/train/export + batch_id + user_id）写入 `audit_log` 表，可查询可导出

---

## 🔬 数据增强路线图

矿山环境数据采集成本极高，极端场景（碰撞、翻车、极暗隧道）几乎无法真实复现。数据增强是补齐训练数据多样性的关键手段。

### 第一层：在线增强 — 训练时实时生成（✅ v3.8 已实现）

集成进 `scripts/mlflow/train_model.py`，`--augment` 参数控制预设：

| 预设 | 说明 |
|------|------|
| `mining`（默认） | 矿山场景强化：高亮度变化 + 模糊（粉尘）+ 随机遮挡 + 小角度旋转 |
| `default` | YOLOv8 内置默认参数 |
| `off` | 关闭所有增强（消融实验用） |

增强预设自动记录到 MLflow params（`augment_preset`），确保每次训练可复现可对比。

### 第二层：离线增强 — 预生成扩充数据集（⬜ 待做）

- [ ] `scripts/augment_dataset.py`：对已标注数据批量生成增强版本，物理保存到 `storage/training/`
- [ ] 支持 Albumentations 完整管道（CoarseDropout、GaussianNoise、RandomFog、MotionBlur）
- [ ] 增强后数据纳入 DataFactory 血缘追踪（`augment_params` 写入 `batch_lineage`）

### 第三层：合成数据 — 游戏引擎模拟边缘案例（⬜ 未来）

真实数据永远无法覆盖所有危险场景，游戏引擎可以无限生成：

- [ ] **NVIDIA Omniverse / Unreal Engine**：构建地下矿道 3D 场景
  - 随机光照（强光/弱光/闪烁）
  - 粉尘密度变化
  - 设备位置/角度随机
  - 极端场景：碰撞前一刻、人员进入危险区、设备故障状态
- [ ] 自动生成标注（Omniverse 原生支持 YOLO 格式输出）
- [ ] 合成数据 + 真实数据混合训练，按比例可配置

> **战略价值**：矿山合成数据目前几乎是空白市场。谁先建立矿山 3D 场景库，谁就拥有后续所有模型训练的数据护城河。

### 第四层：生成式 AI 增强（⬜ 未来）

- [ ] **Diffusion Model**（Stable Diffusion / DALL-E）生成矿山风格图像
  - 文字描述 → 任意场景图像 → 自动标注
  - 成本极低，边际成本趋近于零
- [ ] **ControlNet**：基于现有帧生成光照/天气变体，保持物体位置不变
- [ ] 生成图像质量筛选（FID 评分），低质图像自动过滤

### 第五层：联邦数据增强（⬜ 长期）

- [ ] 多个矿山各自有不同场景数据（铲车多 / 卡车多 / 人员多）
- [ ] 联邦学习框架下互相补充对方缺少的场景，原始数据不离开现场
- [ ] 与联邦学习路线图（见 Phase 4）合并实现

---

## 🚛 场景扩展：矿车关键帧与物料识别（未来）

**目标**：俯视固定摄像头，捕捉"车辆中心穿越画面中心"那一帧，用于激光雷达体积对齐（产量）和物料分类（砂/矿/煤）。关键帧 = 连续车辆段中 bbox 中心与画面中心距离最小的帧。

---

## 🛠️ 技术栈

| 领域 | 当前 / 规划 |
|------|------------|
| 编程与数据 | Python, SQL, 批处理 |
| ML/CV | 规则引擎 + YOLO (v2)，PyTorch/NumPy |
| 实验与交付 | MLflow (v2)，版本映射，数据闭环 (v2.5) |
| 数据库 | **PostgreSQL**（Docker，必须配置） |
| 标注工具 | **本地 CVAT**（Docker，API 全自动，零成本） |
| 运维与部署 | 日志、YAML、.env、Docker（compose），on-edge (v4) |
| 协作与文档 | Git, README/CHANGELOG/Roadmap，邮件与人工复核闭环 |

---

## 📎 关联文档

| 文档 | 用途 |
|------|------|
| docs/v3_dev_plan.md | v3 开发计划：步骤、验收标准 |
| docs/v3_task_list.md | v3 任务清单（Phase 1–5） |
| docs/architecture.md | 系统架构概述 |
| docs/settings_guide.md | 全量 config 参数参考 |
| docs/cvat_setup.md | CVAT 标注工作流操作指南 |
| docs/active_labeling_priority.md | 主动学习标注优先级设计 |
| docs/archive/ | 历史设计文档（AUDIT_REPORT、architecture_thinking 等） |

---

*文档版本：v2026.03 | 版本线：v1 → v1.5 → v2 → v2.5 → v2.6 → v2.7 → v2.8 → v2.9 → v2.10 → v2.11 → v3.0 → v3.1 → v3.2 → v4 | 对齐工业/矿山 AI 安全、效率与数据质量*
