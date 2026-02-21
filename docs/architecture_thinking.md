# 🧠 DataFactory 架构思维进阶指南

> **基于你的 IE 思维 + 软件工程最佳实践**：从「流程 + 工具 + 决策 + 配置」出发，补充一些能让系统更健壮、可扩展的架构思维。

---

## ✅ 你已经有的（IE 思维 → 软件架构）

| 你的 IE 思维 | 在软件里的对应 | 为什么好 |
|------------|--------------|---------|
| **流程为主**（Ingest → QC → Review → Archive） | **编排层 (Orchestration)** | 一眼看懂「数据怎么流」，新人上手快，改流程不改工具 |
| **工具独立**（只干活，不决策） | **工具层 (Tools / Engines)** | 可替换、可测试、可复用（今天用 YOLO，明天换 DETR，工具层换，流程层不变） |
| **决策分离**（根据工具输出 + 配置做判断） | **规则层 (Rules / Policies)** | 改阈值/改规则不改工具，A/B 测试、多环境配置都容易 |
| **配置集中**（工厂参数统一管理） | **配置层 (Config)** | 改行为不改代码，部署到不同环境（开发/测试/生产）只需改配置 |

**结论**：你的「流程 + 工具 + 决策 + 配置」已经是**很好的架构思维**，和软件工程里的「分层架构 (Layered Architecture)」「关注点分离 (Separation of Concerns)」完全一致。

---

## 🚀 可以补充的（软件工程里的常见模式）

### 1. **依赖注入 (Dependency Injection)**：让工具可替换、可测试

**你的现状**：
```python
# core_engine.py 里直接 import
from core_engine import DataMachine
DataMachine.qc_sensor(...)  # 硬编码依赖
```

**更好的做法**：
```python
# core/qc_engine.py
class QCEngine:
    def __init__(self, quality_tool, fingerprinter, db_tool, config):
        self.quality_tool = quality_tool      # 注入工具，而不是硬编码
        self.fingerprinter = fingerprinter
        self.db_tool = db_tool
        self.config = config
    
    def check(self, video_path):
        # 调用注入的工具，而不是直接 import
        fingerprint = self.fingerprinter.compute(video_path)
        quality_result = self.quality_tool.analyze(video_path)
        # ... 决策逻辑
```

**好处**：
- **可测试**：测试时注入「假工具」，不依赖真实文件/数据库
- **可替换**：今天用 `QualityToolV1`，明天换 `QualityToolV2`（支持 LiDAR），流程层代码不变
- **可扩展**：加新工具（如 `lidar_tool`）只需在初始化时注入，不需要改流程代码

**对你来说**：这是「工具类独立」的**实现方式**——不是只把工具代码分开，而是让流程层「依赖工具接口，不依赖具体实现」。

---

### 2. **接口/协议 (Interface / Protocol)**：定义「工具必须做什么」

**你的现状**：
- 工具类「只干活，不决策」，但没有明确定义「每个工具必须返回什么格式」

**更好的做法**：
```python
# engines/interfaces.py（或 engines/base.py）
from abc import ABC, abstractmethod

class QualityTool(ABC):
    """质检工具的接口：所有质检工具必须实现这个方法"""
    @abstractmethod
    def analyze(self, video_path: str) -> dict:
        """
        返回格式：{"br": float, "bl": float, "jitter": float}
        不返回 "Too Dark" 等判断，只返回数值
        """
        pass

class Fingerprinter(ABC):
    """指纹工具的接口"""
    @abstractmethod
    def compute(self, file_path: str) -> str:
        """返回 MD5 字符串"""
        pass

# engines/quality_tools.py
class BasicQualityTool(QualityTool):
    """基础质检工具：blur/brightness/jitter"""
    def analyze(self, video_path: str) -> dict:
        # 实现细节
        return {"br": 120.5, "bl": 45.2, "jitter": 12.3}

# engines/lidar_tools.py（未来）
class LidarQualityTool(QualityTool):
    """LiDAR 质检工具：也实现同样的接口"""
    def analyze(self, lidar_path: str) -> dict:
        # LiDAR 特定的实现
        return {"point_count": 100000, "density": 0.5, "coverage": 0.8}
```

**好处**：
- **一致性**：所有质检工具都返回相同格式，决策层代码统一
- **可扩展**：加新工具（LiDAR、YOLO）只需实现接口，流程层不需要改
- **文档化**：接口就是「契约」，一看就知道工具必须做什么

