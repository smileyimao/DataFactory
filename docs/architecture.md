# DataFactory 架构总览

工业视频质检流水线：**原始素材 → 质检（重复检测 + 不合格检测）→ 人工复核 → 归档**。架构按「流程 + 工具 + 决策 + 配置」分层，便于扩展与维护。

---

## 一、数据流（主流程）

```
storage/raw (原材料)
    → Ingest（准入/凑批）
    → QC Engine（指纹、质量检测、查重）
    → 邮件汇总 + Reviewer（人工 y/n/all/none）
    → Archiver（合格 → storage/archive | 废片 → storage/rejected | 重复 → storage/redundant）
    → DB 记录
```

- **单次运行**：`python main.py` — 扫一次 `storage/raw`，跑完整流程。
- **Guard 模式**：`python main.py --guard` — 监控 `storage/raw`，凑批后自动送厂。

---

## 二、目录与分层

| 层级 | 目录 | 职责 |
|------|------|------|
| **入口** | `main.py` | 总开关：set_base_dir → init_storage_structure → load_config → init_db → pipeline / guard |
| **流程** | `core/` | 编排：ingest → qc_engine → reviewer → archiver；guard 监控 |
| **工具** | `engines/` | 纯工具：quality_tools、fingerprinter、db_tools、report_tools、production_tools、notifier、file_tools |
| **配置** | `config/` | settings.yaml、config_loader（路径解析与 init_storage_structure）、logging |
| **存储** | `storage/` | raw / archive / rejected / redundant / test / reports |
| **数据库** | `db/` | factory_admin.db（生产历史、指纹、sync_id 预留） |
| **文档** | `docs/` | 架构与配置说明、Roadmap |

原则：**工具只干活不决策，决策在 core（qc_engine / reviewer），配置只存不判。**

---

## 三、关键文档索引

- **[architecture_mapping.md](architecture_mapping.md)** — 现状到目标架构的映射表、流程/工具/决策/配置归属、迁移优先级与目标目录结构。
- **[architecture_thinking.md](architecture_thinking.md)** — 架构进阶：依赖注入、接口/协议、状态机、事件驱动、配置验证、错误处理等可选增强。
- **[Roadmap.md](Roadmap.md)** — 版本规划与 v2.x 预留（sync_id、人机冲突 Conflict）。
- **[implementation_checklist.md](implementation_checklist.md)** — 实现与自检清单。

---

## 四、v1.x 与 v2.x

- **v1.x**：集中质检 + 复核 + 物理归档；存储与 DB 已归拢（v1.6）。
- **v2.x**：多模态时间戳对齐（sync_id）、人机冲突标签（Conflict）已在 db_tools / quality_tools 预留扩展点。

变更记录见根目录 `CHANGELOG.md`。
