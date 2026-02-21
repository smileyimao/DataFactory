# 📐 DataFactory 现状 → 目标架构映射表

> **目的**：将现有「平铺、职责混乱」的代码结构，映射到「流程 + 工具 + 决策 + 配置」的清晰架构。

---

## 🗺️ 映射总览

| 现状文件 | 主要职责 | → 目标架构归属 | 迁移建议 |
|---------|---------|---------------|---------|
| `main_factory.py` | 主流程 + 邮件 + 复核决策 + 路径配置 | **流程**（Ingest/QC/Review/Archive）+ **工具**（邮件）+ **决策**（复核逻辑）+ **配置**（路径） | 拆分到 `core/` + `engines/` + `config/` |
| `factory_guard.py` | 监控流程 + 文件工具 + 批处理决策 | **流程**（监控/启动扫描）+ **工具**（文件检测）+ **决策**（批触发） | 拆分到 `core/` + `engines/` |
| `core_engine.py` | 质检工具 + 报告工具 + 质检决策 + 配置加载 | **工具**（质检传感器/报告生成）+ **决策**（质检判断）+ **配置**（阈值） | 拆分到 `engines/` + `config/` |
| `db_manager.py` | 数据库工具（指纹/查重/记录） | **工具**（纯工具，无决策） | → `engines/fingerprinter.py` + `engines/db_tools.py` |
| `log_setup.py` | 日志工具 | **工具** | → `engines/logger.py` 或保留在根目录 |
| `factory_config.yaml` | 配置中心 | **配置** | → `config/settings.yaml` |
| `.env` | 敏感配置 | **配置** | → `config/.env`（已对） |

---

## 📋 详细映射（按「流程/工具/决策/配置」分类）

### 🔄 **流程层 (Process / Orchestration)** → `core/`

| 现状代码位置 | 功能 | → 目标文件 | 说明 |
|------------|------|-----------|------|
| `main_factory.py::run_smart_factory()` | **主流程编排**：Ingest → QC → Review → Archive | `core/ingest.py`<br>`core/qc_engine.py`<br>`core/reviewer.py`<br>`core/archiver.py` | 按流程阶段拆分，每个文件只负责「先做什么、后做什么」，不关心具体算法 |
| `factory_guard.py::startup_scan()` | **启动扫描流程** | `core/ingest.py`（或 `core/startup.py`） | 属于 Ingest 的一部分 |
| `factory_guard.py::VideoFolderHandler` | **监控流程**：文件落地 → 等待稳定 → 批处理触发 | `core/ingest.py`（监控部分） | 属于 Ingest 的「持续监控」模式 |
| `main_factory.py::run_smart_factory()` 里的「试制车间」逻辑 | **试制流程**（目标架构中移除） | ❌ **删除或简化** | 按 Roadmap，试制环节不再必要，raw 直接进 QC |

---

### 🛠️ **工具层 (Tools / Engines)** → `engines/`

| 现状代码位置 | 功能 | → 目标文件 | 说明 |
|------------|------|-----------|------|
| `core_engine.py::qc_sensor()` | **质检传感器**：blur/brightness/jitter 检测 | `engines/quality_tools.py` | 只干活，不决策；返回数值，不返回「合格/不合格」 |
| `core_engine.py::generate_json_manifest()` | **清单生成工具** | `engines/report_tools.py` | 纯工具 |
| `core_engine.py::generate_html_report()` | **HTML 报告生成工具** | `engines/report_tools.py` | 纯工具 |
| `core_engine.py::_get_plot_base64()` | **绘图工具** | `engines/report_tools.py` | 纯工具 |
| `db_manager.py::get_file_md5()` | **指纹生成工具** | `engines/fingerprinter.py` | MD5/内容哈希，纯工具 |
| `db_manager.py::check_reproduce()`<br>`db_manager.py::get_reproduce_info()` | **查重工具**（DB 查询） | `engines/db_tools.py` | 只查，不决策 |
| `db_manager.py::record_production()` | **记录工具**（DB 写入） | `engines/db_tools.py` | 只写，不决策 |
| `main_factory.py::_send_mail()` | **邮件发送工具** | `engines/notifier.py` | 纯工具 |
| `factory_guard.py::_wait_file_stable()` | **文件稳定性检测工具** | `engines/file_tools.py` | 纯工具 |
| `factory_guard.py::_list_video_paths()` | **路径列表工具** | `engines/file_tools.py` | 纯工具 |
| `log_setup.py::setup_logging()` | **日志初始化工具** | `engines/logger.py` 或保留在根目录 | 纯工具 |
| `core_engine.py::start_production()` | **生产工具**（抽帧/保存图片） | `engines/production_tools.py` | 实际是「质检执行器」，调用 `quality_tools` 并保存结果 |

