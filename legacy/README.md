# Legacy — 旧实现（v1.x 入口）

此目录存放 **v1.5 架构重构前** 的入口与实现，仅作保留与对照，**不再作为主入口使用**。

| 文件 | 说明 |
|------|------|
| `main_factory.py` | 旧主流程入口（集中质检复核） |
| `factory_guard.py` | 旧监控入口（watchdog 凑批） |
| `core_engine.py` | 旧质检与报告（DataMachine） |
| `db_manager.py` | 旧 DB 与指纹 |
| `factory_config.yaml` | 旧配置文件 |

**当前推荐**：使用项目根目录的 **`main.py`**（单次运行或 `--guard`），配置在 **`config/settings.yaml`**，逻辑在 **`core/`** 与 **`engines/`**。

若需运行旧入口，请在**项目根目录**执行（以便导入 `config.logging`）：
- `python legacy/main_factory.py --limit 5 --gate 85`
- `python legacy/factory_guard.py`  
（依赖根目录 `.env`、`config/` 等；日志写入根目录 `logs/`。）
