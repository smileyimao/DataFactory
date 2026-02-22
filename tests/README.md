# tests/ — 测试脚本（项目根目录，通用约定）

所有测试类脚本放此目录，与 `scripts/`（运维/工具脚本）区分。pytest、CI 等默认会识别根目录 `tests/`。

**运行方式**（在项目根目录执行）：

```bash
.venv/bin/python tests/test_dual_gate_mlflow.py
.venv/bin/python tests/smoke_test.py
```

脚本内通过 `PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)` 解析项目根，用于加载 config、storage。
