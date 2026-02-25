# 测试与审计指南

> 回答三个问题：1) dry run 是什么？2) 每一步怎么运作？3) 哪些是阑尾、哪些是死角？

---

## 一、Dry Run 是什么？

**Dry run = 模拟执行，不产生真实副作用**（不删文件、不写报告、不发邮件、不并入）。

| 脚本 | dry run 行为 |
|------|--------------|
| `reset_factory.py` | 默认 `--dry-run`：只打印「将要删除什么」，不删；加 `--execute` 才真删 |
| `import_labeled_return.py --dry-run` | 只做伪标签对比、打印结果，不写报告、不发邮件、不并入 training |
| `reset_config.py --dry-run` | 只打印「将要备份/覆盖什么」，不写文件 |

**主流程 `main.py` 没有 dry run**：它跑的是真实流程，处理 `storage/raw` 里的真实视频。要「不跑真实数据」只能：
- 把 `paths.raw_video` 指向空目录或测试目录；
- 或用 `python main.py --test`：在**临时目录**里跑全链路，跑完即删，不污染真实 storage/DB。

**自动化测试：** Pipeline 会把 raw 里的视频 move 到 archive/rejected，raw 会被清空。为支持反复测试：
- 用 `python main.py --test`：从 `paths.test_source`（默认 `storage/test/original`）复制到**临时 raw**，在临时环境中跑全链路（Ingest → QC → Review → Archive），邮件照发，退出后临时目录自动清理；
- 测试源 `paths.test_source` 保持不变，pipeline 不改动此目录。

---

## 二、每一步怎么运作？（流程追踪）

### 主流程：`python main.py`

```
main()
  → config_loader.set_base_dir / load_config
  → startup.run_startup_self_check（路径可写性）
  → startup.run_rolling_cleanup（日志/报表过期清理）
  → [可选] startup.run_golden_run（黄金库真跑）
  → db_tools.init_db
  → pipeline.run_smart_factory()
```

### pipeline.run_smart_factory()

```
1. ingest.get_video_paths(cfg)     # 从 paths.raw_video 扫视频
2. qc_engine.run_qc(cfg, videos)   # 质检
3. [若 blocked] reviewer 或 pending_queue
4. archiver.archive_rejected()     # 废片/冗余
5. archiver.archive_produced()     # 燃料/待人工
6. labeling_export.auto_update_after_batch()  # 待标池
7. _batch_summary / _maybe_log_mlflow
```

### qc_engine.run_qc() 内部

```
指纹 → 判重（DB + 本批）→ 抽检（production_tools 临时目录）→ 源归档 source
→ 质量得分 → vision_detector.run_vision_scan（YOLO）→ 双门槛分流
→ 发邮件 → 返回 (qc_archive, qualified, blocked, auto_reject, path_info)
```

### 如何「看到」每一步？

| 方法 | 说明 |
|------|------|
| **日志** | `logs/factory_YYYY-MM-DD.log`，关键步骤有 INFO |
| **打印** | 控制台有「🚀 [指挥部]」「📊 质检结果」「🏭 [阶段 2]」等 |
| **加断点** | 在 `core/pipeline.py`、`core/qc_engine.py` 设 `breakpoint()`，`python -m pdb main.py` |
| **单步脚本** | 写 `scripts/trace_flow.py` 只跑 ingest 或只跑 qc，逐步调用 |

---

## 三、现有测试

**pytest 分层**（推荐）：`pytest tests/ -v -m "not e2e"`

| 目录 | 测试 | 说明 |
|------|------|------|
| `tests/unit/` | test_config_loader, test_quality_tools | 单元：validate_config、decide_env |
| `tests/integration/` | test_dual_gate | 集成：双门槛分流、archiver |
| `tests/e2e/` | test_smoke, test_main_full_pipeline, test_guard | 端到端：QC 全流程、main.py --test 全链路、Guard 模式 |
| `tests/api/` | test_health_metrics | API：/api/health、/api/metrics |

**全链路**：`main.py --test` 在临时环境跑完整 pipeline，邮件照发，不污染真实数据。

**e2e 失败常见原因**：`paths.test_source`（默认 `storage/test/original/`）不存在或缺少 normal.mov 等测试视频。

---

## 四、阑尾与死角审计

### 阑尾（可删或已废弃）

| 模块/文件 | 状态 | 建议 |
|-----------|------|------|
| **legacy/** | 旧入口，已被 core/ + main.py 替代 | 保留作参考，不删；新开发不依赖 |
| `legacy/main_factory.py` | 旧主流程 | 仅兼容参考 |
| `legacy/factory_guard.py` | 旧 Guard | 仅兼容参考 |
| `legacy/core_engine.py` | 旧 DataMachine | 仅兼容参考 |
| `legacy/db_manager.py` | 旧 DB | 已迁入 engines/db_tools + fingerprinter |

### 可能冗余的配置/代码

| 项 | 说明 |
|----|------|
| `production_setting.save_normal` / `save_warning` | 当 `save_only_screened=true` 时，落盘逻辑不同；两者可能冲突，需文档说明 |
| `1_QC` 目录 | 已移除，不再创建 |
| `Batch_xxx/reports` | 工业报表、智能检测报告、version_info 写入此目录 |

### 死角（边缘场景、易漏）

| 场景 | 风险 |
|------|------|
| raw 为空 | main.py 直接 return，无报错 |
| 全部重复 | qc 跳过抽检，manifest 空 |
| vision 模型加载失败 | 邮件会标红，但 QC 仍继续 |
| 邮箱未配置 | notifier 可能静默失败 |
| for_labeling 无 manifest | import_labeled_return 会报错 |
| 双门槛未配置（null） | 回退单门槛 |
| human_review_flat + 旧 Normal/Warning 结构 | labeling_export 已用 os.walk 兼容 |

### 依赖关系简图（谁调谁）

```
main.py
  → pipeline
  → qc_engine, reviewer, archiver, pending_queue
  → production_tools, vision_detector, labeling_export
  → motion_filter, frame_io（vision_detector 内）
  → quality_tools, fingerprinter, db_tools, report_tools, notifier
```

**独立脚本**（不经过 main）：export_for_labeling, import_labeled_return, compare_models, reset_factory, reset_config。

---

## 五、建议的验证顺序

1. **reset_factory dry-run**：`python scripts/reset_factory.py`，看打印是否符合预期
2. **空 raw 跑 main**：`paths.raw_video` 指向空目录，跑 `main.py`，看是否优雅退出
3. **准备 e2e 测试数据**：在 `paths.test_source`（默认 `storage/test/original/`）放 normal.mov 等，跑 `pytest tests/e2e/ -v`
4. **单次真实跑**：放 1–2 个小视频到 raw，跑 `main.py`，观察每步输出
5. **dashboard**：`review.mode=dashboard`，跑 main 后 `python -m dashboard.app`，看队列
6. **import_labeled_return --dry-run**：若有 for_labeling 数据，跑一遍看对比结果

---

*文档版本：v2026.02 | 与 testing_and_audit 对齐*
