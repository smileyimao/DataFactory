import cv2
import os
import glob
import json
import datetime
from tqdm import tqdm

# ==========================================
# 厂长中控台：工业级配置
# ==========================================
# 相对路径：搬家后，Python 会在项目根目录下自动寻找
RAW_DIR = '../raw_video'
OUTPUT_DIR = '../output_frames'

# 生产参数
FRAME_INTERVAL = 30  # 每30帧采样一次（约1秒1张）
MAX_FRAMES_TOTAL = 300  # 熔断器：单次任务上限，保护硬盘
RESIZE_WIDTH = 1280  # 图像尺寸标准化

# 质检阈值
BRIGHTNESS_THRESHOLD = 40  # 亮度低于此值将被标记为 "Too Dark"


# ==========================================

def get_image_quality(frame):
    """计算图像质量：亮度与模糊度"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = round(float(gray.mean()), 2)
    # 拉普拉斯方差：值越高越清晰
    blur_score = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)
    return brightness, blur_score


def industrial_run():
    # 1. 路径自动对齐 (解决 OneDrive 等路径偏移问题)
    base_path = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_path, RAW_DIR)
    output_path = os.path.join(base_path, OUTPUT_DIR)

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # 2. 扫描视频文件 (大小写兼容模式)
    patterns = ['*.mov', '*.MOV', '*.mp4', '*.MP4']
    video_files = []
    for p in patterns:
        video_files.extend(glob.glob(os.path.join(input_path, p)))

    if not video_files:
        print(f"❌ 找不到货！请检查文件夹：{input_path}")
        return

    video_path = video_files[0]
    video_name = os.path.basename(video_path)
    print(f"🏗️ 生产线启动：正在处理 {video_name}")

    # 3. 初始化视频流
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 4. 准备元数据报告 (工业凭证)
    report = {
        "project": "Mazda_Data_Factory",
        "timestamp": str(datetime.datetime.now()),
        "source": video_name,
        "results": []
    }

    count = 0
    saved_count = 0

    # 5. 核心生产循环
    with tqdm(total=min(total_frames // FRAME_INTERVAL, MAX_FRAMES_TOTAL), desc="切片质检中") as pbar:
        while True:
            success, frame = cap.read()
            if not success or saved_count >= MAX_FRAMES_TOTAL:
                break

            if count % FRAME_INTERVAL == 0:
                # 图像处理：缩放
                if RESIZE_WIDTH:
                    h, w = frame.shape[:2]
                    frame = cv2.resize(frame, (RESIZE_WIDTH, int(h * RESIZE_WIDTH / w)))

                # 质检分析
                brightness, blur = get_image_quality(frame)
                status = "PASS" if brightness > BRIGHTNESS_THRESHOLD else "FAIL_DARK"

                # 保存成品
                file_name = f"frame_{saved_count:04d}.jpg"
                cv2.imwrite(os.path.join(output_path, file_name), frame)

                # 记录元数据
                report["results"].append({
                    "file": file_name,
                    "brightness": brightness,
                    "blur_score": blur,
                    "status": status
                })

                saved_count += 1
                pbar.update(1)

            count += 1

    cap.release()

    # 6. 导出 JSON 质检报告
    report_path = os.path.join(base_path, "batch_metadata.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)

    print(f"\n✅ 任务圆满完成！")
    print(f"📦 产出数量：{saved_count} 张图像")
    print(f"📄 质检报告：{report_path}")


if __name__ == "__main__":
    industrial_run()