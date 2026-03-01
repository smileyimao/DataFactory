# 快速验证 Pipeline 指南（跟人谈之前）

> 目标：用最少步骤验证全流程，拿到可演示的结果。

---

## 一、数据集从哪来（3 选 1）

| 方式 | 耗时 | 适合 |
|------|------|------|
| **A. Roboflow Universe** | 5 分钟 | 矿车/工业场景，直接 YOLO 格式 |
| **B. COCO 子集** | 2 分钟 | 快速验证，有 truck/car 类 |
| **C. 你已有的 Mining truck V1.4** | 0 分钟 | 注意：保持 `train/images` + `train/labels` 结构 |

### A. Roboflow Universe（推荐）

1. 打开 [universe.roboflow.com](https://universe.roboflow.com)，搜索 `mining truck` 或 `truck`
2. 选一个数据集 → Download → 选 **YOLOv8** 格式 → 下载 ZIP
3. 解压后，把 `train/` 整个目录拷到 `storage/raw/`：
   ```bash
   unzip xxx.zip
   cp -r xxx/train storage/raw/
   ```
4. 确保结构是：`storage/raw/train/images/*.jpg` 和 `storage/raw/train/labels/*.txt`

### B. COCO 子集（最快）

```bash
# 用你已有的任意 YOLO 格式小数据集，或从 Roboflow 下个 COCO 子集
# 只要保证：raw/train/images/ + raw/train/labels/ 成对存在
```

### C. 你已有的 Mining truck V1.4

**关键**：必须保持 `images/` 和 `labels/` 同级，否则无检测时找不到原始标注。

```bash
# 正确结构
storage/raw/
  train/
    images/   ← 图
    labels/   ← 同名 .txt
```

---

## 二、验证流程（5 步）

```
1. 清空 → 2. 放入数据 → 3. 跑 pipeline → 4. 看结果 → 5. 导出 CVAT
```

### 1. 清空（避免旧数据干扰）

```bash
python scripts/reset_factory.py --execute
# 或手动清空 storage/raw storage/archive storage/for_labeling
```

### 2. 放入数据

```bash
# 把 train/ 拷到 raw（保持 images+labels 结构）
cp -r /path/to/your/train storage/raw/
```

### 3. 跑 Pipeline

```bash
python main.py --gate 50
# --gate 50 降低门槛，更多放行，便于快速看到 refinery/inspection
```

### 4. 看结果

| 检查项 | 位置 | 预期 |
|--------|------|------|
| 有 Batch | `storage/archive/Batch_*/` | 有 reports、source、refinery、inspection |
| refinery 有图+txt | `archive/Batch_*/refinery/*.jpg` | 高置信的应有 .txt |
| inspection 有图 | `archive/Batch_*/inspection/*.jpg` | 低置信的，部分可能无 .txt |
| for_labeling 有内容 | `storage/for_labeling/images/` | 自动追加了 inspection |

### 5. 导出 CVAT

```bash
python scripts/export_for_cvat.py && python scripts/export_for_cvat_native.py --vehicle
# 生成 for_cvat.zip + for_cvat_native.zip
# 上传到 CVAT：Create task → for_cvat.zip；Upload annotations → CVAT for images 1.1 → for_cvat_native.zip
```

---

## 三、跟人谈时的演示顺序

1. **开场**：这是工业视频/图片的 QC + 归档 + 标注闭环
2. **展示 raw**：`storage/raw/train/` 结构
3. **跑一遍**：`python main.py --gate 50`，看控制台输出
4. **展示 archive**：`Batch_xxx/refinery` vs `inspection`，说明高/低置信分流
5. **展示 for_labeling**：自动进待标池，导出 zip 可导入 CVAT
6. **收尾**：闭环：raw → QC → 分流 → 待标 → CVAT → 回传训练

---

## 四、常见坑

| 问题 | 原因 | 解决 |
|------|------|------|
| 全是 inspection，没 refinery | 模型检测不到（如 COCO 模型看矿车） | 关 cascade：`cascade_light_model_path: ""`；或用矿车模型 |
| 很多图没 .txt | YOLO 无检测 + 原始 labels 没拷进 batch | 放入 raw 时保持 `train/images` + `train/labels` 结构 |
| main.py --test 报错 | --test 只支持视频 | 用真实 run：数据放 raw，直接 `main.py` |
| 想快速不污染 | 用临时目录 | 改 `paths.raw_video` 指向临时目录，跑完删 |
| 图片+视频混合 | auto 会选数量多的，另一类被忽略 | `image_mode: "both"` 或 raw 同时有图+视频时 auto 自动走 both |

---

## 五、最小可演示配置

```yaml
# config/settings.yaml 关键项
ingest:
  image_mode: "auto"   # 有图自动走 image 通路

vision:
  enabled: true
  cascade_light_model_path: ""   # 关 cascade，否则 COCO 模型会过滤掉矿车

production_setting:
  confidence_tiered_output: true
  approved_split_confidence_threshold: 0.6

labeling_pool:
  auto_update_after_batch: true   # 每批 inspection 自动进 for_labeling
```

---

*文档版本：v1 | 快速验证用*
