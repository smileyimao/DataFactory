import cv2
import os
import glob
import datetime
import time
import pandas as pd
import matplotlib.pyplot as plt
from tqdm import tqdm
import io  # 新增：用于内存操作
import base64  # 新增：用于图片编码

class DataFactory:
    def __init__(self, input_dir="../raw_video", output_base="../data_warehouse"):
        # 1. 路径自动对齐
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.input_dir = os.path.join(self.base_path, input_dir)
        self.batch_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.batch_dir = os.path.join(self.base_path, output_base, f"Batch_{self.batch_id}")

        # 建立三级仓库
        self.pilot_dir = os.path.join(self.batch_dir, "pilot_samples")
        self.prod_dir = os.path.join(self.batch_dir, "production_data")
        os.makedirs(self.pilot_dir, exist_ok=True)
        os.makedirs(self.prod_dir, exist_ok=True)

    def analyze_frame(self, frame):
        """质检工位"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = round(float(gray.mean()), 2)
        blur_score = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)
        return brightness, blur_score

    def produce(self, is_pilot=True):
        """核心生产线 (这就是你要找的函数！)"""
        start_time = time.time()  # --- Kaizen: 开始计时 ---

        # 寻找货源
        patterns = ['*.mov', '*.MOV', '*.mp4', '*.MP4']
        video_files = []
        for p in patterns:
            video_files.extend(glob.glob(os.path.join(self.input_dir, p)))

        if not video_files:
            print(f"❌ 找不到货！请检查文件夹：{self.input_dir}")
            return

        current_out_dir = self.pilot_dir if is_pilot else self.prod_dir
        mode_label = "🧪 [留样试制]" if is_pilot else "🚀 [全量投产]"

        stats_list = []
        processed_count = 0

        # 生产参数
        interval = 30
        max_frames = 50 if is_pilot else 500  # 熔断器：试制50张，全量500张
        resize_width = 1280

        for v_path in video_files:
            cap = cv2.VideoCapture(v_path)
            total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            pbar = tqdm(total=min(total_f // interval, max_frames), desc=f"{mode_label} {os.path.basename(v_path)}")

            count = 0
            while cap.isOpened() and processed_count < max_frames:
                success, frame = cap.read()
                if not success: break

                if count % interval == 0:
                    # 标准化加工：Resizing
                    h, w = frame.shape[:2]
                    frame = cv2.resize(frame, (resize_width, int(h * resize_width / w)))

                    # 质检
                    br, bl = self.analyze_frame(frame)
                    img_name = f"{os.path.basename(v_path)}_f{count:05d}.jpg"
                    cv2.imwrite(os.path.join(current_out_dir, img_name), frame)

                    stats_list.append({
                        "name": img_name, "source": os.path.basename(v_path),
                        "br": br, "bl": bl
                    })
                    processed_count += 1
                    pbar.update(1)
                count += 1
            cap.release()
            pbar.close()

        # --- Kaizen: 效率计算 ---
        end_time = time.time()
        duration = end_time - start_time
        metrics = {
            "duration": round(duration, 2),
            "avg_cycle_time": round(duration / processed_count, 4) if processed_count > 0 else 0,
            "throughput_min": round(processed_count / (duration / 60), 2) if duration > 0 else 0
        }

        self.generate_spc_report(stats_list, is_pilot, metrics)

    def generate_spc_report(self, stats_list, is_pilot, metrics):
        """SPC 质量与效率整合报告 (单体 HTML 模式)"""
        df = pd.DataFrame(stats_list)
        target_dir = self.pilot_dir if is_pilot else self.prod_dir
        prefix = "pilot" if is_pilot else "final"
        finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- 1. 绘图 (内存模式) ---
        plt.figure(figsize=(10, 4))
        plt.subplot(1, 2, 1)
        plt.hist(df['br'], bins=20, color='skyblue')
        plt.title("Brightness Dist")

        plt.subplot(1, 2, 2)
        plt.hist(df['bl'], bins=20, color='salmon')
        plt.title("Blur Dist")

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')

        # --- 2. 筛选逻辑 ---
        fail_df = df[(df['br'] < 50) | (df['br'] > 150) | (df['bl'] < 500)]
        pass_rate = round(((len(df) - len(fail_df)) / len(df)) * 100, 2) if len(df) > 0 else 0

        # --- 3. 构造表格行 ---
        fail_rows = ""
        for _, row in fail_df.iterrows():
            br_style = 'style="color:red"' if (row['br'] < 50 or row['br'] > 150) else ""
            bl_style = 'style="color:red"' if row['bl'] < 500 else ""

            fail_rows += f"""
                <tr>
                    <td>{row['name']}</td>
                    <td>{row['source']}</td>
                    <td {br_style}>{row['br']}</td>
                    <td {bl_style}>{row['bl']}</td>
                </tr>"""

        # --- 4. 生成 HTML (注意：这一行必须和上面的 'for' 垂直对齐！) ---
        html_content = f"""
        <html>
        <head><style>
            body {{ font-family: sans-serif; margin: 40px; color: #333; }}
            .summary-box {{ background: #f8f9fa; padding: 20px; border-left: 5px solid navy; border-radius: 5px; margin-bottom: 20px; }}
            .efficiency-box {{ background: #eef9f0; padding: 20px; border-left: 5px solid #28a745; border-radius: 5px; margin-bottom: 20px; }}
            .fail-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            .fail-table th, .fail-table td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            .fail-table th {{ background-color: #ff4d4d; color: white; }}
            .status-pass {{ color: green; font-weight: bold; font-size: 24px; }}
            .status-fail {{ color: red; font-weight: bold; font-size: 24px; }}
        </style></head>
        <body>
            <h1>🏭 {prefix.upper()} 阶段质量与效率报告</h1>
            <div class="summary-box">
                <h3>📊 质量看板</h3>
                <p><b>完成时间：</b> {finish_time}</p>
                <p><b>处理总数：</b> {len(df)} 张切片</p>
                <p><b>FPY (直通率)：</b> <span class="{'status-pass' if pass_rate > 90 else 'status-fail'}">{pass_rate}%</span></p>
            </div>
            <div class="efficiency-box">
                <h3>⚡ Kaizen 效率看板</h3>
                <ul>
                    <li><b>总加工耗时：</b> {metrics['duration']} 秒</li>
                    <li><b>单件循环时间 (Cycle Time)：</b> {metrics['avg_cycle_time']} 秒/张</li>
                    <li><b>生产吞吐率 (Throughput)：</b> {metrics['throughput_min']} 张/分钟</li>
                </ul>
            </div>
            <h3>📈 统计分布图</h3>
            <img src="data:image/png;base64,{img_base64}" width="800">
            <h3>🚫 异常溯源清单 (亮度 <50/>150 或 模糊 <500)</h3>
            <table class="fail-table">
                <tr><th>图片名</th><th>来源视频</th><th>亮度值</th><th>模糊度</th></tr>
                {fail_rows if fail_rows else "<tr><td colspan='4'>🎉 暂无异常，全部合格</td></tr>"}
            </table>
        </body></html>
        """

        # --- 5. 写入文件 ---
        report_path = os.path.join(target_dir, f"{prefix}_quality_report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        # --- 6. 补齐 JSON 底账 (博士和下游算法需要它) ---
        df.to_json(os.path.join(target_dir, f"{prefix}_metadata.json"), orient="records", indent=4)

    def run_control_panel(self):
        print(f"🚀 Mazda 数据工厂 {self.batch_id} 启动...")

        # 1. 试生产
        self.produce(is_pilot=True)
        report_url = os.path.abspath(os.path.join(self.pilot_dir, "pilot_quality_report.html"))
        print(f"\n📢 留样完成！样件包已封存。")
        print(f"🔗 请立即核查报告：file://{report_url}")

        # 2. 防错判断
        while True:
            choice = input("\n❓ 留样合格吗？[y: 启动全量生产 / n: 停机整改 / q: 退出]: ").strip().lower()
            if choice == 'y':
                print("▶️ 全量生产线点火！")
                self.produce(is_pilot=False)
                final_report = os.path.abspath(os.path.join(self.prod_dir, "final_quality_report.html"))
                print(f"✅ 全量产线完工！报告地址：file://{final_report}")
                break
            elif choice in ['n', 'q']:
                print("🛑 生产任务终止。")
                break
            else:
                print("⚠️ 指令无效，请输入 y/n/q")

if __name__ == "__main__":
    factory = DataFactory()
    factory.run_control_panel()