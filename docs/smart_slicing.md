# 抽帧策略：YOLO 筛查与只落盘关键帧

> 用 YOLO + 质量指标做视频筛查，只把「有物体」或「质量异常」的瞬间写成切片落盘，提高效率、减少傻大粗全量切片。

---

## 1. 背景

- **原策略**：按秒抽帧 → 每帧做质量判定 → 所有 Normal 帧写 Normal/、所有 Warning 帧写 Warning/，全部落盘。
- **问题**：1000 个视频 × 每秒 1 帧 → 体量巨大，且大量是「空场、无目标」的 Normal 帧，标注与训练价值低。

---

## 2. 思路：解码照做，落盘筛选

- **解码（抽帧）**：仍然按秒（或配置间隔）解码，否则无法做质量和 YOLO。
- **落盘**：只把**通过筛查**的帧写成图片 + 同名 .txt：
  - **质量异常**：env ≠ Normal（太暗、模糊、抖动、对比度异常）→ 保留，便于排查与标注；
  - **有目标**：YOLO 在该帧检测到至少一个目标 → 保留，作为训练/标注的高价值瞬间；
  - **Normal 且无检测**：不写盘，只参与 manifest/报告统计（算通过率等）。

这样既保证 QC 通过率等指标完整，又大幅减少磁盘与下游标注量。

---

## 3. 配置与行为

| 配置 | 说明 | 默认 |
|------|------|------|
| `production_setting.save_only_screened` | `true` = 只落盘「Warning 或 有 YOLO 检测」的帧；`false` = 原行为（Normal/Warning 全写） | `false` |

- **QC 阶段**（抽检若干秒）：无 YOLO 检测结果时，`save_only_screened=true` 时只写 **Warning** 帧，Normal 不写盘，manifest/报告仍含全部抽检帧。
- **量产阶段**（refinery / inspection）：有 YOLO 检测结果时，只写 **Warning 或 该帧有检测** 的帧；Normal 且无检测不写盘。

---

## 4. 流程小结

```
视频 → 按秒解码 → 质量分析 + YOLO（量产时）
       → 每帧进 manifest/报告（统计用）
       → 仅当 save_only_screened 且 (Warning 或 有检测) 时才写 图片 + .txt 落盘
```

效果：大批量视频时，落盘量明显下降，只保留「关键瞬间」切片，便于快速找到想要的片段并减轻标注负担。

---

## 5. 进阶：解码与检测阶段提效（业界四板斧）

当前「只落盘关键帧」仍是对**已解码、已跑完 YOLO** 的帧做筛选；以下四项可进一步减少**解码与 GPU 计算量**：

1. **I-帧优先** ✅：`vision.use_i_frame_only=true`，只解 I-帧做检测，需 ffprobe。
2. **运动唤醒** ✅：`vision.motion_threshold`，帧差低于阈值不跑 YOLO，0=关闭。
3. **Embedding + 向量库**：待做，对关键帧提向量，存 Milvus/Faiss。
4. **级联检测** ✅：`vision.cascade_light_model_path`，轻量模型初筛，有东西才上主模型。

详见 **docs/Roadmap.md** 中「高效筛查技术线（业界四板斧）」一节。