**未来扩展（v2/v3）：**
- `engines/vision_detector.py`：YOLO 检测器（v2）
- `engines/lidar_tools.py`：LiDAR 点云质量检查（v3）
- `engines/labeling_export.py`：导出到 Label Studio / CVAT（v3）

---

### 🎯 **决策层 (Decision / Rules)** → `core/` 或 `rules/`

| 现状代码位置 | 功能 | → 目标文件 | 说明 |
|------------|------|-----------|------|
| `core_engine.py::qc_sensor()` 里的 `if results['br'] < cfg['min_brightness']` 等 | **质检判断逻辑**：根据工具输出 + 阈值决定「Too Dark/Blurry/Normal」 | `core/qc_engine.py` 或 `rules/quality_rules.py` | **关键**：工具只返回数值，决策层根据配置阈值做判断 |
| `main_factory.py::run_smart_factory()` 里的 `passed = score >= final_gate` | **准入决策**：根据得分 + 门槛决定「合格/不合格」 | `core/qc_engine.py` | 决策逻辑 |
| `main_factory.py::run_smart_factory()` 里的 `is_dup = rep is not None` | **重复判断**：根据查重结果决定「重复/不重复」 | `core/qc_engine.py` | 决策逻辑 |
| `main_factory.py::_ask_review_one()` | **人工复核决策**：y/n/all/none | `core/reviewer.py` | 决策逻辑 |
| `main_factory.py::run_smart_factory()` 里的 `to_produce` / `to_reject` 分类 | **归档决策**：根据复核结果决定「进哪个文件夹」 | `core/archiver.py` | 决策逻辑 |
| `factory_guard.py::VideoFolderHandler::_flush_batch()` | **批处理触发决策**：何时触发批处理 | `core/ingest.py`（监控部分） | 决策逻辑 |

---

### ⚙️ **配置层 (Config)** → `config/`

| 现状代码位置 | 功能 | → 目标文件 | 说明 |
|------------|------|-----------|------|
| `factory_config.yaml` | **质检阈值、生产参数、邮件配置** | `config/settings.yaml` | 统一配置中心 |
| `.env` | **敏感信息**（EMAIL_PASSWORD 等） | `config/.env` | 已对 |
| `main_factory.py` 里的全局路径（INPUT_DIR, WAREHOUSE 等） | **路径配置** | `config/settings.yaml`（paths 节） | 集中管理 |
| `factory_guard.py::BATCH_WAIT_SECONDS` | **批处理参数** | `config/settings.yaml`（ingest 节） | 集中管理 |
| `core_engine.py::DataMachine.config` | **质检阈值默认值** | `config/settings.yaml`（quality_thresholds 节） | 集中管理 |
| `core_engine.py::DataMachine.load_config()` | **配置加载逻辑** | `config/config_loader.py` | 统一配置加载器 |

---

## 🎯 关键原则（避免再次混乱）

### ✅ **工具类：只干活，不决策**
- `engines/quality_tools.py`：返回 `{"br": 120.5, "bl": 45.2, "jitter": 12.3}`，**不返回** `"Too Dark"` 或 `"合格"`
- `engines/fingerprinter.py`：返回 MD5 字符串，**不返回** `"重复"` 或 `"不重复"`
- `engines/db_tools.py`：返回查询结果字典，**不返回** `"已存在"` 或 `"不存在"`

### ✅ **决策类：只判断，不干活**
- `core/qc_engine.py`：调用工具 → 读配置 → 做判断 → 返回决策结果（`{"status": "unqualified", "reason": "blur", "score": 45.2}`）
- `core/reviewer.py`：调用工具（邮件） → 读配置（复核超时） → 做判断（y/n/all/none） → 返回决策结果

