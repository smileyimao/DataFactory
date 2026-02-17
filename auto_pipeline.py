import matplotlib.pyplot as plt
import pandas as pd
import cv2
import numpy as np
import json
import os
import glob
from datetime import datetime
from tqdm import tqdm


class DataFactory:
    def __init__(self, input_dir="raw_video", output_base="data_warehouse"):
        self.input_dir = input_dir
        self.batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.batch_dir = os.path.join(output_base, f"Batch_{self.batch_id}")

        # 建立三级仓库结构
        self.pilot_dir = os.path.join(self.batch_dir, "pilot_samples")  # 留样区
        self.prod_dir = os.path.join(self.batch_dir, "production_data")  # 成品区
        os.makedirs(self.pilot_dir, exist_ok=True)
        os.makedirs(self.prod_dir, exist_ok=True)

    def get_video_files(self):
        extensions = ('*.mp4', '*.MP4', '*.mov', '*.MOV', '*.avi')
        files = []
        for ext in extensions:
            files.extend(glob.glob(os.path.join(self.input_dir, ext)))
        return files

    def analyze_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = np.mean(gray)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        std_dev = np.std(gray)
        env_tag = "Normal"
        if std_dev < 20:
            env_tag = "Low Visibility (Dust/Fog)"
        elif std_dev > 80:
            env_tag = "Harsh Light"
        return round(brightness, 2), round(blur_score, 2), env_tag

    def produce(self, is_pilot=True):
        """
        核心生产逻辑：不再拼凑 HTML 字符串，而是收集结构化数据
        """
        video_files = self.get_video_files()
        current_out_dir = self.pilot_dir if is_pilot else self.prod_dir
        mode_label = "🧪 [留样试制]" if is_pilot else "🚀 [全量投产]"

        # --- 重点修改1：创建一个空列表来装数据 ---
        stats_list = []

        for v_path in video_files:
            cap = cv2.VideoCapture(v_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            limit = int(fps * 5) if is_pilot else total_frames
            pbar = tqdm(total=limit, desc=f"{mode_label} {os.path.basename(v_path)}")

            frame_idx = 0
            while cap.isOpened() and frame_idx < limit:
                ret, frame = cap.read()
                if not ret: break

                if frame_idx % int(fps) == 0:
                    br, bl, env = self.analyze_frame(frame)
                    img_name = f"{os.path.basename(v_path)}_f{frame_idx:05d}.jpg"
                    cv2.imwrite(os.path.join(current_out_dir, img_name), frame)

                    # --- 重点修改2：把每一帧的数据“打包”存进列表 ---
                    stats_list.append({
                        "name": img_name,
                        "source": os.path.basename(v_path),
                        "br": br,
                        "bl": bl,
                        "env": env
                    })

                frame_idx += 1
                pbar.update(1)
            cap.release()
            pbar.close()

        report_path = self.generate_spc_report(stats_list, is_pilot)

    def generate_spc_report(self, stats_list, is_pilot):
        """
        分级交付报告系统：自动生成 HTML 和 JSON，并归类存放
        """
        df = pd.DataFrame(stats_list)
        total_count = len(df)
        finish_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 确定存放路径：试制区还是成品区
        target_dir = self.pilot_dir if is_pilot else self.prod_dir
        prefix = "pilot" if is_pilot else "final"

        # 1. 核心计算
        passed_df = df[(df['br'] >= 50) & (df['br'] <= 150)]
        fail_df = df[(df['br'] < 50) | (df['br'] > 150)]
        pass_rate = round((len(passed_df) / total_count) * 100, 2) if total_count > 0 else 0

        # 2. 绘制分布图 (存入对应文件夹)
        plt.figure(figsize=(10, 4))
        plt.subplot(1, 2, 1)
        plt.hist(df['br'], bins=20, color='skyblue', edgecolor='black')
        plt.axvline(50, color='red', linestyle='--')
        plt.axvline(150, color='red', linestyle='--')
        plt.title(f"{prefix.upper()} Brightness Distribution")

        plt.subplot(1, 2, 2)
        plt.hist(df['bl'], bins=20, color='salmon', edgecolor='black')
        plt.title(f"{prefix.upper()} Blur Score Distribution")

        plot_path = os.path.join(target_dir, f"{prefix}_distribution.png")
        plt.tight_layout()
        plt.savefig(plot_path)
        plt.close()

        # 3. 导出 JSON (给下游博士)
        json_path = os.path.join(target_dir, f"{prefix}_metadata.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            # 将 DataFrame 转换为博士们最喜欢的记录格式
            json.dump(stats_list, f, indent=4, ensure_ascii=False)

        # 4. 生成 HTML (给老板)
        fail_rows = ""
        for _, row in fail_df.iterrows():
            fail_rows += f"<tr><td>{row['name']}</td><td>{row['source']}</td><td>{row['br']}</td></tr>"

        html_content = f"""
        <html>
        <head><style>
            body {{ font-family: sans-serif; margin: 40px; }}
            .summary-box {{ background: #f8f9fa; padding: 20px; border-left: 5px solid navy; border-radius: 5px; }}
            .fail-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            .fail-table th, .fail-table td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            .fail-table th {{ background-color: #ff4d4d; color: white; }}
        </style></head>
        <body>
            <h1>🏭 {prefix.upper()} 阶段质量报告</h1>
            <div class="summary-box">
                <p><b>完成时间：</b> {finish_time}</p>
                <p><b>处理总数：</b> {total_count} 张切片</p>
                <p><b>合格率指标：</b> <span style="font-size: 20px; color: {'green' if pass_rate > 90 else 'red'};">{pass_rate}%</span></p>
                <p><b>技术附件：</b> 已生成 {prefix}_metadata.json 供下游调用</p>
            </div>
            <h3>📊 统计分布图</h3>
            <img src="{prefix}_distribution.png" width="800">
            <h3>🚫 异常溯源清单</h3>
            <table class="fail-table">
                <tr><th>图片名</th><th>来源视频</th><th>亮度异常值</th></tr>
                {fail_rows if fail_rows else "<tr><td colspan='3'>暂无异常，全部合格</td></tr>"}
            </table>
        </body></html>
        """
        report_path = os.path.join(target_dir, f"{prefix}_quality_report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return report_path  # 返回路径方便打印

    def run_control_panel(self):
        self.produce(is_pilot=True)
        # 现在的报告在 pilot_samples 文件夹里了
        report_url = os.path.abspath(os.path.join(self.pilot_dir, "pilot_quality_report.html"))
        print(f"\n📢 留样完成！样件包已封存。请查阅报告：file://{report_url}")

        # 步骤 2: 决策
        choice = input("\n❓ 样品质量是否合格？(y: 启动全量生产 / n: 停机整改): ").strip().lower()

        if choice == 'y':
            self.produce(is_pilot=False)
            print(f"\n✅ 任务结束。所有数据已存入成品区：{self.prod_dir}")
        else:
            print("\n🛑 生产指令撤回，请调整后再试。")


if __name__ == "__main__":
    factory = DataFactory()
    factory.run_control_panel()