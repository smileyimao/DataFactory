# Image 通路与自动模式判定（v2.10）

> 支持 YOLOv8 图片数据集全流程；raw 目录按内容自动选择 image/video 通路，无需手动改 config。

---

## 1. 概述

DataFactory 支持两种内容通路：

| 通路 | 扫描方式 | decode_check | QC 行为 | 输出 |
|------|----------|--------------|----------|------|
| **video** | 递归扫描 `video_extensions` | cv2.VideoCapture 首帧 | 帧率、时长、I-frame、blur、brightness、dedup | 抽帧切片 `xxx_f00000.jpg` |
| **image** | 递归扫描 `image_extensions` | cv2.imread | blur、brightness、dedup（跳过视频专用项） | 保持原名，同步复制 YOLO 标签 |

**自动判定**：当 `ingest.image_mode: "auto"` 时，`config_loader.get_content_mode()` 递归统计 raw 目录下图片/视频数量；**两者都有时返回 both（混合模式）**；仅一种时按数量多者；空目录默认 video。

---

## 2. 配置

| 键 | 说明 | 可选值 |
|----|------|--------|
| `ingest.image_mode` | 内容通路 | `"auto"`（默认）、`true`（强制图片）、`false`（强制视频）、`"both"`（混合，图片+视频都处理） |
| `ingest.image_extensions` | 图片扩展名 | `[".jpg", ".jpeg", ".png"]` |
| `ingest.video_extensions` | 视频扩展名 | `[".mp4", ".mov", ".avi", ".mkv"]` |

---

## 3. 目录结构（YOLOv8）

推荐将 Roboflow 导出的 YOLOv8 数据集放入 `storage/raw/`。**支持递归扫描**：可平铺、可子目录、可深层嵌套。

```
storage/raw/
  train/
    images/   ← .jpg 等
    labels/   ← .txt（YOLO 格式）
  valid/
    images/
    labels/
  test/
    images/
    labels/
```

也支持：`raw/项目A/2024-01/相机1/xxx.jpg`、`raw/deep/folder/sub/yyy.jpg` 等任意层级。

复制方式：

```bash
cp -r "数据集/train" "数据集/valid" "数据集/test" storage/raw/
```

---

## 4. 技术实现

### 4.1 自动判定

- **file_tools.detect_content_mode(directory, image_extensions, video_extensions)**  
  递归扫描目录，统计图片/视频数量；`n_img > n_vid` 返回 `"image"`，否则 `"video"`。

- **config_loader.get_content_mode(cfg)**  
  解析 `image_mode`：`true`→image，`false`→video，`auto`/未配置→调用 `detect_content_mode`。

### 4.2 标签路径

YOLO 格式约定：`.../images/xxx.jpg` 对应 `.../labels/xxx.txt`。

```python
# 从图片路径推导标签路径
label_path = os.path.join(
    os.path.dirname(os.path.dirname(img_path)),
    "labels",
    os.path.splitext(os.path.basename(img_path))[0] + ".txt"
)
```

### 4.3 涉及模块

| 模块 | 改动 |
|------|------|
| `engines/file_tools.py` | `detect_content_mode()`、`list_image_paths_recursive()`、`list_video_paths_recursive()` |
| `config/config_loader.py` | `get_content_mode()` |
| `core/ingest.py` | `get_video_paths()` 按 content_mode 选择扫描 |
| `engines/modality_handlers.py` | `_decode_check_image()`、`get_modality()` 使用 `get_content_mode` |
| `core/qc_engine.py` | image 时跳过视频专用 QC；移动图片时同步移动标签 |
| `engines/production_tools.py` | `_is_image_path()`、`_find_label_path()`；图片用 imread 单帧，复制标签 |
| `core/archiver.py` | 移动/复制图片时同步处理对应标签 |

---

## 5. 使用流程

1. 将 train/valid/test 放入 `storage/raw/`（保持 images/labels 结构）。
2. 保持 `ingest.image_mode: "auto"`（默认），或显式设为 `true`。
3. 运行 `python main.py --gate 50`（或 Guard 模式）。

Pipeline 会自动识别图片为主，走 image 通路，完成 QC、复核、归档，并将标签一并复制到 refinery/inspection。