### ✅ **流程类：只编排，不实现**
- `core/ingest.py`：调用工具（文件扫描） → 调用决策（是否需要批处理） → 调用 QC 引擎
- `core/qc_engine.py`：调用工具（质检/指纹/查重） → 调用决策（合格/不合格/重复） → 返回 QC 结果
- `core/reviewer.py`：调用工具（邮件） → 调用决策（人工复核） → 返回复核结果
- `core/archiver.py`：调用工具（文件移动） → 调用决策（进哪个文件夹） → 执行归档

### ✅ **配置类：只存储，不逻辑**
- `config/settings.yaml`：纯数据，不包含任何 `if/else` 逻辑
- `config/config_loader.py`：只负责「读配置 → 返回字典」，不负责「根据配置做判断」

---

## 🚀 迁移优先级

### **Phase 1：配置集中化**（风险低，收益高）
1. 将所有路径、阈值、参数移到 `config/settings.yaml`
2. 创建 `config/config_loader.py` 统一加载
3. 各文件改为从 `config_loader` 读取，不再硬编码

### **Phase 2：工具类抽取**（风险中，收益高）
1. 创建 `engines/` 目录
2. 将 `core_engine.py::qc_sensor()` → `engines/quality_tools.py`（**去掉判断逻辑，只返回数值**）
3. 将 `db_manager.py` → `engines/fingerprinter.py` + `engines/db_tools.py`
4. 将 `main_factory.py::_send_mail()` → `engines/notifier.py`

### **Phase 3：决策类分离**（风险中，收益高）
1. 在 `core/qc_engine.py` 中实现决策逻辑：调用 `quality_tools` → 读配置 → 判断
2. 在 `core/reviewer.py` 中实现复核决策：调用 `notifier` → 读配置 → 判断

### **Phase 4：流程类重构**（风险高，收益高）
1. 将 `main_factory.py::run_smart_factory()` 拆分为 `core/ingest.py`、`core/qc_engine.py`、`core/reviewer.py`、`core/archiver.py`
2. 移除「试制车间」逻辑，raw 直接进 QC
3. 将 `factory_guard.py` 的监控逻辑并入 `core/ingest.py`

---

## 📝 迁移后目标结构（参考你画的蓝图）

```
Ad_Data_Processor/
├── config/                    【配置中心】
│   ├── settings.yaml         准入分数、抽帧率、时区、路径、阈值等
│   └── .env                  敏感信息（密钥、密码）
│
├── core/                      【产线编排】Ingest → QC → Review → Archive
│   ├── ingest.py             扫描 raw_video，负责"入场"
│   ├── qc_engine.py          调度质检工具箱，负责"体检"（调用工具 + 决策）
│   ├── reviewer.py           邮件汇总与人工复核交互，负责"审判"
│   └── archiver.py           文件的最终搬运与归档，负责"入库"
│
├── engines/                    【工具类/机器】独立的工具箱，只干活，不决策
│   ├── vision_detector.py    YOLO 专用检测器（未来可换成其他模型）[v2]
│   ├── quality_tools.py      亮度、模糊、抖动等基础质检工具箱
│   ├── fingerprinter.py      MD5/指纹生成工具
│   ├── db_tools.py           数据库工具（查重、记录）
│   ├── notifier.py           邮件/告警通知工具
│   ├── file_tools.py         文件工具（稳定性检测、路径列表）
│   ├── report_tools.py       报告生成工具（JSON/HTML/图表）
│   ├── production_tools.py   生产工具（抽帧/保存）
│   ├── lidar_tools.py        LiDAR 点云质量检查 [v3]
│   └── labeling_export.py    导出到 Label Studio / CVAT [v3]
│
├── storage/                    【物理仓库】真正的文件存放点
│   ├── raw_video/            原料
│   ├── data_warehouse/        合格成品
│   ├── rejected_material/    废品
│   └── redundant_archives/   重复冗余
│
├── logs/                       【黑匣子】生产流水日志
├── db/                         【账本】指纹数据库与元数据记录
│   └── factory_admin.db
│
└── main.py                     【总开关】工厂启动入口
```

---

*文档版本：v2026.02 | 基于「流程 + 工具 + 决策 + 配置」的架构思维*
