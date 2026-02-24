# 1_QC 已移除 · 燃料伪标签 · 待人工预画框

## 1_QC 已移除

自本实现起，**不再创建 `Batch_xxx/1_QC`**。抽检在临时目录进行，读完 manifest 即删；报告写入 **`Batch_xxx/reports/`**（工业报表、智能检测报告、version_info）。pipeline 目标为：产出**可直接给模型用的燃料**（带伪标签），以及**需人工标注的待人工**（带预画框，人只确认）。

---

## 燃料自动伪标签（已实现）

- **refinery**：写图时同时写**同名 YOLO .txt**（`class_id x_center y_center w h` 归一化），由 archiver 对 to_fuel 按 1 秒间隔跑 vision，将 `detections_by_video` 传给 production_tools，写图即写伪标签。
- **inspection**：同样带**预画框**（同名 .txt），便于导入标注工具后**人只需点确认**。

---

## 待人工：预画框 + 人只确认

- **inspection** 下已有图及同名 **.txt**（YOLO 格式），即「模型先画好的框」。
- 导入 **Label Studio / CVAT** 等时：选择「导入预标注」或「从 YOLO .txt 加载」，即可在界面上看到已画好的框，**人工只做确认/微调**，无需从零画框，减少标注工作量。
- 若需把待人工导出到统一目录：可将 `inspection` 或指定批次下的图 + .txt 拷贝到 **`storage/for_labeling`**，并用 `scripts/export_for_labeling.py` 生成 manifest；标注工具指向 for_labeling 并启用「预标注」即可。

**结论**：能做到「给人工直接画好框，人只需要点一下确认」——通过 inspection 内同名的 YOLO .txt 作为预标注，在标注工具中加载即可。
