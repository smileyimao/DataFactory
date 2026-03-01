# Demo 流程梳理：A 训练 → B 验证

> 找人聊时的价值主张：见 **docs/demo_pitch.md**（为什么招 IE 背景会 pipeline 的人）

## 数据流

```
raw (A 视频) → pipeline → QC 分流
                           ├── refinery（高置信，有伪标签）
                           └── inspection（低置信，待人工标）
                                    ↓
                    export_for_labeling 从 archive 导出
                                    ↓
                    for_labeling/images（refinery + inspection）
                                    ↓
                    export_for_cvat + export_for_cvat_native → for_cvat.zip + for_cvat_native.zip
                                    ↓
                    CVAT 上传 → 人工标注 → 回传 → training → retrain
```

## 关键点

| 环节 | 说明 |
|------|------|
| **auto_update_after_batch** | 只追加 **inspection** 到 for_labeling；inspection 为空时不会创建 for_labeling |
| **export_for_labeling** | 从 **archive** 扫描 refinery + inspection，生成 for_labeling/images，**必须执行** |
| **顺序** | 先 `export_for_labeling`，再 `export_for_cvat` + `export_for_cvat_native` |

## 当全部进 refinery（0 inspection）时

- `auto_update_after_batch` 不写入任何内容
- 必须跑 `export_for_labeling` 从 archive 导出 refinery 到 for_labeling
- refinery 有伪标签，可导入 CVAT 做确认/微调，不必从零画框

## 一键脚本（run_demo_a.sh）已包含

```
[4/5] export_for_labeling --last 1   ← 从 archive 导出
[5/5] export_for_cvat + export_for_cvat_native  ← 打包图片 zip + 标注 zip
```

## 你当前状态（已跑完 pipeline，archive 有数据）

直接补跑：

```bash
python scripts/export_for_labeling.py --last 1
python scripts/export_for_cvat.py && python scripts/export_for_cvat_native.py --vehicle
```

即可生成 for_cvat.zip + for_cvat_native.zip，无需重跑 pipeline。
