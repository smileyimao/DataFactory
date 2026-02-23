# 厂长中控台设计（Dashboard）

> 替代 Terminal 逐项 y/n，改为 Web 排队复核：指标、缩略图、单项/批量决策，无 600s 超时丢料。

---

## 1. 目标

| 现状 | 目标 |
|------|------|
| Terminal 逐项按 y/n/all/none | Web 中控台，厂长上班打开即可见 |
| 600s 无响应自动丢弃 | 排队等待，无超时丢料 |
| 无缩略图、指标分散 | 缩略图 + 规则分项 + 得分一目了然 |
| 只能整批 all/none | 单项放行/拒绝 + 批量复核 |

---

## 2. 架构

```
QC 产线（24h 运行）
    → blocked 项写入 pending_review 队列（不阻塞）
    → 合格/自动拦截照常归档

厂长中控台（Web）
    → 读取队列 → 展示缩略图 + 指标
    → 单项/批量 放行/拒绝 → 调用 archiver 归档
```

**配置**：`review_mode: "terminal" | "dashboard"`  
- `terminal`：保持现有 Terminal 交互  
- `dashboard`：blocked 入队，不阻塞，由中控台复核

---

## 3. 队列存储

- **路径**：`storage/pending_review/queue.json`
- **缩略图**：`storage/pending_review/thumbs/{item_id}.jpg`（入队时从视频首帧提取）
- **结构**：每项含 `id`, `batch_id`, `filename`, `archive_path`, `score`, `rule_stats`, `is_duplicate`, `thumbnail`, `created_at`

---

## 4. API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/pending` | 获取待复核列表 |
| POST | `/api/pending/{id}/approve` | 单项放行 |
| POST | `/api/pending/{id}/reject` | 单项拒绝 |
| POST | `/api/pending/batch/approve` | 批量放行（body: `{"ids": [...]}`） |
| POST | `/api/pending/batch/reject` | 批量拒绝 |

---

## 5. 前端

- 列表：缩略图 + 文件名 + 得分 + 规则分项（未达标标红）
- 操作：每项 [放行] [拒绝]；顶部 [全选放行] [全选拒绝]
- 刷新：可定时或手动刷新

---

## 6. 启动方式

```bash
# 产线（Guard 或单次）
python main.py --guard

# 中控台（单独进程，可 24h 常驻）
python -m dashboard.app
# 或
uvicorn dashboard.app:app --host 0.0.0.0 --port 8765
```

配置 `paths.dashboard_port` 或环境变量可指定端口。