**对你来说**：这是「工具类独立」的**标准化**——不是只有代码分开，而是定义「工具必须遵守的协议」，让工具之间可以互换。

---

### 3. **状态机 (State Machine)**：让流程状态可追踪、可恢复

**你的现状**：
- 流程是「黑盒」：一个视频从 raw 到归档，中间状态（正在质检、等待复核、已归档）没有记录

**更好的做法**（Roadmap v3 已有，这里补充「为什么好」）：
```python
# db/schema.py
CREATE TABLE task_state (
    task_id TEXT PRIMARY KEY,
    file_path TEXT,
    state TEXT,  -- 'pending' | 'processing' | 'qc_done' | 'reviewing' | 'archived' | 'failed'
    current_stage TEXT,  -- 'ingest' | 'qc' | 'review' | 'archive'
    metadata JSON,  -- 存储中间结果（得分、指纹等）
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

# core/qc_engine.py
def process_video(self, video_path):
    task_id = self.db.create_task(video_path, state='processing', stage='qc')
    try:
        result = self._do_qc(video_path)
        self.db.update_task(task_id, state='qc_done', metadata=result)
        return result
    except Exception as e:
        self.db.update_task(task_id, state='failed', metadata={'error': str(e)})
        raise
```

**好处**：
- **可追踪**：任何时候都能查「这个文件到哪一步了」
- **可恢复**：系统崩溃后，可以从「上次失败的地方」继续
- **可监控**：Dashboard 可以显示「有多少文件在 QC、多少在 Review、多少已归档」
- **可调试**：出问题时，看状态机记录就知道「卡在哪一步」

**对你来说**：这是「流程为主」的**可观测性**——不是只有流程代码，而是让流程的「状态」可以被记录、查询、恢复。

---

### 4. **事件驱动 (Event-Driven)**：让流程解耦、可扩展

**你的现状**：
- 流程是「同步」的：Ingest → QC → Review → Archive，一步接一步，中间不能插入其他逻辑

**更好的做法**（可选，适合未来扩展）：
```python
# core/event_bus.py（事件总线）
class EventBus:
    def __init__(self):
        self.handlers = {}  # event_type -> [handler1, handler2, ...]
    
    def subscribe(self, event_type, handler):
        """订阅事件：当 event_type 发生时，调用 handler"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    def publish(self, event_type, data):
        """发布事件：通知所有订阅者"""
        for handler in self.handlers.get(event_type, []):
            handler(data)

# core/qc_engine.py
def process_video(self, video_path):
    result = self._do_qc(video_path)
    self.event_bus.publish('qc_completed', {
        'file_path': video_path,
        'result': result
    })
    return result

# engines/notifier.py（订阅事件）
def setup_notifier(event_bus):
    def on_qc_completed(data):
        if data['result']['status'] == 'blocked':
            send_email(...)  # 只在「被拦」时发邮件
    event_bus.subscribe('qc_completed', on_qc_completed)
```

**好处**：
- **解耦**：QC 引擎不需要知道「谁在监听 QC 完成事件」，只需要发布事件
- **可扩展**：加新功能（如「QC 完成后自动导出到 labeling 工具」）只需订阅事件，不需要改 QC 引擎代码
- **灵活**：可以「选择性监听」：开发环境不监听，生产环境监听

**对你来说**：这是「流程为主」的**可扩展性**——不是只有固定的流程步骤，而是让流程的「每一步」都可以被「外部逻辑」监听和扩展，而不需要改流程代码。

---

### 5. **配置验证 (Config Validation)**：让配置错误早发现

**你的现状**：
- 配置在 YAML 里，但如果写错了（如 `min_brightness: "abc"`），要到运行时才报错

**更好的做法**：
```python
# config/schema.py（配置模式定义）
from dataclasses import dataclass
from typing import Optional

@dataclass
class QualityThresholds:
    min_brightness: float
    max_brightness: float
    min_blur_score: float
    max_jitter: float
    
    def __post_init__(self):
        """验证配置合法性"""
        if self.min_brightness >= self.max_brightness:
            raise ValueError("min_brightness must be < max_brightness")
        if self.min_blur_score < 0:
            raise ValueError("min_blur_score must be >= 0")

@dataclass
class Config:
    quality_thresholds: QualityThresholds
    paths: dict
    email_setting: dict

# config/config_loader.py
def load_config(config_path: str) -> Config:
    """加载配置并验证"""
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    # 验证并转换为强类型对象
    return Config(
        quality_thresholds=QualityThresholds(**raw['quality_thresholds']),
        paths=raw['paths'],
        email_setting=raw['email_setting']
    )
```

