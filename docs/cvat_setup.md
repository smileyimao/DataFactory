# CVAT 标注流程

## 唯一推荐：CVAT 原生格式

**教训**：Import Dataset 与 Upload Annotations 是两套逻辑。COCO、LabelMe、Ultralytics YOLO 等格式走 datumaro 解析，坑多。**只用 CVAT for images 1.1 原生格式**，与 CVAT 导出完全一致，Upload 成功率最高。

```bash
# 1. 图片 zip（创建 Task）
python scripts/export_for_cvat.py

# 2. 标注 zip（Upload Annotations）
python scripts/export_for_cvat_native.py --vehicle
```

### 流程

1. **Create task** → Select files → 上传 **for_cvat.zip**
2. 进入 Task → **Upload annotations** → 选择 **CVAT for images 1.1** → 上传 **for_cvat_native.zip**

---

## 演示前预演练

```bash
./scripts/demo_prepare.sh
```

---

## 方式一：API 自动创建 Project Labels（可选）

```bash
export CVAT_URL="https://app.cvat.ai" CVAT_TOKEN="your_token"
python scripts/cvat_setup_labels.py
```

## 方式二：手动添加 Label（可选）

```bash
python scripts/cvat_setup_labels.py --print
```

按输出顺序在 Project → Labels → Add label 中逐个添加。**顺序必须一致**。

---

## 置信度显示

伪标签导出时会在每个 box 上附带 `confidence` 属性。若要在 CVAT 中看到置信度：

- **export_for_cvat_native** 生成的 annotations.xml 已包含 `confidence` 属性定义（meta 中）及每个 box 的 `<attribute name="confidence">0.xx</attribute>`
- 若 Task 来自 Project，且 Project 的 label 未定义 `confidence`，可在 Project → Labels → 编辑对应 label → Add attribute：`confidence`，类型 `Number`，默认 0
