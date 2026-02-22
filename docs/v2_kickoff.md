# DataFactory v2.0 开工说明

> 结合 **implementation_checklist.md** 与 **Roadmap.md**，v1.5 已完成，v2.0 正式开工。  
> 本文档为 v2 分批任务、首项落地与接口预留的单一入口。

---

## 1. v2.0 目标（与 checklist 对应）

| # | 项 | 说明 |
|---|----|------|
| 13 | 计算机视觉质检接入 | YOLO/等效、单例加载、智能抽检 |
| 14 | Edge 预留 | 轻量化、配置可下发，与 13 一起设计 |
| 15 | 版本映射 | 日志/元数据记录算法/模型版本 |
| 16 | 双门槛准入 | 自动放行/拦截 + 人工审核中间态 |
| 17 | MLflow Tracking | 实验参数、质量指标、性能指标 |
| 18 | 模型注册与复现 | model registry，与训练/评估 pipeline 打通 |
| 19 | 不合格检测可扩展 | 配置/插件，在 blur/brightness/jitter 基础上新增 |

---

## 2. 建议实施顺序

```
13+14（YOLO + Edge 预留） → 15（版本映射） → 16（双门槛） → 17（MLflow） → 18（模型注册）
                                                                              ↑
19（不合格检测可扩展）———————————————————————— 可与 13 并行或稍后接入
```

- **首批**：13+14 打地基（视觉引擎 + 单例 + 抽检 + 轻量/配置预留）。  
- **随后**：15 版本映射（便于溯源），16 双门槛（用上模型输出），17–18 实验与模型管理。  
- **19**：与 13 设计时预留扩展点，实现上可稍后（配置/插件接口）。

---

## 3. 首批任务（落地项）

### 3.1 视觉引擎骨架（#13 + #14 预留）

- [x] 新增 **engines/vision_detector.py**（或等价模块名）  
  - 职责：加载 2D 检测/分割模型（如 YOLO）、对视频/帧做推理，**只返回数值/检测结果**，不做了「合格/不合格」决策。  
  - 单例：全局唯一模型实例，控制显存与延迟。  
  - 智能抽检：等间隔采样（可配置秒数或帧数），与现有 `qc_sample_seconds` 对齐或扩展。  
  - Edge 预留：接口设计上支持「轻量化模型路径/配置可下发」（具体量化/剪枝可 v3 再做）。

- [x] **config/settings.yaml** 增加 v2 段（可选，不破坏现有 key）：  
  - 如 `vision:`：`model_path`、`sample_seconds`、`enabled`、`edge_lightweight` 等占位。

- [x] **core/qc_engine** 预留调用点：  
  - 在现有「规则质检」之后、汇总前，可调用 `vision_detector.run(...)`，将视觉结果并入 qc_archive 或扩展字段；首阶段可先不参与合格/不合格决策，仅落日志与元数据。

### 3.2 版本映射（#15，建议尽早）

- [x] 在日志与批次元数据中记录「当前生效的算法/模型版本」  
  - 例如：`algorithm_version: "rules_v1"`、`vision_model_version: "YOLOv8-1.0"`（占位亦可）。  
  - 写入 DB 或 qc_archive 的元数据，便于 v4 血缘与审计。

### 3.3 不合格检测可扩展（#19 接口）

- [x] 在 **engines/quality_tools** 或 **config** 中预留「可插拔检测项」扩展点  
  - 现有 blur/brightness/jitter 不变；新增项通过配置或注册式插件接入，由 qc_engine 统一调度。  
  - 便于后续接入 YOLO 输出、黑帧、分辨率异常等。

---

## 4. 依赖与约束

- **Python**：保持 3.9+，venv；若引入 YOLO，需在 requirements.txt 中增加相应依赖（如 ultralytics、torch 等），并注明可选或按需安装。  
- **配置**：所有 v2 新增项均通过 config 开关/路径控制，不开启时行为与 v1.6 一致。  
- **向后兼容**：不删除、不破坏现有 pipeline；Guard、自检、流水线逻辑保持不变。

---

## 5. 验收与里程碑

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| M1 | vision_detector 骨架就绪，单例+抽检可调，qc_engine 有预留调用点，配置有 v2 占位 | ✅ 已完成 |
| M1.5 | 抽帧 + 实际 YOLO 推理（按 sample_seconds 抽帧，predict 用 config 参数），结果汇总日志 | ✅ 已完成 |
| M2 | 版本映射在日志/元数据中可见，至少 1 个算法版本字段可写可读（version_info.json + path_info） | ✅ 已完成 |
| M3 | 双门槛（#16）接入决策层；MLflow（#17）至少记录批次级实验与指标 | ✅ 已完成 |

完成 M1 即视为 v2.0 开工落地；M2 已与抽帧推理一并完成；M3 已完成。**v2.0 主体收尾**；#18 模型注册留待 v2.5 或后续。

---

## 6. 相关文档

| 文档 | 用途 |
|------|------|
| **docs/implementation_checklist.md** | 逐项状态、已实现 vs 待做、v2 小结与链接 |
| **docs/Roadmap.md** | 阶段二全文、Edge/多模态等长期规划 |
| **docs/architecture_mapping.md** | 架构映射与目录结构 |
| **docs/logic_diagram.md** | 当前整体逻辑图 |

---

*v2.0 开工 | 与 implementation_checklist + Roadmap 同步*
