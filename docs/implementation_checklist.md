# ✅ DataFactory 逐步实现清单（与 Roadmap 对照）

> 对照 Roadmap 与当前代码库，明确**已实现**与**待做**，便于按步骤执行。  
> 更新自：代码库浏览 + Roadmap v2026.02。

---

## 📂 当前代码库概况

| 文件/目录 | 作用 | 对应 Roadmap |
|-----------|------|--------------|
| `main.py` | 总开关：单次运行 / `--guard` 持续监控 | v1.5 ✓ |
| `core/` | ingest, qc_engine, reviewer, archiver, pipeline, guard | v1.5 ✓ |
| `engines/` | quality_tools, fingerprinter, db_tools, notifier, file_tools, report_tools, production_tools | v1.5 ✓ |
| `config/` | settings.yaml、config_loader、startup（自检/滚动清零/黄金库） | v1.5 ✓ |
| `storage/` | raw, archive, rejected, redundant, reports, for_labeling | v1.6 ✓ |
| `db/` | factory_admin.db（production_history、batch_metrics、sync_id 预留） | v1.6 ✓ |
| `.env` / `.env.example` | 敏感信息（EMAIL_PASSWORD 等） | v1 ✓ |
| `legacy/` | main_factory、factory_guard 等旧入口，兼容参考 | v1 兼容 |

---

## 🏗️ 阶段一 (v1.x) — 标准化与精细化生产

| # | Roadmap 项 | 状态 | 说明 |
|---|------------|------|------|
| 1 | 环境变量管理（.env 隔离） | ✅ 已实现 | `.env` + `.env.example`，EMAIL_PASSWORD 等 |
| 2 | 批处理复核流水线（一封邮件、y/n/all/none） | ✅ 已实现 | `main_factory.run_smart_factory`，send_batch_qc_report，_ask_review_one |
| 3 | 多伦多时区本地化 | ✅ 已实现 | `log_setup`、batch_id、DB 记录、now_toronto() |
| 4 | 工业级 Logging（[时间][级别][模块]、关键事件） | ✅ 已实现 | `log_setup.setup_logging`，logs/factory_[日期].log |
| 5 | 物理隔离归档对齐（rejected/redundant、Batch、_得分pts） | ✅ 已实现 | rejected_material/Batch_xxx_Fails，redundant_archives，重命名逻辑 |
| 6 | 数据清洗与标注管道扩展 | ❌ 未做 | 可选；为 ML 做准备的清洗/标注/增强 pipeline |

**v1 小结**：1–5 已完成；6 为可选收尾。

---

## 🔧 阶段一点五 (v1.5) — 架构重构

| # | Roadmap 项 | 状态 | 说明 |
|---|------------|------|------|
| 7 | Phase 1 — 配置集中化 | ✅ 已实现 | config/settings.yaml、config/config_loader.py，路径解析为绝对路径 |
| 8 | Phase 2 — 工具类抽取 | ✅ 已实现 | engines/：quality_tools, fingerprinter, db_tools, notifier, file_tools, report_tools, production_tools |
| 9 | Phase 3 — 决策类分离 | ✅ 已实现 | 质检决策在 qc_engine + quality_tools.decide_env；复核在 reviewer；归档在 archiver |
| 10 | Phase 4 — 流程类重构 | ✅ 已实现 | core/ingest, qc_engine, reviewer, archiver, pipeline；guard 在 core/guard.py |
| 11 | 入口与兼容（main.py，行为不变） | ✅ 已实现 | main.py 调用 core.pipeline；--guard 调用 core.guard；行为与 v1.x 一致 |
| 12 | 基础指标收集 | ✅ 已实现 | 批次结束输出：文件数、总大小 GB、耗时秒；日志记录批次摘要 |

**v1.5 小结**：7–12 已完成；旧入口 main_factory.py / factory_guard.py 保留，推荐使用 `python main.py` / `python main.py --guard`。

---

## 🧠 阶段二 (v2.x) — 视觉感知与自动化准入

| # | Roadmap 项 | 状态 | 说明 |
|---|------------|------|------|
| 13 | 计算机视觉质检接入（YOLO、单例、智能抽检） | ✅ 已实现 | engines/vision_detector.py，抽帧+推理，config 全参数 |
| 14 | 为 Edge Deployment 做准备（轻量化、配置可下发） | ✅ 已实现 | vision 段预留 edge_lightweight；接口配置可下发 |
| 15 | 版本映射 (Version Mapping) | ✅ 已实现 | version_info.json、path_info.version_mapping、日志 |
| 16 | “双门槛”自适应准入 | ✅ 已实现 | dual_gate_high/dual_gate_low，自动放行/拦截，中间态人工复核 |
| 17 | MLflow Tracking | ✅ 已实现 | config mlflow.enabled，批次级 params/metrics 记录 |
| 18 | 模型注册与复现 | ❌ 未做 | model registry，与训练/评估 pipeline 打通 |
| 19 | 不合格检测可扩展（配置/插件） | ✅ 已实现 | quality_tools.register_extra_check，decide_env 统一调度 |

