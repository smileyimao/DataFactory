# DataFactory 工业级设计规范与改进路线图

> 目标：在系统初级阶段建立规范，保证 robust、可维护、可观测。

---

## 一、已完成的规范

| 规范 | 状态 |
|------|------|
| Path Decoupling 路径解耦 | ✅ 已实现 |
| 配置中心集中管理 | ✅ settings.yaml |
| 环境变量覆盖 | ✅ DATAFACTORY_* |
| 配置校验 | ✅ validate_config() |

---

## 二、待改进项（按优先级）

### P0 关键（影响稳定性）✅ 已完成

| 问题 | 状态 |
|------|------|
| **文件操作无重试** | ✅ retry_utils.safe_move_with_retry、safe_copy_with_retry；config retry.max_attempts/backoff_seconds；copy 失败打 warning、计入 file_copy_errors_total |
| **数据库无错误处理** | ✅ db_tools 所有操作 try/except sqlite3.Error，记录日志，返回 None/False |
| **无健康检查端点** | ✅ GET /api/health，检查 DB、目录可写、config 校验 |
| **路径遍历风险** | ✅ get_thumbnail 用 Path.resolve() 严格校验，拒绝 .. / \\ |

### P1 高（影响可维护性）✅ 已完成

| 问题 | 状态 |
|------|------|
| **时区硬编码** | ✅ core/time_utils.py，config timezone |
| **视频扩展名分散** | ✅ startup._get_video_extensions(cfg)，ingest 已用 config |
| **异常被吞掉** | ✅ fingerprinter 打 warning 日志 |
| **配置范围未校验** | ✅ validate_config 校验 min<max、gate、双门槛 |
| **日志无轮转** | ✅ RotatingFileHandler，config logging.max_bytes/backup_count |

### P2 中（影响可观测性）✅ 已完成

| 问题 | 状态 |
|------|------|
| **无 metrics 导出** | ✅ engines/metrics.py，GET /api/metrics |
| **临时目录清理** | ✅ qc_engine 用 TemporaryDirectory |
| **邮件无重试** | ✅ notifier max_retries/retry_delay_seconds |

### P3 低（长期优化）✅ 已完成

| 问题 | 状态 |
|------|------|
| 代码格式化 | ✅ pyproject.toml black + isort + mypy |

---

## 三、设计原则（大厂规范）

### 1. 配置驱动
- 所有可变值进 config，不硬编码
- 支持 env 覆盖，便于部署

### 2. 失败透明
- 异常必须记录，带上下文（batch_id, path, operation）
- 不吞异常，不裸 except
- 关键操作有重试（可配置）

### 3. 可观测
- 健康检查端点
- 关键路径有耗时日志
- 错误有计数（便于告警）

### 4. 可测试
- 依赖可注入（config, time, file_ops）
- 无隐式全局状态

### 5. 安全
- 路径严格校验，防 traversal
- 敏感信息从 env 读取，启动时校验

### 6. 一致性
- 错误返回：统一 Optional[T] 或 Result
- 命名：cfg, paths, qc_cfg 等约定
- 日志级别：INFO=正常，WARNING=可恢复，ERROR=需关注

---

## 四、实施顺序建议

1. **本周**：P0 四项（重试、DB 错误处理、health、路径校验）
2. **下周**：P1 五项（时区、扩展名、异常日志、配置校验、日志轮转）
3. **迭代**：P2、P3 按需推进

---

*文档版本：v1 | 基于代码审计报告*
