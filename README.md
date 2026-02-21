# DataFactory

工业视频质检流水线：**原始素材 → 质检（重复检测 + 不合格检测）→ 人工复核 → 归档**（合格/废片/冗余）。面向 v2.x 多模态与 MLOps 预留扩展。

---

## 快速启动

**环境**：仅需 Python 3.9+ 与 pip，无需 Conda。推荐在项目下建 venv：

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 编辑 .env 填入邮件等敏感配置（可选）

# 单次运行：从 storage/raw 扫描视频，走完整流程
python main.py

# 可选参数
python main.py --gate 85             # 准入门槛 85%
python main.py --guard              # Guard 模式：持续监控 storage/raw，新视频落地即凑批送厂（Watchdog 事件驱动）
```

首次运行会自动创建 `storage/`、`db/` 目录结构；报告副本写入 `storage/reports/`。

**运维脚本**：`python scripts/reset_factory.py` 清理测试目录（默认 --dry-run）；`python scripts/export_for_labeling.py` 导出合格批次为待标注清单；`python scripts/smoke_test.py` 冒烟测试（生成测试物料 + 跑 QC + 断言）。

---

## 2.0 之前版本特性总览

当前代码已完成 **Roadmap 阶段一 (v1.x)** 与 **阶段一点五 (v1.5)**，并包含 **v1.6 地基加固** 及两项可选收尾（基础指标完整化、数据清洗与标注扩展）。v2.x 尚未开发。

### 阶段一 (v1.x) — 标准化与精细化生产

| 特性 | 说明 |
|------|------|
| **环境变量管理** | 敏感信息（邮件密码等）放入 `.env`，不写进配置与代码。 |
| **批处理复核流水线** | 一批物料先全部做完质检与查重，再发**一封汇总邮件**，仅对「被拦」项做逐条 y/n/all/none 复核。 |
| **多伦多时区** | 日志、邮件、DB、batch_id 统一使用 America/Toronto。 |
| **工业级 Logging** | `logs/factory_YYYY-MM-DD.log`，格式 `[时间][级别][模块]`，记录指纹、查重、得分、厂长决策、移动路径、超时熔断等。 |
| **物理隔离归档** | 废片 → `storage/rejected/Batch_xxx_Fails/`（`原名_得分pts.后缀`）；冗余 → `storage/redundant/`；合格 → `storage/archive/` 并写 DB。 |
| **数据清洗与标注扩展** | 可选：`scripts/export_for_labeling.py` 扫描 `storage/archive` 生成 `storage/for_labeling/manifest_for_labeling.json`，供 Label Studio / CVAT 等导入，为 ML 标注做准备。 |

### 阶段一点五 (v1.5) — 架构重构

| 特性 | 说明 |
|------|------|
| **配置集中化** | 路径、阈值、批处理参数、邮件等全部在 `config/settings.yaml`，由 `config/config_loader.py` 加载并解析为绝对路径。 |
| **工具类抽取** | `engines/`：quality_tools、fingerprinter、db_tools、report_tools、production_tools、notifier、file_tools；工具只返回数值/结果，不做合格与否决策。 |
| **决策与流程分离** | 质检判断在 `core/qc_engine`，复核在 `core/reviewer`，归档在 `core/archiver`；流程编排在 `core/pipeline`。 |
| **入口统一** | `main.py` 单次运行 / `--guard` 监控；行为与 v1.x 一致，旧脚本保留在 `legacy/`。 |
| **基础指标收集** | 批次结束输出：文件数、总大小 (GB)、总耗时、**各阶段耗时**（Ingest / QC / Review / Archive）、**吞吐量**（GB/h、文件/h）；并写入 DB 表 `batch_metrics`，供后续监控与报表。 |

### v1.6 — 地基加固

| 特性 | 说明 |
|------|------|
| **存储与 DB 归拢** | 所有物料与报表在 `storage/`（raw、archive、rejected、redundant、test、reports、for_labeling）；数据库在 `db/factory_admin.db`；启动时 `init_storage_structure()` 自动建目录。 |
| **报表持久化** | 每批 QC 报告与图表额外写入 `storage/reports/`（`{batch_id}_quality_report.html`、`{batch_id}_chart.png`）。 |
| **v2.x 预埋** | DB 表 `production_history` 增加 `sync_id`；`quality_tools` 预留 Conflict 标签扩展点。 |

更细的变更见根目录 **CHANGELOG.md**；Roadmap 与实现清单见 **docs/Roadmap.md**、**docs/implementation_checklist.md**。

---

## 架构索引

| 层级 | 目录 | 说明 |
|------|------|------|
| 入口 | `main.py` | 总开关；单次 / Guard |
| 流程 | `core/` | pipeline → ingest → qc_engine → reviewer → archiver；guard 监控 |
| 工具 | `engines/` | quality_tools, fingerprinter, db_tools, report_tools, production_tools, notifier, file_tools, labeling_export |
| 配置 | `config/` | settings.yaml、config_loader、logging；路径与阈值 |
| 存储 | `storage/` | raw, archive, rejected, redundant, test, reports, for_labeling |
| 数据库 | `db/` | factory_admin.db（production_history、batch_metrics、sync_id 预留） |
| 文档 | `docs/` | Roadmap、架构、配置说明、实现清单 |
| 运维 | `scripts/` | reset_factory、export_for_labeling、smoke_test |
| 旧脚本 | `legacy/` | main_factory、factory_guard 等，兼容参考 |

详见 **docs/architecture.md**、**docs/settings_guide.md**；根目录 **ROOT_LAYOUT.md** 为目录结构说明。

---

## 项目定位与后续

- **v1.x / v1.5 / v1.6**：集中质检 + 复核 + 物理归档 + 指标落库 + 标注导出扩展；2.0 之前规划项已全部完成。
- **v2.x**：视觉感知（YOLO 等）、MLflow、双门槛准入、不合格检测可扩展等；见 **docs/Roadmap.md**。

变更记录见 **CHANGELOG.md**。