**v2 小结**：13–17、19 已完成；18 模型注册留待 v2.5 或后续。**v2.0 主体已完成**，详见 **docs/v2_kickoff.md**。

---

## 🐳 阶段三 (v3.x) — 高并发、多模态、云原生

| # | Roadmap 项 | 状态 | 说明 |
|---|------------|------|------|
| 20 | 任务状态机 (State Machine) | ❌ 未做 | Pending/Processing/Reviewing/Done/Fail |
| 21 | 多进程/分布式 Worker | ❌ 未做 | 消息队列、多任务并行 |
| 22 | 容器化部署 (Docker) | ❌ 未做 | 镜像、Prometheus 资源监控 |
| 23 | 系统处理指标监控（Prometheus + Grafana） | ❌ 未做 | 吞吐量、延迟、资源、业务指标 |
| 24 | Edge Deployment（边缘部署） | ❌ 未做 | edge 节点处理、只传结果摘要、同步机制 |
| 25 | LiDAR 点云数据接入 | ❌ 未做 | .pcd/.las/.ply，点云质检，时间戳对齐 |
| 26 | 统一多模态质检 | ❌ 未做 | 视频+LiDAR 统一策略、归档结构 |
| 27 | 与标注流程对接（Labeling） | ❌ 未做 | 导出待标注、回写、版本关联 |
| 28 | 不合格检测扩展（LiDAR 侧规则） | ❌ 未做 | 点云密度、范围等 |

**v3 小结**：全部未做；可先做 20→21→22→23，再 24；25→26 与 27→28 可并行或按需排期。

---

## 🚀 阶段四 (v4.x) — 真实生产与深度溯源

| # | Roadmap 项 | 状态 | 说明 |
|---|------------|------|------|
| 29 | 转换算子记录 (Transform Log) | ❌ 未做 | 抽帧率、码率、分辨率等 |
| 30 | 可视化血缘图谱 (Data Lineage Graph) | ❌ 未做 | UI 按 Batch_ID 查流转 + 处理指标 |
| 31 | 扩展方向（传感器融合、SLAM、3D） | ❌ 未做 | 可选 |

**v4 小结**：全部未做；29→30 为 v4 核心。

---

## 📋 建议的逐步实现顺序

### v1.5 — 已完成 ✅
1–6 项（配置集中、工具抽取、决策分离、流程重构、main.py、基础指标）均已实现；当前推荐入口为 `main.py` / `main.py --guard`。

### v2.0 开工 — 当前阶段
- 详见 **docs/v2_kickoff.md**（分批任务、首项落地、依赖与接口）。
- 建议顺序：**13+14**（YOLO + Edge 预留）→ **15** 版本映射 → **16** 双门槛 → **17** MLflow → **18** 模型注册；**19** 不合格检测可扩展可与 13 并行或稍后。

### 立即可做（可选）
- [ ] **v1 可选**：数据清洗与标注管道扩展（若要做 ML 准备）。

### 第三步：v3 扩展
13. [ ] **20–23** 状态机、Worker、Docker、Prometheus+Grafana。  
14. [ ] **24** Edge Deployment（同步、数据策略）。  
15. [ ] **25–28** LiDAR、多模态、Labeling、不合格扩展。

### 第四步：v4 溯源
16. [ ] **29–30** Transform Log、数据血缘图谱。  
17. [ ] **31** 扩展方向（可选）。

---

## 🎯 一表总览：已实现 vs 待做

| 阶段 | 已实现 | 待做 |
|------|--------|------|
| **v1** | 5 项（环境变量、批处理复核、时区、Logging、物理归档） | 1 项（数据清洗与标注扩展，可选） |
| **v1.5** | 6 项（配置集中、工具抽取、决策分离、流程重构、main.py、基础指标） | 0 项 |
| **v2** | 6 项（13–17、19） | 1 项（#18 模型注册） |
| **v3** | 0 项 | 9 项 |
| **v4** | 0 项 | 3 项（2 项核心 + 1 项可选） |

**合计**：已实现 **17** 项（v1 共 5 + v1.5 共 6 + v2 共 6）；待做 **14** 项（v1 可选 1 + v2 共 1 + v3 共 9 + v4 共 3）。

---

*清单版本：v2026.02 | v2.0 开工 | 与 Roadmap.md 同步*
