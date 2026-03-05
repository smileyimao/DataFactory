# 产线优化日志 (IE / Continuous Improvement)

> **定位**：Auto pipeline 不可能一蹴而就，持续优化是核心财富。本日志记录每次瓶颈、根因与优化方案，供复盘与传承。

---

## 记录模板（每项）

```markdown
### [日期] 优化主题

**现象**：用户/系统反馈的问题（如「慢」「卡住」）

**根因**：瓶颈在哪（YOLO 跑两遍、I/O、无进度反馈等）

**方案**：具体改动（代码、配置、流程）

**效果**：量化指标（时间减半、进度可见等）

**教训**：可复用的设计原则
```

---

## 已记录优化

### [2026-02-26] YOLO 二次推理消除

**现象**：1008 张图 pipeline 耗时过长，用户反馈「归档后迟迟没动静」

**根因**：YOLO 跑了两遍——QC 报告一次、archiver 量产分流一次。同一批数据重复推理。

**方案**：
- qc_engine: `run_vision_scan(cfg, ..., return_detections=True)`，将 `qc_detections_by_video` 写入 `path_info`
- archiver: 若 `path_info` 中有 `qc_detections_by_video`，则复用，不再调用 `_get_detections_by_video` / `run_vision_scan`

**效果**：YOLO 推理次数减半，整体耗时约减半

**教训**：跨阶段数据流要显式传递，避免「下游重复算上游已有结果」

---

### [2026-02-26] 视觉扫描进度可见

**现象**：归档后长时间无输出，用户怀疑「卡住了」

**根因**：`run_vision_scan` 对 1008 文件循环无进度条，终端无反馈

**方案**：vision_detector 增加 tqdm 进度条 + 启动时打印「YOLO 视觉扫描 共 N 个文件」

**效果**：用户可感知进度，减少误判为卡死

**教训**：长耗时循环必须有进度反馈

---

### [2026-02-26] 加工进度条收敛

**现象**：每文件一条进度条，1008 条刷屏，看得累

**根因**：`production_tools` 每文件一个 tqdm，输出过于冗长

**方案**：改为单条整体进度条 `tqdm(video_paths, desc="加工", unit="文件")`

**效果**：单行进度，如 `加工: 45%|████| 450/1008 [02:30<03:00, 3.10文件/s]`

**教训**：批量任务用整体进度条，避免逐项刷屏

---

### [2026-02-26] raw 递归扫描

**现象**：同事或实际场景中，文件可能按文件夹分类、或藏在深层子目录，平铺在 raw 根目录不现实。

**根因**：video 模式用 `list_video_paths` 只扫顶层；image 已递归，video 未统一。

**方案**：
- `list_video_paths_recursive`：视频也递归扫描
- ingest：video 模式改用递归
- guard：`_list_raw_media` 复用 `ingest.get_video_paths`；Watchdog `recursive=True`；支持 image 扩展名

**效果**：raw 下任意层级子目录的图片/视频都能被发现

**教训**：Ingest 要兼容「随意扔进去」的用法，递归扫描是默认行为

---

### [2026-02-28] CVAT 伪标签上传：只用原生格式

