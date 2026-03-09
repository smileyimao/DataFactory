# DataFactory 架构总览

工业视频质检流水线：**原始素材 → 质检（重复检测 + 不合格检测）→ 人工复核 → 归档**。架构按「流程 + 工具 + 决策 + 配置」分层，便于扩展与维护。

---

## 一、数据流（主流程）

```
storage/raw (原材料)
    → Ingest（准入/凑批）
    → QC Engine（指纹、质量检测、查重）
    → 邮件汇总 + Reviewer（人工 y/n/all/none）
    → Archiver（合格 → storage/archive | 废片 → storage/rejected/qc_fail | 重复 → storage/rejected/duplicate）
    → DB 记录
```

- **单次运行**：`python main.py` — 扫一次 `storage/raw`，跑完整流程。
- **Guard 模式**：`python main.py --guard` — 监控 raw 目录，凑批后自动送厂；双通道检测 + 产线期间新物料登记。

---

## 二、Guard 模式巡逻逻辑（必读）

Guard 模式下保安持续巡逻 raw 目录，发现新视频即凑批送厂。**循环逻辑**如下，避免漏检与冲突：

### 1. 双通道检测

| 通道 | 机制 | 说明 |
|------|------|------|
| **Watchdog** | 文件系统事件（创建/移入） | 新文件落地即触发，等写入稳定 + `batch_wait_seconds` 后凑批 |
| **轮询兜底** | 每 `poll_interval_seconds` 秒扫一次 raw | macOS 上 Finder 复制、iCloud 同步等可能漏检，轮询可兜底 |

两者并行：Watchdog 漏检时，轮询最多延迟一个间隔即可发现。

### 2. 产线加工期间新视频

当产线正在加工（QC / 复核 / 归档）时，若有新视频写入 raw：

- Timer 或轮询触发 `_flush_batch`，发现 `_processing=True`，则**不立即处理**，而是设置 `_pending_flush=True`
- 本批加工结束后，`finally` 中检查 `_pending_flush`，若为 True 则**立即再扫一次 raw**，把加工期间写入的新视频送厂

这样既不会与当前批次冲突，也不会漏掉新物料。

### 3. 流程小结

```
开机 → startup_scan（存量视频先送厂）
     → 启动 Watchdog + 轮询线程
     → 循环：
         - Watchdog 事件 → 等稳定 → 重置 Timer → Timer 到期 → _flush_batch
         - 轮询线程每 N 秒 → _flush_batch
         - _flush_batch：若加工中则 _pending_flush=True；否则取 paths 送厂
         - 送厂结束：若 _pending_flush 则立即再扫
```

---

## 三、目录与分层

| 层级 | 目录 | 职责 |
|------|------|------|
| **入口** | `main.py` | 总开关：set_base_dir → init_storage_structure → load_config → init_db → pipeline / guard |
| **流程** | `core/` | 编排：ingest → qc_engine → reviewer → archiver；guard 监控 |
| **工具** | `engines/` | 纯工具：quality_tools、fingerprinter、db_tools、report_tools、production_tools、notifier、file_tools、retry_utils（move/copy 重试）、labeled_return |
| **配置** | `config/` | settings.yaml、config_loader（路径解析与 init_storage_structure）、logging |
| **存储** | `storage/` | raw / archive / rejected / redundant / test / reports / for_labeling / labeled_return / training；Batch 内 reports/source/refinery/inspection/labeled |
| **数据库** | `db/` | factory_admin.db（生产历史、指纹）；mlflow.db（MLflow 实验，tracking_uri 默认） |
| **文档** | `docs/` | 架构与配置说明、Roadmap |

原则：**工具只干活不决策，决策在 core（qc_engine / reviewer），配置只存不判。**

---

## 四、关键文档索引

- **[architecture_thinking.md](architecture_thinking.md)** — 架构进阶：依赖注入、接口/协议、状态机、事件驱动、配置验证、错误处理等可选增强。
- **[Roadmap.md](Roadmap.md)** — 版本规划；v3 Auto-modality routing、Backward Compatibility；v4 Temporal Sync、Resource Locking。
- **[active_labeling_priority.md](active_labeling_priority.md)** — 主动学习标注优先级：时间紧优先标低 confidence + QC 异常；迭代闭环直至精度满意。

---

## 五、v1.x 与 v2.x

- **v1.x**：集中质检 + 复核 + 物理归档；存储与 DB 已归拢（v1.6）。
- **v2.x**：多模态时间戳对齐（sync_id）、人机冲突标签（Conflict）已在 db_tools / quality_tools 预留扩展点。

变更记录见根目录 `CHANGELOG.md`。
