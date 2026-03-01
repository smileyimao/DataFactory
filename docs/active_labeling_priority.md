# 主动学习：标注优先级设计

> **目标**：时间紧时优先标对模型更有用的图，时间松再处理次要图；迭代循环直至达到满意精度。

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **主动学习** | 优先标模型最不确定、边际收益最大的样本 |
| **两阶段筛选** | 先按 confidence 分层，再在中间态内按 QC + confidence 排序 |
| **迭代闭环** | 标注 → 回传并入 → 重训 → 再跑 pipeline → 精度满意则停 |

---

## 2. 价值分层

### 2.1 按 Confidence 分层（已有）

| 来源 | 含义 | 标注价值 |
|------|------|----------|
| **inspection** | YOLO 置信度低或未检测 | **高**：模型不确定，修正后收益大 |
| **refinery** | YOLO 置信度高 | 中：多为简单样本，可少量标 |
| **Warning 帧** | 质量异常（jitter、black、blur 等） | **高**：边缘场景，利于鲁棒性 |

### 2.2 中间态：confidence 越低价值越高

- inspection 内：**confidence 越低** → 模型越不确定 → 修正后收益越大
- 结合 QC：**低 confidence + QC 异常**（jitter、black、blur）→ 最高优先级

### 2.3 QC 异常帧的价值

| QC 类型 | 含义 | 价值（画面可辨时） |
|---------|------|-------------------|
| jitter | 抖动/轻微模糊 | 高：真实场景常有，利于鲁棒性 |
| black | 偏暗 | 高：夜间/逆光等低照度 |
| blur | 模糊 | 高：运动模糊、镜头虚化 |
| brightness | 过曝/过暗 | 高：极端光照 |

**原则**：只要画面还能辨出目标，就有标注价值；完全看不清则丢弃。

---

## 3. 优先级排序公式

```
优先级分数 = f(1 - max_confidence, QC_异常权重)
```

- **max_confidence**：该帧 YOLO 最高检测置信度（无检测时视为 0）
- **QC 异常**：有 jitter/black/blur/brightness 等则加分
- **排序**：分数越高越优先

**简化实现**：
1. 先按 `subdir` 分：inspection 优先于 refinery
2. 再按 `max_confidence` 升序：低置信优先
3. 再按 QC 异常：有 Warning 的优先

---

## 4. 数据流与实现要点

### 4.1 当前已有

- **confidence 分流**：`approved_split_confidence_threshold`，高→refinery 低→inspection
- **manifest 字段**：`batch_id`、`filename`、`subdir`（refinery/inspection）
- **skip_empty_labels**：并入训练集时丢弃无标注图（相似帧未标）

### 4.2 待扩展（TODO）

| 组件 | 扩展内容 |
|------|----------|
| **production_tools** | 写 manifest 时附带 `max_confidence`、`qc_env`（Normal/Warning） |
| **labeling_export** | manifest 含 `max_confidence`、`qc_env`；export 时可选 `--sort-by-priority` 按优先级排序 |
| **export_for_cvat** | 从 manifest 读取优先级字段，生成 `manifest_for_labeling.json` 时按优先级排序；或生成 `priority_order.txt` 供 CVAT 侧参考 |

### 4.3 配置项（预留）

```yaml
labeling_export:
  sort_by_priority: true    # 导出时按优先级排序
  priority_inspection_first: true  # inspection 优先于 refinery
  priority_low_conf_first: true    # 低置信优先
  priority_qc_warning_bonus: true  # QC Warning 加分
```

---

## 5. 标注策略（人工侧）

| 时间 | 策略 |
|------|------|
| **紧** | 优先标：低 confidence + QC 异常（jitter、black 等） |
| **松** | 再标 refinery 高置信、正常光照等 |
| **相似帧** | 跳过，`skip_empty_labels` 会在回传时自动丢弃 |

---

## 6. 迭代闭环

```
标注高价值图 → 回传并入训练集 → 重训/微调模型 → 再跑 pipeline
     ↑                                              ↓
     └──────────── 精度满意？否 → 继续 ──────────────┘
```

---

## 7. 与现有能力的关系

| 现有能力 | 与本设计关系 |
|----------|--------------|
| confidence_tiered_output | 提供 refinery/inspection 分层 |
| skip_empty_labels | 自动丢弃未标相似帧 |
| manifest_for_labeling | 待扩展 max_confidence、qc_env |
| export_for_cvat | 待支持按优先级排序导出 |

---

*文档版本：v1 | 2026-02-26 | 与 optimization_log、Roadmap 对齐*