**好处**：
- **早发现**：启动时就发现配置错误，而不是运行到一半才崩
- **类型安全**：IDE 可以提示「这个配置项是什么类型」，写代码时不会用错
- **文档化**：配置模式就是「配置的文档」，一看就知道「必须配什么、可选配什么」

**对你来说**：这是「配置集中」的**健壮性**——不是只有配置文件，而是让配置「有模式、可验证」，避免配置错误导致系统崩溃。

---

### 6. **错误处理策略 (Error Handling Strategy)**：让系统更健壮

**你的现状**：
- 代码里有 `try/except`，但没有统一的「错误处理策略」：有些错误该重试、有些该跳过、有些该告警

**更好的做法**：
```python
# core/error_handler.py
class ErrorHandler:
    """统一错误处理策略"""
    
    @staticmethod
    def handle_qc_error(error, video_path, retry_count=0):
        """QC 错误：重试 3 次，失败后标记为 'failed'，不阻塞其他文件"""
        if retry_count < 3:
            logger.warning(f"QC 失败，重试 {retry_count + 1}/3: {video_path}")
            return "retry"
        else:
            logger.error(f"QC 最终失败: {video_path}, 错误: {error}")
            return "skip"  # 跳过这个文件，继续处理下一个
    
    @staticmethod
    def handle_db_error(error, operation):
        """DB 错误：告警，但不阻塞流程"""
        logger.error(f"DB 操作失败 ({operation}): {error}")
        # 可以发邮件告警
        return "continue"  # 继续流程，但记录错误
    
    @staticmethod
    def handle_critical_error(error):
        """关键错误：停止整个批次"""
        logger.critical(f"关键错误，停止批次: {error}")
        # 发紧急告警
        raise  # 抛出异常，停止流程
```

**好处**：
- **策略清晰**：不同错误有不同处理方式，不会「所有错误都重试」或「所有错误都停止」
- **可恢复**：非关键错误（如单个文件 QC 失败）不阻塞整个批次
- **可观测**：所有错误都有日志，方便排查

**对你来说**：这是「流程为主」的**健壮性**——不是只有流程代码，而是让流程「遇到错误时知道该怎么做」，不会因为一个小错误就整个系统停摆。

---

## 🎯 总结：你的架构思维 + 补充建议

| 你的思维 | 补充建议 | 为什么补充 |
|---------|---------|-----------|
| ✅ **流程为主** | + **状态机**（可追踪）+ **事件驱动**（可扩展） | 让流程「可观测、可扩展」，不只是「能跑」 |
| ✅ **工具独立** | + **依赖注入**（可替换）+ **接口/协议**（标准化） | 让工具「可测试、可替换、可扩展」，不只是「代码分开」 |
| ✅ **决策分离** | + **配置验证**（健壮性） | 让决策「有模式、可验证」，不只是「能判断」 |
| ✅ **配置集中** | + **错误处理策略**（健壮性） | 让系统「遇到错误知道该怎么做」，不只是「有配置」 |

---

## 📝 优先级建议

### **Phase 1（现在就可以做）**：配置验证 + 错误处理策略
- **收益高、风险低**：不改现有代码结构，只是加验证和错误处理
- **立即见效**：配置错误早发现，错误处理更清晰

### **Phase 2（重构时做）**：依赖注入 + 接口/协议
- **收益高、风险中**：需要重构现有代码，但能让系统更可测试、可扩展
- **为未来铺路**：加 LiDAR、加 YOLO 时，只需要「实现接口、注入工具」，不需要改流程代码

### **Phase 3（v3 时做）**：状态机 + 事件驱动
- **收益高、风险高**：需要改数据库 schema、改流程代码，但能让系统「可追踪、可恢复、可扩展」
- **适合大规模**：当数据量大、需要监控、需要恢复时，状态机和事件驱动就很有用

---

## 💡 一句话总结

**你的「流程 + 工具 + 决策 + 配置」已经是很好的架构思维。**  
**补充的「依赖注入、接口、状态机、事件驱动、配置验证、错误处理」是让这个架构「更健壮、可扩展、可测试」的实现方式。**

**不需要一次全做**，按优先级逐步补充即可。最重要的是：**保持「流程为主、工具独立、决策分离、配置集中」这个核心思维，然后在实现时用这些模式让代码更健壮。**

---

*文档版本：v2026.02 | 基于 IE 思维 + 软件工程最佳实践*
