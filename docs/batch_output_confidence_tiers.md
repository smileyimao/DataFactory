# 按置信区间分类的批次产出结构（草案）

> **目标**：保留 `0_Source_Video` 与 `1_QC`；将「量产」形态从单一 `2_Mass_Production` 改为**按置信区间分类的产出**——高置信=燃料、中间=待人工、低=报废。便于下游按用途消费（燃料直接进生产、待人工进复核/抽检、报废仅审计或丢弃）。

---

## 1. 当前 Batch_xxx 结构（现状）

```
storage/archive/
└── Batch_{batch_id}/
    ├── 0_Source_Video/     # 本批源视频归档（保留）
    ├── 1_QC/               # QC 过程数据：报表、version_info、抽帧/检测结果等（保留）
    └── 2_Mass_Production/  # 当前：所有「放行」产出（合格+复核通过）统一写在此目录
        ├── Normal/
        ├── Warning/
        ├── manifest.json
        └── ...
```

**落盘逻辑现状**：`qc_engine` 产出 `qualified`（自动放行）、`blocked`（待复核）、`auto_reject`（自动拦截）；`reviewer` 对 blocked 做 y/n 后，`to_produce = qualified + review_通过的`，全部交给 `archiver.archive_produced` 写入**同一个** `2_Mass_Production`。

---

## 2. 目标目录命名与含义（草案）

| 目录 | 含义 | 内容来源 |
|------|------|----------|
| **0_Source_Video** | 源视频 | 不变，本批 raw 归档 |
| **1_QC** | 过程数据 | 不变，报表、version_info、智能检测等 |
| **2_高置信_燃料** | 高置信度、直接可用 | 双门槛下 `score >= dual_high` 自动放行的文件；下游直接当「燃料」进生产 |
| **3_待人工** | 中间置信、需人工确认或抽检 | 双门槛下 `dual_low <= score < dual_high` 经复核**通过**的文件；或单门槛下复核通过项。供人工抽检/二次确认后再决定是否晋升为燃料 |
| **4_低置信_报废** | 本批内低置信、仅审计/报废 | 双门槛下 `score < dual_low` 的已进 `rejected_material/Batch_xxx_Fails`，**不在此目录重复落盘**；若业务需要在 Batch 下也留一层「本批低置信」可做 manifest 或软链（可选） |

**说明**：

- **2_高置信_燃料**：仅来自 `qualified`（自动放行），不混入复核通过项。
- **3_待人工**：仅来自「blocked 里复核通过」的项；若希望「待人工」在复核前就有物理目录，可先建空目录或先把 blocked 的副本写入 3，复核通过后再迁到 2（见下文落盘逻辑可选方案）。
- **4_低置信_报废**：低置信当前已写入 `rejected_material/Batch_{batch_id}_Fails`，Batch 下可不建 4，避免重复；若需「按批查看低置信清单」，可在 1_QC 的报表或单独 manifest 中体现，或可选在 Batch 下建 `4_低置信_报废` 仅放 manifest（路径指向 rejected 下的文件）。

---

## 3. 落盘逻辑草案（与现有 pipeline 对齐）

### 3.1 数据流回顾

- **qc_engine** 输出：`qualified`（高置信自动放行）、`blocked`（中间置信待复核）、`auto_reject`（低置信自动拦截）。
- **reviewer** 输出：对 blocked 逐项 y/n，得到 `added_produce`（复核通过）、`review_reject`（复核拒绝）。
- **archiver** 当前：`to_reject` → `archive_rejected`（rejected_material / redundant_archives）；`to_produce` → `archive_produced`（全部写 2_Mass_Production）。

### 3.2 拆分 to_produce 为两档

- **to_fuel** = 原 `qualified`（高置信，自动放行）→ 写 **2_高置信_燃料**。
- **to_human** = 原 `added_produce`（blocked 里复核通过的）→ 写 **3_待人工**。

为此，pipeline 或 archiver 需要能区分「来自 qualified」与「来自 review 通过」：在合并 `to_produce` 时打标（例如每项带 `tier: "fuel" | "human"`），或分别调用两次归档（先归档 qualified → 2，再归档 added_produce → 3）。

### 3.3 path_info 扩展（qc_engine）

在 `path_info` 中增加分层目录，供 archiver 与 production_tools 使用：

