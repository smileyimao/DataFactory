# Path Decoupling 路径解耦

> 工业级设计：所有路径与目录名从配置读取，改名只需改一处，支持环境变量覆盖。

---

## 1. 配置中心 (config/settings.yaml)

### paths 节

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `batch_prefix` | 批次目录前缀 | `Batch_` |
| `batch_fails_suffix` | 废片目录后缀 | `_Fails` |
| `batch_subdirs` | 批次内子目录名 | 见下 |
| `ensure_dirs` | 启动时确保存在的目录 key 列表 | `[raw_video, data_warehouse, ...]` |

### batch_subdirs

```yaml
paths:
  batch_subdirs:
    reports: "reports"      # 质量报告、工业报表
    source: "source"        # 源视频归档
    refinery: "refinery"    # 高置信燃料
    inspection: "inspection" # 待人工
```

改名时只改此处，代码自动生效。

---

## 2. 环境变量覆盖

部署时可使用环境变量覆盖 paths 中的值：

| 环境变量 | 覆盖 |
|----------|------|
| `DATAFACTORY_RAW_VIDEO` | paths.raw_video |
| `DATAFACTORY_DATA_WAREHOUSE` | paths.data_warehouse |
| `DATAFACTORY_REJECTED_MATERIAL` | paths.rejected_material |
| ... | 规则：`DATAFACTORY_` + key 大写 |

---

## 3. API (config/config_loader.py)

- **get_batch_paths(cfg, batch_base)** → 返回 qc_dir, source_archive_dir, fuel_dir, human_dir, mass_dir
- **get_batch_media_subdirs(cfg)** → 返回扫描媒体时需遍历的子目录名（含兼容旧版）
- **get_batch_prefix(cfg)** → 批次前缀
- **get_batch_fails_suffix(cfg)** → 废片后缀
- **get_pending_queue_path(cfg)** → 待复核队列 JSON 路径
- **get_pending_thumbs_dir(cfg)** → 待复核缩略图目录
- **validate_config(cfg)** → 校验配置完整性，返回错误列表
- **init_storage_from_config(cfg)** → 根据配置创建目录

---

## 4. 原则

- **单一真相源**：路径与目录名只在 config 定义
- **无硬编码**：业务代码不写死 "Batch_"、"reports" 等字符串
- **可测试**：测试可注入自定义 cfg，不依赖物理路径
