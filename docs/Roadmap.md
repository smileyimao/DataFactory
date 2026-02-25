# 🗺️ DataFactory 数字化工厂 - MLOps 演进路线图 (v2026.02)

> **Positioning**：本 pipeline 面向**数据采集与质检、准入决策、可追溯归档**的端到端流程，可直接复用到矿业/工业场景下的视频质检、安全巡检与感知数据质量保障（perception data curation），与 AI 驱动的安全、效率与资产利用场景对齐。

---

## 💡 愿景：给 AI 大脑接上高质量数据管道

人脑擅长多模态——触觉、视觉、听觉——但前提是**正确的数据**能**稳定、持续**地进入大脑，大脑才能对环境越来越熟、做出更准的决策。我们做的事本质上是同一类：把高质量的数据（经 QC、去重、不合格过滤）源源不断地喂给「大脑」，驱动它成长。

边缘计算可以类比为**眼球**：视网膜在本地先做大量预处理（亮度适应、边缘增强、运动检测），再通过视神经把已结构化的信号送给大脑，而不是原始像素。这条 pipeline 里的 edge 节点（现场质检、黄金库自检、只传摘要到中心）扮演的也是类似角色：保证送进「大脑」的是干净、可用、稳定的数据。

**产业视角**：大语言模型能快速爆发，是因为语言数据本质上是人类无意识中已经「打过标」的。机器人、自动驾驶则不同：公司必须投入海量成本去采集、清洗、打标，且模态更多。根本瓶颈在于**数据质量与供给**。本 pipeline 的使命即在于此。

*（2026.02 设计动机与类比记录于此，便于后续扩展多模态与边缘部署时回顾。）*

---

## 📐 完整系统结构框架（目标架构）

*主数据流：raw 数据直接进入质检，质检分为两大类别，再进入复核与归档。*

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  数据接入 (Ingest)                                                                │
│  raw_video/  [已实现]     raw_lidar/  [v4 扩展]                                   │
│  Auto-modality routing  [v3 待做]：按文件格式/内容自动识别 → video/audio/lidar/vibration 分流 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  质检 (Funnel QC) — 两大类别，可扩展                                               │
│  (1) 重复检测 [已实现]  MD5/指纹 → DB 对比 → 命中归 redundant_archives            │
│  (1a) Ingest 预检 [v2.8] dedup + 首帧解码 → 失败移入 quarantine/duplicate、quarantine/decode_failed │
│  (1b) 损坏视频 [v2.8 部分] 首帧解码失败 → quarantine/decode_failed；完整质量检测仍在 QC │
│  (2) 不合格检测 [已实现] blur/brightness/jitter + 可扩展(register_extra_check)     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  准入 (Admission) [已实现]  自动放行 + HITL；邮件汇总 → Terminal y/n 或 厂长中控台 Web 复核（入队无超时）  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  归档 (Archive) [已实现]                                                          │
│  Batch_xxx/source  源视频  |  Batch_xxx/reports  质量报告                │
│  refinery（含伪标签 .txt）  |  inspection（按 Batch 可整批拷贝）                 │
│  rejected_material/  不合格  |  redundant_archives/  重复                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Edge（v4）**：现场跑完整 pipeline，只传结果摘要到中心（含**特征提取前置**：向量 + 元数据；金矿关键帧/片段本地落盘、**按需回传**）；**Edge 自动清理（v4）**：重复可配置删除或按天滚动清理，损坏视频可读性检测后移走或删除。

---

## 🧭 架构原则与版本总览

**统一架构思维**：流程（Ingest → Funnel QC → Admission → Archive）+ 工具类（engines/）+ 决策在 core/ + 配置（config/）。工具只返回数值，决策层读配置做判断。

**版本总览**（整体框架不变，仅标注进度）：

