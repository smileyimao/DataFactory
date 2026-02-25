# DataFactory 测试

pytest 分层测试：unit / integration / e2e / api。

## 安装

```bash
pip install -r requirements-dev.txt
```

## 运行

```bash
# 全量（排除 e2e，e2e 需测试视频）
pytest tests/ -v -m "not e2e"

# 仅单元
pytest tests/unit/ -v

# 仅集成
pytest tests/integration/ -v

# 含 e2e（需 storage/test/original/ 下 normal.mov 等）
pytest tests/ -v

# 覆盖率
pytest tests/ -m "not e2e" --cov=config --cov=core --cov=engines --cov-report=term-missing
```

## 目录

| 目录 | 说明 |
|------|------|
| `unit/` | 单元：validate_config、decide_env 等 |
| `integration/` | 集成：双门槛分流、archiver |
| `e2e/` | 端到端：smoke QC 全流程（需测试视频） |
| `api/` | API：/api/health、/api/metrics |
| `fixtures/` | 测试数据占位 |

## 旧脚本

`smoke_test.py`、`test_dual_gate_mlflow.py` 保留作参考，推荐使用 pytest。
