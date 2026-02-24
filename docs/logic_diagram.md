# DataFactory 整体逻辑图

## 1. 入口与运行模式

```mermaid
flowchart TB
    subgraph entry["入口 main.py"]
        A[python main.py] --> B{带 --guard?}
        B -->|否| C[单次运行]
        B -->|是| D[Guard 模式]
    end

    C --> E[pipeline.run_smart_factory]
    E --> F[从 storage/raw 扫描视频]
    F --> G[Ingest → QC → Review → Archive]
    G --> H[结束退出]

    D --> I[开机大扫除 startup_scan]
    I --> J[存量视频作为一批送厂]
    J --> K[启动 Watchdog 监控 storage/raw]
    K --> L{新文件创建/移入?}
    L -->|是| M[等写入稳定 + 凑批时间]
    M --> N[本批送厂 run_smart_factory]
    N --> K
    L -->|否| K
```

---

## 2. Guard 模式：监控与凑批

```mermaid
flowchart LR
    subgraph raw["storage/raw"]
        R[新视频落地]
    end

    R --> A[Watchdog 检测到]
    A --> B[等文件稳定<br/>file_stable_*]
    B --> C[启动/重置 batch_wait 计时]
    C --> D{计时到?}
    D -->|否，期间又来新文件| C
    D -->|是| E[列出 raw 下全部视频]
    E --> F[run_smart_factory 送厂]
    F --> G[继续监控]
```

---

## 3. 主流水线：Ingest → QC → Review → Archive

```mermaid
flowchart TB
    subgraph ingest["1. Ingest 入场"]
        I1[get_video_paths]
        I2[从 raw_video 扫描或使用传入列表]
        I1 --> I2
    end

    subgraph qc["2. QC 质检"]
        Q1[指纹采集 MD5]
        Q2[质量检测 + 重复检测]
        Q3[源文件移入 Batch/source]
        Q4[建 qc_archive + 发汇总邮件]
        Q1 --> Q2 --> Q3 --> Q4
    end

    subgraph split["质检结果"]
        S1[qualified 合格]
        S2[blocked 被拦]
    end

    subgraph review["3. Review 复核"]
        R1[仅对 blocked 发一封邮件]
        R2[逐条 y/n/all/none 人工决策]
        R3[→ to_produce 或 to_reject]
        R1 --> R2 --> R3
    end

    subgraph archive["4. Archive 归档"]
        A1[to_reject: 废片/冗余]
        A2[to_produce: 合格]
        A1 --> A1a[废片 → storage/rejected/<br/>冗余 → storage/redundant]
        A2 --> A2a[量产 → storage/archive<br/>写 DB production_history]
    end

    ingest --> qc
    qc --> split
    S1 --> archive
    S2 --> review
    review --> archive
```

---

## 4. 数据与存储流向

```mermaid
flowchart LR
    subgraph input["输入"]
        RAW[storage/raw<br/>原始视频]
    end

    subgraph pipeline["流水线"]
        P[QC + Review]
    end

    subgraph output["输出"]
        ARCH[storage/archive<br/>合格成品 + DB]
        REJ[storage/rejected<br/>废片 Batch_*_Fails]
        RED[storage/redundant<br/>重复/冗余]
        REP[storage/reports<br/>HTML + 图表]
    end

    RAW --> P
    P --> ARCH
    P --> REJ
    P --> RED
    P --> REP
```

---

## 5. 配置与模块依赖（简图）

```mermaid
flowchart TB
    subgraph config["config/"]
        CFG[settings.yaml]
        LOADER[config_loader]
        CFG --> LOADER
    end

    subgraph core["core/"]
        MAIN[main.py]
        PIPE[pipeline]
        GUARD[guard]
        ING[ingest]
        QC[qc_engine]
        REV[reviewer]
        ARC[archiver]
        MAIN --> PIPE
        MAIN --> GUARD
        PIPE --> ING
        PIPE --> QC
        PIPE --> REV
        PIPE --> ARC
        GUARD --> PIPE
    end

    subgraph engines["engines/"]
        FT[file_tools]
        FING[fingerprinter]
        DB[db_tools]
        NOTIFY[notifier]
        PROD[production_tools]
    end

    LOADER --> core
    ING --> FT
    QC --> FING
    QC --> DB
    QC --> NOTIFY
    QC --> PROD
    ARC --> DB
    ARC --> PROD
```

---

说明：

- **单次运行**：`python main.py` → 扫一次 raw → 走完整流水线 → 退出。
- **Guard 模式**：`python main.py --guard` → 先处理存量 → 再持续监控 raw，新文件凑批后送厂，循环。
- **流水线**：Ingest 取视频列表 → QC（指纹+质量+重复+邮件）→ 仅对被拦项复核 → 按结果归档到 archive/rejected/redundant，并写 DB、报表。