| 版本 | 状态 | 核心内容 |
|------|------|----------|
| **v1.x** | ✅ 已完成 | 流程跑通、人机闭环、可追溯、工业级 Logging、物理隔离归档 |
| **v1.5** | ✅ 已完成 | 架构重构：config + engines + core，无新业务 |
| **v2.x** | ✅ 主体已完成 | YOLO、版本映射、双门槛、MLflow、按置信分层落盘、伪标签、不合格可扩展；待做：模型注册与复现 |
| **v2.5** | ✅ 已完成 | 按置信分流、厂长中控台、3_待人工精简、待标池自动更新、新旧模型对比 |
| **v2.6** | ✅ 已完成 | Smart Ingest / 高效筛查：I-帧、运动唤醒、级联检测（四板斧 3/4） |
| **v2.7** | ✅ 已完成 | 工业级加固：P0/P1/P2/P3、Path decoupling、Batch 重命名 — **Edge 部署前最关键一步** |
| **v2.8** | ✅ 已完成 | Ingest 预检：dedup + 首帧解码，失败项移入 quarantine — **流程模块化** |
| **v2.9** | ✅ 已完成 | Modality 解耦；加固：MLflow→db/mlflow.db、labeled 子目录、safe_copy 防静默失败、pytest 套件；根目录清理（mlflow.db、mlruns 等旧产物） |
| **v3.x** | ⬜ 待做 | **模型就绪**：数据血缘、Transform Log、MLflow 数据→模型追溯；**Auto-modality routing**：按文件自动识别并路由 |
| **v4.x** | ⬜ 待做 | **规模与扩展**：多模态（audio/vibration）、FFT、predictive maintenance、Edge、多节点 |

---

## 🚗 角色定位与协作边界（整车与发动机）

我们是造**整车**的，模型团队是造**发动机**的。我们负责产线（Ingest → Funnel QC → Admission → Archive）、配置、部署与可观测性；他们负责模型训练与发布。我们**留接口**（如 `run_vision_scan(cfg, video_paths)`），模型方提供 `.pt` 或实现接口即可接入。部署到 Edge 时仍是同一套 pipeline + 同一份配置，责任清晰。

---

## 🔄 CI/CD 与可部署性

| 维度 | 当前实现 | 说明 |
|------|----------|------|
| 配置与代码分离 | settings.yaml + .env | 改配置即可换环境，无需改代码 |
| 单一入口 | main.py（单次 / --guard） | 便于测试与部署 |
| 启动自检 | startup_self_check | 路径与可写性校验 |
| 黄金库自检（可选） | startup_golden_run | 真跑一遍 QC 冒烟 |
| 冒烟/全链路测试 | pytest tests/e2e/、main.py --test | QC smoke、全链路、Guard 模式 |
| 单元/集成测试 | pytest tests/ -v -m "not e2e" | unit/integration/api 分层；requirements-dev.txt |
| 环境可重置 | scripts/reset_factory.py、reset_config.py | dry-run / for-test / db；reset_config 恢复 settings.default.yaml |
| 版本可追溯 | version_mapping、version_info.json、path_info | 每批规则/模型版本可审计 |
| **待自动化** | CI 自动跑 pytest、main.py --test、v3 Docker | 当前设计已支持，流水线待接 |

---

## 📈 规模扩大与多节点（设计已就绪，实现属 v4）

**定位**：系统是公司的「感官」——在边缘完成 Ingest → QC，只把摘要送「大脑」，控制带宽与成本。

**扩展形态**：单机（当前）→ 多 Worker（v4 消息队列+并行）→ Edge+中心（v4 现场跑四步、只传摘要）。四步骨架不变，加的是节点数与拓扑。

**多节点设计要点**（详见下文章节，实现项在 v4）：
- **冲突避免**：node_id + 全局 batch_id，DB/目录不碰撞。
- **协同**：按源划分（每节点本地 raw）或中心分配任务。
- **中心整理**：接收摘要入库、跨节点去重、分发给标注/训练/运营。

---

## 🔀 多节点部署：冲突、协同与中心汇总（概要）

| 冲突类型 | 应对 |
|----------|------|
| 批次号/DB/目录碰撞 | node_id + 本地时间戳（或 UUID）作为全局 batch_id |
| 重复处理同一份数据 | 数据源划分（每节点只消费指定目录）或中心下发任务 |

**中心**：接收各节点摘要 → 入库、去重、按批次/节点/时间分发。**具体实现项**见阶段三「多节点部署」。

---

## 🏗️ 阶段一：标准化与精细化生产 (v1.x) — ✅ 已完成

*核心：工业级准入、人机闭环、可追溯*

