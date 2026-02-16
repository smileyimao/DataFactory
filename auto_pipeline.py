import cv2
import os
import glob
import json
import shutil
from datetime import datetime
from tqdm import tqdm

# ==========================================
# 厂长中控台：自动化配置
# ==========================================
RAW_DIR = 'raw_video'
WAREHOUSE_DIR = 'data_warehouse'
FRAME_INTERVAL = 30
RESIZE_WIDTH = 1280


def run_pipeline():
    base_path = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_path, RAW_DIR)
    warehouse_dir = os.path.join(base_path, WAREHOUSE_DIR)

    # 1. 扫描 raw_video
    video_files = []
    for ext in ['*.mp4', '*.MP4', '*.mov', '*.MOV']:
        video_files.extend(glob.glob(os.path.join(input_dir, ext)))

    if not video_files:
        print("📭 仓库空空如也，没有新货可以加工。")
        return

    for video_path in video_files:
        # 2. 为每一段视频准备“专属包间”
        video_filename = os.path.basename(video_path)
        video_pure_name = os.path.splitext(video_filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        batch_name = f"Batch_{video_pure_name}_{timestamp}"
        batch_path = os.path.join(warehouse_dir, batch_name)

        frames_dir = os.path.join(batch_path, 'frames')
        source_dir = os.path.join(batch_path, 'source')

        os.makedirs(frames_dir, exist_ok=True)
        os.makedirs(source_dir, exist_ok=True)

        print(f"\n🏗️  正在加工批次: {batch_name}")

        # 3. 开始切片加工
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        report = {"source": video_filename, "date": timestamp, "results": []}
        count = 0
        saved_count = 0

        with tqdm(total=total_frames // FRAME_INTERVAL, desc="生产中") as pbar:
            while True:
                success, frame = cap.read()
                if not success: break

                if count % FRAME_INTERVAL == 0:
                    # 质量分析与保存 (复用之前的逻辑)
                    img_name = f"frame_{saved_count:04d}.jpg"
                    save_path = os.path.join(frames_dir, img_name)

                    # 缩放处理
                    h, w = frame.shape[:2]
                    frame_resized = cv2.resize(frame, (RESIZE_WIDTH, int(h * RESIZE_WIDTH / w)))
                    cv2.imwrite(save_path, frame_resized)

                    report["results"].append({"file": img_name, "frame_index": count})
                    saved_count += 1
                    pbar.update(1)
                count += 1

        cap.release()

        # 4. 写入报告
        with open(os.path.join(batch_path, 'report.json'), 'w') as f:
            json.dump(report, f, indent=4)

        # 5. 【关键动作】原视频入库归档，清空收货区
        shutil.move(video_path, os.path.join(source_dir, video_filename))
        print(f"✅ 加工完成，原视频已归档至: {source_dir}")


if __name__ == "__main__":
    run_pipeline()