```python
# 当前
mass_dir = os.path.join(warehouse, f"Batch_{batch_id}", "2_Mass_Production")

# 草案：改为多个目录
base = os.path.join(warehouse, f"Batch_{batch_id}")
path_info["source_archive_dir"] = os.path.join(base, "0_Source_Video")  # 已有
path_info["qc_dir"] = os.path.join(base, "1_QC")                       # 已有
path_info["fuel_dir"]    = os.path.join(base, "2_高置信_燃料")
path_info["human_dir"]   = os.path.join(base, "3_待人工")
path_info["scrap_dir"]   = os.path.join(base, "4_低置信_报废")          # 可选，空或仅 manifest
# 兼容旧逻辑：path_info["mass_dir"] 可暂时仍指向 fuel_dir 或保留废弃
```

### 3.4 archiver.archive_produced 改造草案

- **入参**：除现有 `to_produce`、`path_info` 外，需要**分档列表**，例如：
  - `to_fuel: List[Dict]` → 写 `path_info["fuel_dir"]`
  - `to_human: List[Dict]` → 写 `path_info["human_dir"]`
- **行为**：
  - 对 `to_fuel`：`run_production(..., target_dir=path_info["fuel_dir"], ...)`，并写入 production_history（同现有）。
  - 对 `to_human`：同上，`target_dir=path_info["human_dir"]`。
  - 若 `to_human` 为空则只建空目录或跳过，不写 3_待人工。
- **兼容**：若配置或开关为「仍用单一 Mass_Production」，则 `fuel_dir` 与 `human_dir` 可指向同一目录，或保留 `mass_dir` 写回 2_Mass_Production，便于分步上线。

### 3.5 production_tools.run_production

- 无需改签名：仍为 `run_production(video_paths, target_dir, batch_id, cfg, ...)`。
- 调用方（archiver）按档传入不同 `target_dir`：第一次 `target_dir=fuel_dir`，第二次 `target_dir=human_dir`。每个目录下仍为现有结构（Normal/、Warning/、manifest.json、报告等）。

### 3.6 pipeline 改动要点

- `run_qc` 返回的 `qualified` 与 `blocked` 在 reviewer 之后：
  - `to_fuel = list(qualified)`（不合并 review 通过的）
  - `added_produce, review_reject = reviewer.review_blocked(...)`
  - `to_human = list(added_produce)`
- 调用 `archiver.archive_rejected(cfg, to_reject, ...)` 不变。
- 调用 `archiver.archive_produced(cfg, to_fuel, path_info, tier="fuel")` 与 `archiver.archive_produced(cfg, to_human, path_info, tier="human")`，或合并为一次调用 `archive_produced(cfg, to_fuel=to_fuel, to_human=to_human, path_info=path_info)`，由 archiver 内部分别落盘。

---

## 4. 配置与兼容（建议）

- **配置项**（示例）：`production_setting.confidence_tiered_output: true/false`。为 `false` 时保持现有行为（所有 to_produce 写 2_Mass_Production）；为 `true` 时按上述 2/3 分档落盘。
- **导出与 labeling**：`engines/labeling_export.py` 当前扫描 `2_Mass_Production` 与 `1_QC`；扩展为同时扫描 `2_高置信_燃料`、`3_待人工`（及可选的 `4_低置信_报废`），或通过配置指定「参与 manifest 的子目录列表」。
- **滚动清理**：若启用 `rolling_cleanup.archive_retention_days`，仍按 `Batch_*` 整目录清理，无需按子目录区分。

---

## 5. 实施顺序建议

1. **只改命名与文档**：在 Roadmap 与本文档中固定「2_高置信_燃料、3_待人工、4_低置信_报废」的命名与含义；代码仍写 2_Mass_Production，或先增加 `path_info` 中的 `fuel_dir`/`human_dir` 但暂未使用。
2. **迭代实现**：在 qc_engine 中写入 `path_info["fuel_dir"]`/`path_info["human_dir"]`；pipeline 拆分 to_fuel / to_human；archiver 支持分档写入；production_tools 保持按 target_dir 写入；最后打开 `confidence_tiered_output` 配置并更新 labeling_export。

---

## 6. 小结表

| 置信区间 | 当前落盘 | 目标落盘 |
|----------|----------|----------|
| 高（自动放行） | 2_Mass_Production | **2_高置信_燃料** |
| 中（复核通过） | 2_Mass_Production | **3_待人工** |
| 低（自动拦截） | rejected_material/Batch_xxx_Fails | 不变（可选 Batch 下 4_低置信_报废 仅 manifest） |
| 重复 | redundant_archives | 不变 |

*文档版本：草案 v1 | 与 Roadmap「按置信区间导出/重命名批次产出结构」对齐*