- [x] 环境变量管理（.env 隔离敏感信息）
- [x] 批处理复核流水线（集中审批、一封邮件、y/n/all/none）
- [x] 多伦多时区本地化（日志、邮件、DB）
- [x] 工业级 Logging（`logs/factory_日期.log`）
- [x] 物理隔离归档（rejected_material/Batch_ID_Fails、redundant_archives，废片 `原名_得分pts`）
- [ ] 数据清洗与标注管道扩展（为接入 ML 做准备）

---

## 🔧 阶段一点五：架构重构 (v1.5) — ✅ 已完成

*核心：流程+工具+决策+配置拆分，为 v2 打基础*

- [x] 配置集中化（config/settings.yaml、config_loader）
- [x] 工具类抽取（engines/：quality_tools、fingerprinter、db_tools、notifier、file_tools、report_tools、production_tools）
- [x] 决策类分离（qc_engine、reviewer、archiver）
- [x] 流程类重构（core/ingest、qc_engine、reviewer、archiver、pipeline、guard）
- [x] 入口与兼容（main.py 单次 / --guard）
- [x] 基础指标收集（批次文件数、大小、耗时、吞吐量等）

---

## 🧠 阶段二：视觉感知与自动化准入 (v2.x) — ✅ 主体已完成

*核心：YOLO、版本映射、双门槛、MLflow、置信分层落盘、不合格可扩展*

**已实现**

- [x] **计算机视觉质检**：YOLO 单例、config 抽帧与推理（conf/iou/device 等全配置化），决策在 qc_engine
- [x] **版本映射**：Batch_xxx/reports/version_info.json、path_info.version_mapping，便于血缘与审计
- [x] **双门槛准入**：dual_gate_high / dual_gate_low；高分放行、低分拦截、中间人工复核
- [x] **MLflow Tracking**：mlflow.enabled；批次级 params/metrics 记录
- [x] **按置信分层落盘**：refinery、inspection（含 manifest、伪标签 .txt），质量报告在 Batch_xxx/reports
- [x] **不合格检测可扩展**：quality_tools.register_extra_check，decide_env 统一调度

**待做**

- [ ] **模型注册与复现**：model registry 与训练/评估 pipeline 打通

**规划（不改主流程）**

- **多模型接入**：配置/注册表 + 统一推理接口，多模型注册后按任务选用
- **模型参数调整界面**：按模型分片配置或小型 Web/API，做模型的人只改自己名下的模型参数；可与 MLflow 联动

---

## 🔄 阶段二点五：数据闭环与持续学习 (v2.5) — 🔶 部分已完成

*核心：按置信分流 → 待标池/伪标签 → 训练触发 → 新旧模型对比*

**已实现**

- [x] **按置信度分流**：与双门槛衔接，高分放行、低分拦截、中间态进 inspection
- [x] **按置信区间落盘**：refinery、inspection，带 manifest 与伪标签 .txt
- [x] **高置信伪标签**：燃料与待人工写图时同步写 YOLO 格式 .txt（无检测时写空），便于标注工具一一对应
- [x] **YOLO 筛查落盘**：`production_setting.save_only_screened=true` 时只落盘「Warning 或 有检测」的帧，减少全量切片（见 docs/smart_slicing.md）

**待做**

- [x] **inspection 精简**：Normal/Warning 合并，只保留 manifest.json + 图片 + txt，便于 for_labeling 直接导入（`production_setting.human_review_flat=true`）
- [x] **待标池自动生成与更新**：低置信/不确定样本自动写入 for_labeling + manifest，按批次或阈值筛选（`labeling_pool.auto_update_after_batch=true`，归档后自动追加）
- [x] **新旧模型对比**：新模型与线上/注册模型离线或在线对比，结果入 MLflow/DB，支持上线决策（`scripts/compare_models.py --new X --baseline Y --data DIR`）

### 标注回传与伪标签一致性校验（多级净化）

*目标：建立标注团队回传线路，用伪标签抽检做一致性校验，反复循环提炼更纯净的 AI 燃料。*

**流程**

1. **伪标签抽检**：从 refinery 按比例（如 5%–10%）抽一批样本进入 for_labeling，供标注团队标。
2. **回传线路**：标注团队完成标注后，一次性传回（YOLO/COCO 等格式），落盘到指定目录（如 `storage/labeled_return/`）。
3. **一致性对比**：回传标签 vs 伪标签逐图对比（IoU、类别、框数等），计算一致率。
4. **门槛与报警**：设置差异门槛（如一致率 < 95% 自动报警），要求对差异部分再次复核。
5. **循环净化**：复核后更新标签 → 再对比 → 达标后并入训练集；未达标继续复核。多轮迭代，提炼更纯净的 AI 燃料。

