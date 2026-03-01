# Demo 演示脚本：核心逻辑

> **要证明的一件事**：  
> 「没有 pipeline，标注 100 张图需要人工从零画框。有了 pipeline，80% 的框自动生成，人工只需要确认和修改剩下的 20%。」

---

## 五步演示流程

### 第一步：展示原始视频（约 30 秒）

**动作**：播放 dashcam 视频（Sudbury 街道场景）

**话术**：  
「这是真实的 Sudbury 街道行车记录仪视频，有车、行人、各种光线条件——逆光、阴天、夜间。」

**目的**：让对方看到数据来源真实、场景多样。

---

### 第二步：跑 pipeline（约 1 分钟）

**前置**：视频已放入 `storage/test/original/` 或 `storage/raw/`

**命令**：
```bash
./scripts/run_demo_a.sh
# 或分步：
# 1. python scripts/reset_factory.py --execute --target for-test --confirm-dangerous
# 2. cp your_video.MOV storage/raw/
# 3. python main.py --gate 50
# 4. python scripts/export_for_labeling.py --last 1
# 5. python scripts/export_for_cvat.py && python scripts/export_for_cvat_native.py --vehicle
```

**话术**：  
「终端在跑 pipeline：抽帧、QC 过滤模糊过曝、YOLO 生成 pseudo-label、按置信度分流到 refinery 和 inspection，MLflow 记录这个 batch。」

**目的**：展示全自动处理，无需人工干预。

---

### 第三步：打开 MLflow（约 30 秒）

**命令**：
```bash
mlflow ui
# 或若用 db/mlflow.db：mlflow ui --backend-store-uri sqlite:///db/mlflow.db
```

**话术**：  
「这是这个 batch 的记录：处理了多少帧、通过率、pseudo-label 数量。全程可追溯。」

**目的**：证明可追溯性。

---

### 第四步：打开 CVAT（约 2 分钟）

**动作**：进入 Task，翻几张图，按类型举例：

| 类型 | 话术 |
|------|------|
| **框很准的** | 「这张模型识别得很好，人工直接确认就行，不需要改。」 |
| **框有偏差的** | 「这张模型不确定，框位置稍微偏了，人工调整一下。」 |
| **逆光无框的** | 「这张逆光，模型没识别到，但人眼能看到有车。这就是最有价值的困难样本，人工从零标注，专门用来提高模型在强光下的准确率。」 |

**目的**：说明 pseudo-label 减少人工工作量，困难样本被系统识别出来。

---

### 第五步：说出数字（约 30 秒）

**话术**：  
「这段五分钟视频，pipeline 自动处理了约 120 张关键帧，其中约 90 张生成了 pseudo-label，人工只需要确认或微调。剩下约 30 张是困难样本，需要人工标注，但 pipeline 已经帮你找出来了，不需要人工一张一张去翻。整体人工标注工作量减少了约 75%。」

**目的**：用数字总结价值。

---

## 演示前准备清单

- [ ] 视频在 `storage/test/original/` 或 `storage/raw/`
- [ ] `vision.cascade_light_model_path: ""`（数车辆时关闭级联过滤）
- [ ] `./scripts/demo_prepare.sh` 跑过一遍，确认 zip 可导入 CVAT
- [ ] CVAT Task 已创建，for_cvat.zip + for_cvat_native.zip 已上传
- [ ] MLflow 可访问（`mlflow ui`）

---

## 数字说明（可依实际调整）

| 指标 | 示例值 | 来源 |
|------|--------|------|
| 关键帧数 | ~120 张 | 5 分钟视频 × 约 1 帧/秒 |
| 有 pseudo-label | ~90 张 | refinery + inspection 中有 .txt 的帧 |
| 困难样本 | ~30 张 | inspection 中 0 检测或低置信 |
| 工作量减少 | ~75% | 90/120 只需确认，30/120 需从零标 |

*实际比例取决于视频内容。演示前可跑一遍 pipeline，用以下命令统计真实数字：*
```bash
# 有 pseudo-label 的帧数（refinery + inspection 中有 .txt 的）
find storage/archive/Batch_* -name "*.txt" | wc -l
# 总帧数（图片数）
find storage/archive/Batch_* \( -path "*/refinery/*" -o -path "*/inspection/*" \) -name "*.jpg" | wc -l
```