**现象**：COCO、LabelMe、Ultralytics YOLO 等格式反复报错（Could not match item id、ImportFail、Dataset must contain **/*.xml），折腾很久。

**根因**：Import Dataset 与 Upload Annotations 是两套逻辑。前者走 datumaro 解析，格式要求极严；后者只需标注与 Task 帧名匹配。COCO/LabelMe/YOLO 等第三方格式在云版上解析不稳定。

**方案**：**只用 CVAT for images 1.1 原生格式**。反推 CVAT 导出的 annotations.xml 结构，用 `export_for_cvat_native.py` 生成。格式与 CVAT 导出一致，Upload 成功率最高。

**教训**：以后 CVAT 伪标签导出一律用原生格式，不再尝试 COCO/LabelMe/YOLO。

---

### [2026-02-20] CVAT 云版 Ultralytics YOLO item id 匹配 bug

**现象**：`Could not match item id: 'xxx' with any task frame`，上传标注失败。

**根因**：CVAT 云版对 Ultralytics YOLO Detection 格式的 item id 匹配有 bug。

**方案**：已废弃，改用 CVAT 原生格式。

---

### [2026-02-20] CVAT 导入失败：文件名含空格

**现象**：`CvatImportError: Failed to import dataset 'yolo_ultralytics_detection'`，反复失败。

**根因**：源视频名含空格（如 `outputVideo 2.MOV`），导出后 `train.txt` 路径为 `images/train/xxx_outputVideo 2.MOV_f00000.jpg`。CVAT/datumaro 解析 `train.txt` 时按空格分词，导致路径被截断、无法匹配图片。

**方案**：
1. **源头**：`production_tools` 输出帧时对媒体名做 `_safe_media_name()`（空格→下划线），archive/for_labeling 全链路不再含空格。
2. **兜底**：`export_for_cvat.py` 的 `_sanitize_filename()` 对历史数据二次兜底；`labeled_return` 支持 sanitized 回传匹配。
3. **预演练**：`scripts/demo_prepare.sh` 跑完整流程并验证 zip 无空格，演示前跑一次，当天直接用已验证 zip。

**效果**：`for_cvat.zip` 内路径无空格，CVAT 导入可正常完成；演示前预演练可避免现场翻车。

**教训**：导出给外部工具时，文件名应避免空格；源头预防比下游修补更稳。

---

### [2026-02-26] CVAT 云版标注上传踩坑

**现象**：将 YOLO 伪标签上传到 app.cvat.ai 时，REST 直接调用返回 405、格式名报 Unknown、SSL 证书验证失败，流程卡住很久。

**根因**：
1. **云版与文档不一致**：app.cvat.ai 对直接 REST POST 返回 405，实际用 TUS 分片上传，需用官方 cvat-sdk
2. **格式名不匹配**：文档/ datumaro 内部名 `yolo_ultralytics_detection` 无效，云版需 `Ultralytics YOLO Detection 1.0`（带空格、版本号）
3. **macOS SSL**：python.org 安装的 Python 缺根证书，HTTPS 报 CERTIFICATE_VERIFY_FAILED

**方案**：
- 用 cvat-sdk 替代裸 requests，`Client(config=Config(verify_ssl=False))` + `AccessTokenCredentials(token)`
- 格式名改为 `Ultralytics YOLO Detection 1.0`
- 增加 `--list-formats` 用于查询实例支持的格式名
- 用 certifi 或 `verify_ssl=False` 解决 macOS SSL

**效果**：`python scripts/cvat/cvat_upload_annotations.py <task_id>` 可稳定上传

**教训**：接入外部 API 时，优先查官方 SDK；格式/参数以实例返回为准（如 `--list-formats`）；云版与自建版行为可能不同

---

### [2026-02-26] CVAT Track 对导出图片序列无效

**现象**：同车不同帧（图 1、2）想用 Track 跨帧插值，但 Track 用不了。

**根因**：DataFactory 导出的是**单张图片**（每帧一个文件），不是视频。CVAT 的 Track 插值对视频/连续帧支持好，对「图片序列」效果差或不可用。

**方案**：逐张标。复制粘贴（Ctrl+C/V）在图片序列下可能无效，可尝试 **Propagate**：选中框 → `Ctrl+B` → 选「Propagate forward」复制到后续 N 帧（位置不变，需逐帧微调）。或直接逐帧画框，连续相似帧可跳过。

**教训**：若需 Track，应直接上传原始视频到 CVAT；当前抽帧→导出图片流程只能按图片逐张标。

---

### [2026-02-26] 未标相似帧自动丢弃

**现象**：变化不大的连续帧用户不标，希望 pipeline 并入训练集时自动丢弃，减少冗余。

**根因**：未标图对模型训练价值低，相似帧冗余增加数据量无益。

**方案**：`labeled_return.skip_empty_labels: true`（默认开启）。并入训练集时跳过 .txt 为空的图；copy_to_batch_labeled 同理。CVAT 导出含未标图时，import_labeled_return 自动过滤。

**效果**：用户可放心跳过相似帧，回传后 pipeline 只保留有标注的图。

**教训**：标注流程与 pipeline 策略要协同，减少人工无效劳动。

---

## 待优化项（待验证）

| 优化项 | 预期收益 | 优先级 |
|--------|----------|--------|
| GPU/MPS 显式启用 | YOLO 加速 5–10x | 高 |
| 换 yolov8n 轻量模型 | 推理更快，精度略降 | 中 |
| 质量分析重复 | QC + 量产各一次，可考虑缓存 | 低 |

---

## 设计原则（提炼）

1. **复用上游结果**：下游能用上游数据就不重算
2. **进度可见**：长耗时必有反馈
3. **输出收敛**：批量用整体进度，不逐项刷屏
4. **瓶颈可测**：加 profiling 或分段计时，定位瓶颈再优化
5. **控制台摘要、日志明细**：控制台只打汇总（如「共隔离 23 重复」），逐项明细写入 log 文件，需要时查 logs/
6. **外部 API 优先 SDK**：接入第三方服务时，优先用官方 SDK；格式/参数以实例返回为准，云版与自建版行为可能不同
7. **主动学习标注**：时间紧优先标低 confidence + QC 异常；相似帧可跳过，skip_empty_labels 自动丢弃；迭代直至精度满意（见 docs/active_labeling_priority.md）