**待实现**

- [x] **回传接收**：标注数据一次性导入（目录/压缩包），写入 `storage/labeled_return/` 并生成 Import_YYYYMMDD_HHMMSS
- [x] **伪标签对比**：回传 vs 伪标签一致性计算（IoU 0.5 + 类别匹配），输出 `comparison_report.json` 差异报告
- [x] **门槛与报警**：配置一致率门槛（如 95%），低于则触发邮件报警（`labeled_return.alert_via_email`），标记差异样本待复核
- [x] **训练触发**：达标数据并入 `storage/training/Import_xxx/`，与 import_id 关联
- [x] **标注回写批次**：达标后按 batch_id 写回 `archive/Batch_xxx/labeled/`，safe_copy 防静默失败
- [ ] **API 上传**：可选 HTTP 上传回传压缩包（预留）

**完成标准**：回传线路打通；伪标签抽检与一致性校验可运行；门槛报警生效；训练触发有明确入口。

---

## 🖥️ 厂长中控台与远程访问（已实现 + 预留接口）

*核心：Web 复核替代 Terminal 阻塞，为远程操作留扩展点*

**已实现**

- [x] **厂长中控台**：`review.mode=dashboard` 时 blocked 入队，`python -m dashboard.app` 启动 Web 界面
- [x] **队列复核**：缩略图、得分、规则分项、单项/批量放行或拒绝，无 600s 超时丢料
- [x] **局域网访问**：`host=0.0.0.0`，同网段设备可通过 `http://<机器IP>:8765` 访问

**远程访问预留接口（v3 或后续）**

| 能力 | 当前 | 预留/待做 |
|------|------|-----------|
| 监听地址 | `0.0.0.0`（已支持局域网） | 配置 `paths.dashboard_host` 可扩展 |
| 端口 | `paths.dashboard_port` | 已配置化 |
| 外网访问 | 需手动端口转发/VPN | 预留：反向代理配置说明、内网穿透示例 |
| 鉴权 | 无 | 预留：API 层加 middleware 或 Basic Auth，前端加登录页 |
| 多用户/分权 | 无 | 预留：与 v4 分权管理对齐 |

**实现建议**：dashboard 为 FastAPI 应用，后续可在 `dashboard/app.py` 增加 `middleware` 鉴权、`/api/` 前缀统一、CORS 配置等，不改主流程。

---

## ⚡ 高效筛查技术线（业界四板斧）

*目标：在「解码 + 检测」阶段就少算、晚算，而不是只靠落盘筛选。四项均可接入当前 pipeline，形成“先粗筛再细算”的唤醒链。*

### 1. 关键帧 / I-帧提取（Key-frame / I-Frame）

- **原理**：视频由 I-帧（全量图像）和 P/B-帧（像素变化）组成。只扫 I-帧（例如每秒 1–2 帧），若 I-帧无目标则中间 P/B 帧**不解码**。
- **接入点**：在 `production_tools` 或独立 `engines/frame_io` 中，用 OpenCV/FFmpeg 只读 I-帧，再对 I-帧跑质量 + YOLO；有命中的时间段再按需解 P/B 做细粒度。
- **效果**：计算量可降约 90%（视 GOP 结构而定）。
- [x] **已实现**：`engines/frame_io.py`、配置 `vision.use_i_frame_only`；production_tools 与 vision_detector 均支持；需 ffprobe，失败则回退按秒抽帧。

### 2. 运动向量 / 光流唤醒（Motion Vector Analysis）

- **原理**：用光流或帧差算运动梯度，画面静止（矿井无车无人）时**不启动 YOLO**；仅当运动超过阈值（如车进画面）才唤醒检测。
- **接入点**：在抽帧循环内，先算 OpenCV 光流或简单帧差，低于阈值则跳过本帧检测与落盘，只记入 manifest 为“静态”。
- **效果**：GPU 唤醒次数大幅减少，功耗与延迟双降。
- [x] **已实现**：`engines/motion_filter.py`、配置 `vision.motion_threshold`（0=关闭）；与 `save_only_screened` 组合使用。

