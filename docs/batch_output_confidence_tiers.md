# 批次产出结构（reports / source / refinery / inspection）

> **目标**：每批 Batch 目录仅含四类子目录——`reports`、`source`、`refinery`、`inspection`。便于下游按用途消费（refinery 直接反哺模型、inspection 进复核/抽检）。

---

## 1. Batch_xxx 目录结构（当前）

```
storage/archive/
└── Batch_{batch_id}/
    ├── reports/      # 质量报告、工业报表、智能检测报告、version_info
    ├── source/       # 本批源视频归档
    ├── refinery/     # 高置信燃料：manifest + 图 + .txt 伪标签，直接反哺模型
    └── inspection/   # 待人工：manifest + 图 + .txt，供复核/抽检
```

**落盘逻辑**：`qc_engine` 产出 `qualified`（自动放行）、`blocked`（待复核）、`auto_reject`（自动拦截）；`reviewer` 对 blocked 做 y/n 后，`to_fuel` → refinery，`to_human` → inspection。

---

## 2. 目录命名与含义

| 目录 | 含义 | 内容来源 |
|------|------|----------|
| **reports** | 报告与元数据 | 质量报告、工业报表、智能检测报告、version_info.json |
| **source** | 源视频 | 本批 raw 归档 |
| **refinery** | 高置信燃料 | 双门槛下 `score >= dual_high` 自动放行；平铺 manifest+图+txt，直接反哺模型 |
| **inspection** | 待人工 | 双门槛下 `dual_low <= score < dual_high` 经复核**通过**；供人工抽检/二次确认 |

**说明**：

- **refinery**：仅来自 `qualified`（自动放行），不混入复核通过项。目录平铺（无 Normal/Warning），只含 manifest.json + 图 + .txt 伪标签，无报告。
- **inspection**：仅来自「blocked 里复核通过」的项；按 `human_review_flat` 决定是否平铺。

---

## 3. 落盘逻辑草案（与现有 pipeline 对齐）

### 3.1 数据流回顾

- **qc_engine** 输出：`qualified`（高置信自动放行）、`blocked`（中间置信待复核）、`auto_reject`（低置信自动拦截）。
- **reviewer** 输出：对 blocked 逐项 y/n，得到 `added_produce`（复核通过）、`review_reject`（复核拒绝）。
- **archiver** 当前：`to_reject` → `archive_rejected`（rejected_material / redundant_archives）；`to_produce` → `archive_produced`（全部写 2_Mass_Production）。

### 3.2 拆分 to_produce 为两档

- **to_fuel** = 原 `qualified`（高置信，自动放行）→ 写 **refinery**。
- **to_human** = 原 `added_produce`（blocked 里复核通过的）→ 写 **inspection**。

为此，pipeline 或 archiver 需要能区分「来自 qualified」与「来自 review 通过」：在合并 `to_produce` 时打标（例如每项带 `tier: "fuel" | "human"`），或分别调用两次归档（先归档 qualified → 2，再归档 added_produce → 3）。

### 3.3 path_info 扩展（qc_engine）

在 `path_info` 中增加分层目录，供 archiver 与 production_tools 使用：

```python
base = os.path.join(warehouse, f"Batch_{batch_id}")
path_info["qc_dir"] = os.path.join(base, "reports")
path_info["source_archive_dir"] = os.path.join(base, "source")
path_info["fuel_dir"] = path_info["mass_dir"] = os.path.join(base, "refinery")
path_info["human_dir"] = os.path.join(base, "inspection")
```

### 3.4 archiver.archive_produced 改造草案

- **入参**：除现有 `to_produce`、`path_info` 外，需要**分档列表**，例如：
  - `to_fuel: List[Dict]` → 写 `path_info["fuel_dir"]`
  - `to_human: List[Dict]` → 写 `path_info["human_dir"]`
- **行为**：
  - 对 `to_fuel`：`run_production(..., target_dir=path_info["fuel_dir"], ...)`，并写入 production_history（同现有）。
  - 对 `to_human`：同上，`target_dir=path_info["human_dir"]`。
  - 若 `to_human` 为空则只建空目录或跳过，不写 inspection。
- **兼容**：`confidence_tiered_output=false` 时，全部写 refinery。

### 3.5 production_tools.run_production

- 调用方（archiver）按档传入不同 `target_dir`：`target_dir=fuel_dir` 或 `target_dir=human_dir`。
- **refinery**：`use_flat_output=True`、`skip_html_report=True`。平铺结构，无 Normal/Warning 子目录，无 quality_report.html、warning_list.json；仅保留 manifest.json + 图 + .txt 伪标签，直接反哺模型。
- **inspection**：按 `human_review_flat` 配置决定是否平铺；保留 manifest、warning_list、HTML 报告。

### 3.6 pipeline 改动要点

- `run_qc` 返回的 `qualified` 与 `blocked` 在 reviewer 之后：
  - `to_fuel = list(qualified)`（不合并 review 通过的）
  - `added_produce, review_reject = reviewer.review_blocked(...)`
  - `to_human = list(added_produce)`
- 调用 `archiver.archive_rejected(cfg, to_reject, ...)` 不变。
- 调用 `archiver.archive_produced(cfg, to_fuel, path_info, tier="fuel")` 与 `archiver.archive_produced(cfg, to_human, path_info, tier="human")`，或合并为一次调用 `archive_produced(cfg, to_fuel=to_fuel, to_human=to_human, path_info=path_info)`，由 archiver 内部分别落盘。

---

## 4. 配置与兼容（建议）

- **配置项**：`production_setting.confidence_tiered_output: true/false`。为 `false` 时全部写 refinery；为 `true` 时分档落盘 refinery / inspection。
- **导出与 labeling**：`engines/labeling_export.py` 扫描 `refinery`、`inspection`、`source`（兼容旧版 2_高置信_燃料、3_待人工、2_Mass_Production）。
- **滚动清理**：若启用 `rolling_cleanup.archive_retention_days`，仍按 `Batch_*` 整目录清理，无需按子目录区分。

---

## 5. 实施顺序建议

1. 已实现：Batch 目录仅含 reports、source、refinery、inspection。
2. qc_engine 写入 path_info；archiver 分档写入 refinery / inspection；labeling_export 扫描新目录并兼容旧版。

---

## 6. 小结表

| 置信区间 | 落盘目录 |
|----------|----------|
| 高（自动放行） | **refinery** |
| 中（复核通过） | **inspection** |
| 低（自动拦截） | rejected_material/Batch_xxx_Fails |
| 重复 | redundant_archives |

*文档版本：v2 | Batch 目录：reports / source / refinery / inspection | 路径解耦见 docs/path_decoupling.md*
