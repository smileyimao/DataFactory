# DataFactory 工作交接（给下一个对话的 Agent）

## 一、已经做完的事（v1.6 地基加固）

### 1. 存储与运维（Storage & Ops）
- 建了 **storage/**：下面有 raw、archive、rejected、redundant、test、reports；配置里路径已改为用这些（key 仍是 raw_video、data_warehouse 等，value 指向 storage/raw、storage/archive 等）。
- 建了 **db/**：数据库路径改为 `db/factory_admin.db`；若根目录曾有 factory_admin.db，已迁到 db/；Roadmap.md 已移到 docs/。
- **报表持久化**：每批 QC 生成的 HTML 报告和图表会额外写入 `storage/reports/`（`{batch_id}_quality_report.html`、`{batch_id}_chart.png`）。
- **注意**：根目录可能还留着旧文件夹 raw_video、data_warehouse、rejected_material、redundant_archives、test_videos，里面的内容尚未迁到 storage/ 对应子目录；若用户需要，可再做一次「把旧目录内容迁入 storage」并视情况删旧目录。

### 2. 数据协议预埋（Future-Proofing）
- **db_tools**：production_history 表新增 `sync_id VARCHAR(64) NULL`；record_production 增加可选参数 sync_id，用于以后对齐外部传感器时间戳。
- **quality_tools**：在 decide_env 里预留了 Conflict 标签的注释/扩展点，为 v2.x 人机冲突检测做准备。

### 3. 健壮性（Hardening）
- **config/settings.yaml**：paths 已全部指向 storage/ 与 db/（key 不变）。
- **config/config_loader.py**：新增 `init_storage_structure()`，启动时创建 storage/* 和 db/；_default_config 的默认路径已同步为新结构。
- **main.py**：启动时调用 init_storage_structure()，并若有 db_file 则调用 db_tools.init_db(db_path)，保证表与 sync_id 列存在。
- 根目录已添加 **requirements.txt**（PyYAML、opencv-python-headless、tqdm、pandas、matplotlib、python-dotenv、watchdog、inputimeout）。

### 4. 门户
- 根目录有 **README.md**：项目定位、架构索引（core/engines/config/storage/db/docs/legacy）、快速启动（python main.py / python main.py --guard）、v1.x/v2.x 简要说明，并指向 docs/ 与 CHANGELOG.md。

### 5. 流程闭环
- `python main.py`：set_base_dir → init_storage_structure → load_config → init_db → pipeline.run_smart_factory 或 guard.run_guard。
- 流程从 storage/raw 取视频 → QC（报告写 Batch 下并复制到 storage/reports/）→ 复核 → 归档到 storage/archive | rejected | redundant，并写 DB（可传 sync_id）。

---

## 二、以后/接下来可以干的事（建议优先级）

1. **旧目录迁移（可选）**  
   若用户希望根目录干净：把 raw_video、data_warehouse、rejected_material、redundant_archives、test_videos 的内容迁到 storage/raw、storage/archive、storage/rejected、storage/redundant、storage/test，再视情况删除或清空旧目录。

2. **验证主流程**  
   在项目根执行 `pip install -r requirements.txt` 后跑 `python main.py`，确认无报错、能扫 storage/raw、能写 storage/reports/ 和 DB；无视频时应有友好提示而非崩溃。

3. **CHANGELOG**  
   已补 v1.6 条（存储重构、sync_id/Conflict 预埋、init_storage_structure、requirements、README 等）。

4. **v2.x 预留的后续**
   - 在业务逻辑里真正使用/写入 sync_id（例如对接外部传感器时间戳）。
   - 在 quality_tools 或上层根据「人机冲突」信号设置 env = "Conflict"，并在报告/统计里体现。

5. **用户新需求**  
   用户可能继续提新功能或修 bug；以当前 ldg 代码库为准，按用户当条消息的需求接着做即可。

---

## 三、关键文件位置（方便快速接手）

| 用途 | 路径 |
|------|------|
| 配置与自检 | config/settings.yaml、config/config_loader.py（含 init_storage_structure） |
| 入口与流程 | main.py、core/pipeline.py、core/qc_engine.py、core/archiver.py |
| 报告与报表持久化 | engines/report_tools.py（copy_to_dir）、engines/production_tools.py（reports_archive_dir） |
| DB 与预埋 | engines/db_tools.py（sync_id）、engines/quality_tools.py（Conflict 预留） |
| 文档 | 根目录 README.md、docs/Roadmap.md、docs/architecture_mapping.md、docs/implementation_checklist.md、CHANGELOG.md |