### 3. 特征向量索引与 Re-ID（Embedding & Indexing）

- **原理**：用小模型将图像/人转成 128/512 维向量，写入向量库（Milvus / Faiss）；查询时“搜数字”而非“扫录像”，毫秒级定位「某人出现在哪段视频」。
- **接入点**：在量产或独立索引任务中，对落盘关键帧（或 I-帧）提 embedding，写入向量库并关联 `batch_id + 时间戳`；检索接口返回 (video_id, start_ts, end_ts)。
- **效果**：支持“谁在哪儿出现过”的检索与报表，与现有 QC/归档并列，不替代 YOLO，只做上层索引。
- [ ] **待做**：embedding 模型接入、向量库选型与写入、检索 API；可选与 Re-ID 模型联合。

### 4. 级联检测器（Cascaded Detectors）

- **原理**：先用极小、低精度模型（几百 KB）做**初筛**，仅当小模型说“有东西”时再上 YOLO 或更大模型确认。
- **接入点**：在 `vision_detector` 或抽帧循环前增加一层「轻量检测」；仅当轻量输出超过置信阈值时，再调用现有 `run_vision_scan`。
- **效果**：空画面被轻量模型过滤，大模型只算候选帧，吞吐与成本显著优化。
- [x] **已实现**：配置 `vision.cascade_light_model_path`、`cascade_light_conf`；与 I-帧、运动唤醒组合。

### 小结

| 技术 | 作用阶段 | 依赖 | 与当前 pipeline 关系 |
|------|----------|------|---------------------------|
| I-帧 | 解码 | OpenCV/FFmpeg | 替代或补充“按秒全解码” ✅ |
| 运动唤醒 | 抽帧/检测前 | OpenCV 光流/帧差 | 在现有抽帧循环内加一层判断 ✅ |
| Embedding/Re-ID | 落盘后 / 独立任务 | 向量库、小模型 | 与 QC 并列，提供检索与“谁在哪儿” |
| 级联检测 | 检测 | 轻量 .pt / ONNX | 在 vision_detector 前加一阶 ✅ |

四条可组合使用：例如 **I-帧 + 运动唤醒** 先减解码与唤醒次数，**级联** 再减大模型调用，**Embedding/Re-ID** 做检索与报表。详见 **docs/smart_slicing.md** 与后续「高效筛查」设计文档。

---

## 🍭 Auto-modality Routing（按文件自动识别与路由）— ⬜ v3 待做

*核心：Ingest 根据文件格式与内容自动判断 modality，无需人工配置；混合数据（视频+音频+LiDAR+振动）一次扫描自动分流。*

### 设计目标

| 当前 | 目标 |
|------|------|
| `config modality: video` 人工指定 | 自动检测：扩展名 + 可选内容探测 → 路由到对应通道 |
| 单一 modality 一批 | 按 modality 分组，每批走各自 QC/Archive handler |
| 换数据类型需改 config | 零配置：raw 目录混放，自动分流 |

### 实现步骤

#### 1. 识别方式（非指纹）

**不用指纹**：指纹（MD5）用于去重（内容身份），不用于格式识别。Modality 识别用：

| 层级 | 手段 | 说明 |
|------|------|------|
| **扩展名** | 主判据，O(1) | .mp4→video、.wav→audio、.pcd→lidar、.csv→vibration |
| **Magic bytes** | 可选，读文件头 | .bin 区分 lidar 点云 vs 振动二进制；避免误判 |
| **内容探测** | 可选 | .mp4 用 ffprobe 查 stream 类型（video vs 纯音频）；.csv 读表头判断列含义 |

**优先级**：扩展名 → 命中注册表则返回；未命中或歧义（如 .bin）→ Magic bytes；仍不确定 → `unknown`。

#### 2. 格式→modality 注册表

