# 黄金库 (Golden Library)

用于**开机黄金库自检**：在 `settings.yaml` 中开启 `startup_golden_run: true` 后，启动时会用本目录下的视频真跑一遍 QC，确保整条 pipeline 能跑通（边缘/生产环境建议开启）。

## 放置内容

- 放入 **1～2 个参考视频**（如 `.mov`、`.mp4`），体积不必大，能代表正常素材即可。
- 目录为空或未配置时，自检会**跳过**，不报错。

## 路径配置

- **默认**：`storage/golden`（相对项目根，与仓库一起）。
- **工业/边缘部署**：在 `config/settings.yaml` 的 `paths` 下设置 `golden` 为挂载点，例如：
  - 本机固定目录：`/opt/factory/golden`
  - NFS/共享盘：`/mnt/nfs/factory/golden`

同一套代码即可在开发用默认路径、在 edge 用挂载的黄金库。