| 格式/扩展名 | modality | 说明 |
|-------------|----------|------|
| .mp4, .mov, .avi, .mkv | video | 视频容器；可用 ffprobe 区分纯音频 |
| .wav, .mp3, .flac, .m4a | audio | 音频 |
| .pcd, .las, .ply | lidar | LiDAR 点云（扩展名唯一） |
| .bin (点云) | lidar | 需 Magic bytes 或配置约定 |
| .csv, .bin (振动) | vibration | 振动；.csv 可读表头，.bin 需 Magic bytes |
| 未注册 / 无法判断 | unknown | **进 quarantine/unknown_format/**，不静默丢弃 |

#### 3. Ingest 改造

```
get_video_paths() / get_raw_paths()
    → 扩展为 scan_raw(cfg, paths)
    → 对每个文件：detect_modality(path) → "video" | "audio" | "lidar" | "vibration" | "unknown"
    → 按 modality 分组：{video: [p1,p2], audio: [p3], ...}
    → 返回 groups，或保持扁平但每项带 modality 标签
```

**pre_filter**：在 dedup/decode_check 之前或之后，按 modality 调用对应 `modality_handlers.decode_check`。

#### 4. Pipeline 路由

- **方案 A**：按 modality 分批，每批独立跑 pipeline（batch_id 可带 modality 后缀，如 `Batch_20260224_video`）
- **方案 B**：单批混合，pipeline 内按文件 modality 分发到不同 QC/Archive 逻辑

推荐 **方案 A**：批次语义清晰，DB/归档结构简单。

#### 5. Config 角色

| 配置项 | 含义 |
|--------|------|
| `modality_filter: null` | 处理所有检测到的 modality（默认） |
| `modality_filter: "video"` | 仅处理 video，其余跳过或进 quarantine |
| `modality_filter: ["video", "audio"]` | 白名单，只处理列出的 modality |

#### 6. 未知类型处理

- **默认**：移入 `quarantine/unknown_format/`，与 duplicate、decode_failed 同级；打 WARNING 日志。
- **可配置**：`unknown_format_action: "quarantine"`（默认）或 `"skip"`（仅 log 跳过，不移动）。
- **原则**：不静默丢弃；人工可定期检查 quarantine/unknown_format/ 后决定纳入注册表或删除。

### 与现有架构关系

- **modality_handlers**（v2.9）：已有 `decode_check(path, cfg)` 按 modality 分发；入口从 config 改为 `detect_modality(path)` 返回值
- **Ingest pre_filter**（v2.8）：在 pre_filter 内或之前加 modality 检测
- **扩展**：新 modality 只需注册 `format → modality` + 实现 handler，不改主流程

### 完成标准

- [ ] `engines/modality_detector.py`：`detect_modality(path) -> str`，基于扩展名 + 可选 ffprobe
- [ ] Ingest：`scan_raw` 返回按 modality 分组；pre_filter 按组调用对应 decode_check
- [ ] Pipeline：支持按 modality 分批或单批内分发
- [ ] Config：`modality_filter` 替代 `modality`，向后兼容（modality: video 视为 filter）
- [ ] 未知格式：默认进 `quarantine/unknown_format/`，可配置 `unknown_format_action`
- [ ] **Backward Compatibility**：旧 `modality: "video"` 等价 `modality_filter: ["video"]`，零改动迁移（见下）

### 配置回退兼容 (Backward Compatibility) — v3 必须

**场景**：大厂平滑迁移；老同事的旧配置 `modality: "video"` 不能一更新就报错。

**设计**：

- **保留** `modality: "video"` 语义：视为 `modality_filter: "video"`，仅处理 video 文件，其余跳过。
- **兼容** `modality: "audio"`、`modality: "lidar"` 等单值：等价于 `modality_filter: ["audio"]`。
- **新配置** `modality_filter: null` 或 `["video","audio"]`：显式控制。
- **迁移**：config_loader 读取时，若存在 `modality` 且无 `modality_filter`，则 `modality_filter = [modality]`；旧配置零改动即可继续工作。

---

## 🧬 阶段三：模型就绪与深度溯源 (v3.x) — ⬜ 待做

*核心：数据→模型可追溯，团队可直接跑模型；Deep lineage 让 MLflow 真正闭环*

**目标**：v3 完成后，模型团队可基于 pipeline 产出直接训练，且能追溯「哪个模型用了哪些数据」。

### 数据血缘与 Transform Log

- [ ] **转换算子记录 (Transform Log)**：抽帧率、压缩码率、分辨率等算子参数可审计
- [ ] **可视化血缘图谱**：按 Batch_ID 查看端到端数据流转（raw → QC → refinery/inspection → labeled → training）
- [ ] **标注回写关联**：标注完成后回写 DB，与批次/模型版本关联

### MLflow 数据→模型追溯

- [ ] **Dataset 关联**：MLflow run 关联 training 数据来源（batch_id、refinery/inspection 路径）
- [ ] **Model lineage**：模型版本可追溯至训练数据批次与变换链路
- [ ] **可复现**：给定模型版本，可反查其训练数据与 QC 参数

### Labeling 工作流

- [ ] 与 Label Studio/CVAT 对接；待人工已按 Batch 组织，同事可整批拷贝
- [ ] 标注完成后回写 DB，与批次/模型版本关联

---

## 🐳 阶段四：规模与扩展 (v4.x) — ⬜ 待做

*核心：海量吞吐、多模态、Edge、多节点、分权管理*

### 任务编排与监控

- [ ] 任务状态机（Pending/Processing/Reviewing/Done/Fail）
- [ ] 多进程/分布式 Worker（消息队列 + 并行质检）
- [ ] 容器化部署（Docker）+ Prometheus 资源与业务指标（吞吐、延迟、合格率等）+ Grafana

### Edge 部署

- [ ] **场景**：现场跑完整 pipeline，只传结果摘要（KB 级）；中心汇总、复核、归档
- [ ] **车→站点传输管道**：车回集中区后数据落盘为 Ingest 输入，与现有 guard 衔接
- [ ] **技术**：模型轻量化、edge↔中心同步（结果上传、配置与模型下发）、模型热更新、本地数据短期保留
- [ ] **隐私与安全**：原始数据不外传；中心只收摘要/关键帧/特征；Edge 自动清理重复与损坏视频（见上文框架）

#### 特征提取前置 + 按需回传金矿（矿井带宽场景）

*目标：在带宽受限场景下，Edge 只回传轻量向量与摘要，金矿（可标注/训练的关键帧或片段）本地落盘，由中心按需拉取。*

| 角色 | 行为 |
|------|------|
| **Edge（矿井侧）** | 跑完整 pipeline（可接四板斧）→ 关键帧/片段本地落盘；对关键帧提 embedding → **只回传**：向量 + manifest/摘要（时间、摄像头、有无目标等） |
| **中心** | 接收向量入库、做检索/报表/复核；**按需**向 Edge 请求「某摄像头某时间段」的关键帧或短视频 → 拉回后进标注/训练/归档 |

**待做**

- [ ] **回传协议**：Edge 上报 payload 定义（向量 + 元数据 + 可选缩略图 URL/ID），与现有摘要格式统一或扩展
- [ ] **向量与金矿关联**：Edge 侧向量写入时关联 `(node_id, batch_id, 时间戳, 摄像头)`，中心检索结果可映射到「可请求的片段」
- [ ] **按需拉取接口**：中心 → Edge 请求「某节点、某时间段、某摄像头」的关键帧或片段；Edge 返回打包文件或流，落盘到中心 `storage/` 后走现有 Ingest/QC
- [ ] **部署形态**：Edge 按**站点/汇聚点**部署（一矿一节点或一机房一节点），而非每摄像头一节点；同一 pipeline 代码在中心与 Edge 共用，配置区分「仅摘要上传」与「全量落盘」

**与四板斧关系**：I-帧、运动唤醒、级联检测在 Edge 先接好可进一步减算力与带宽；Embedding 即「特征前置」的实现，向量回传后中心做检索再触发按需回传金矿。

### 多节点部署（实现项）

- [ ] node_id 与全局 batch_id（未配置时用 MAC/主机名）
- [ ] 节点侧：上报摘要（HTTP/队列）、断网重试（Store-and-Forward）
- [ ] 中心侧：接收入库、跨节点去重、分发出口（待标池 manifest / API）
- [ ] 配置与部署说明（主节点/各节点参数分离）

### 多模态（audio/vibration、LiDAR）

- [ ] **audio/vibration**：modality_handlers 扩展，FFT 频谱、predictive maintenance
- [ ] **raw_lidar/**：接入（.pcd/.las/.ply）、点云质量检查、与视频时间戳对齐
- [ ] 统一重复+不合格策略，Batch_xxx/video 与 Batch_xxx/lidar 对齐

#### 跨模态时间对齐 (Temporal Sync) — v4

**场景**：矿车 10:00 发生剧烈震动，需同时看 10:00 的视频与 10:00 的振动数据，做多模态融合分析。

**设计**：`detect_modality` 同时强制提取 **Timestamp**。无论何种模态，入库时必须有统一字段 `observed_at`（或 `timestamp`）。

| 模态 | 时间戳来源 |
|------|------------|
| video | 文件元数据（creation_time）、或首帧 PTS、或文件名约定 |
| audio | 同上 |
| lidar | 点云帧头、或文件名时间戳 |
| vibration | CSV 首列/时间列、或文件名 |

**入库**：DB、manifest、MLflow 均带 `observed_at`；MLOps 可按时间窗口做跨模态关联（如「10:00±5s 的视频+振动」）。

#### 硬件资源排他性 (Resource Locking) — v4 Edge

**场景**：视频吃 GPU，振动吃 CPU/内存；多模态并发可能把 Edge 盒子跑崩。

**设计**：在 `modality_handlers` 中增加**资源声明**。Handler 启动前检查资源占用，满足才执行。

| Handler | 资源声明 | 检查逻辑 |
|---------|----------|----------|
| VideoHandler | gpu | 检查 GPU 占用率/显存；超阈值则排队或跳过 |
| LidarHandler | memory | 检查可用内存；点云大文件需预留 |
| VibrationHandler | cpu | 可选：CPU 负载高时降频或排队 |
| AudioHandler | cpu | 通常轻量，可与其他 CPU 型串行 |

**实现**：`modality_handlers` 注册 `required_resources: ["gpu"]`；调度层在启动 handler 前调用 `resource_guard.acquire(resources)`，用毕 `release`。Edge 单机时可简单串行：同一时刻只跑一个「重资源」modality。

### 分权管理与多租户（权限、审计、专属账号）

- [ ] **模型组与专属账号**：每组只能使用与热更新自己名下的模型资产
- [ ] **燃料与数据归属**：各组只能领取/拷贝本组模型燃料（按批次或业务线）
- [ ] **拷贝与操作审计**：谁、何时、拷贝了哪些资料（批次 ID、目录、账号）落库可查
- [ ] **目标**：分权清晰、各拿各的燃料、各更各的模型、拷贝可追溯

### 质检扩展

- [ ] LiDAR 侧不合格规则（密度、范围、spatial_consistency 等），保持「重复+不合格」两类清晰
- [ ] **扩展方向（可选）**：传感器融合、SLAM/定位、3D 检测等与矿业/自动驾驶对齐

---

## 🚛 场景扩展：矿车关键帧与物料识别（日后实现）

*讨论结论记录，供日后对照。*

**目标**：顶视固定机位取「车中心过画面中心」一帧，用于与 Lidar 体积对齐反推产量、及物料分类（砂石/矿石/煤矿等）。**关键帧**：连续有车段落内 bbox 中心与画面中心距离最小的帧。**bbox**：先数学（背景减除+轮廓）→ 初版标注训练 YOLO → 再用模型出 bbox 选关键帧。

---

## 🛠️ 技术与工具栈对齐

| 领域 | 当前 / 规划 |
|------|-------------|
| 编程与数据 | Python，SQL，数据结构与批处理 |
| ML/CV | 规则引擎 + YOLO（v2），PyTorch/NumPy 规划 |
| 实验与交付 | MLflow（v2），版本映射，数据闭环（v2.5） |
| 运维与部署 | Logging，YAML，.env，Docker（v3），on-edge |
| 协作与文档 | Git，README/CHANGELOG/Roadmap，邮件与人工复核闭环 |

---

## 📎 相关文档

| 文档 | 用途 |
|------|------|
| **docs/v3_dev_plan.md** | V3 开发计划：步骤拆解、排期、验收标准 |
| docs/architecture_thinking.md | 依赖注入、接口、状态机等进阶 |
| docs/batch_output_confidence_tiers.md | refinery、inspection 命名与落盘逻辑 |

---

*文档版本：v2026.02 | 版本线：v1 → v1.5 → v2 → v2.5 → v2.6 → v2.7 → v2.8 → v2.9 → v3 → v4 | 与工业/矿业 AI 安全、效率与数据质量需求对齐*

**V3 开发计划**：详见 [docs/v3_dev_plan.md](v3_dev_plan.md)（步骤拆解、排期建议、验收标准）。
