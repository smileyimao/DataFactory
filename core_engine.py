import cv2
import numpy as np
import os
import yaml
import json
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime
from tqdm import tqdm
from typing import Any, List


class DataMachine:
    # 🧠 [配置存储器] 保命默认值，即使config丢失，工厂照样可以生产
    config = {
        "min_brightness": 40.0,
        "max_brightness": 220.0,
        "min_blur_score": 15.0,
        "min_contrast": 15.0,
        "max_contrast": 95.0,
        "max_jitter": 35.0,
        "trial_limit_seconds": 5,
        "pass_rate_gate": 80.0,
    }

    # 📧 [邮件配置存储器]：新增，默认为空字典
    email_config = {}

    @classmethod
    def load_config(cls, config_path="factory_config.yaml"):
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                    if content:
                        # 1. 质检标准
                        if 'quality_thresholds' in content:
                            cls.config.update(content['quality_thresholds'])

                        # 2. 生产控制 (只要 YAML 顶格写了，这里就能读到)
                        if 'production_setting' in content:
                            cls.config.update(content['production_setting'])

                        # 3. 邮件配置
                        if 'email_setting' in content:
                            cls.email_config = content['email_setting']

                        # 🛠️ 厂长专属调试：看看现在大脑里到底记了多少秒
                        print(f"✅ [配置中心] 同步成功！当前试产时长：{cls.config.get('trial_limit_seconds')}s")
            except Exception as e:
                print(f"⚠️ [配置中心] 加载失败: {e}")

    @classmethod
    def qc_sensor(cls, frame: np.ndarray, prev_gray=None):
        """
        [感知诊断中心]：已升级为配置驱动版
        """
        results: dict = {}
        cfg = cls.config  # 👈 引用当前大脑中的配置

        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # 插件1：基础物理质检
            results['br'] = round(float(np.mean(gray)), 2)
            results['bl'] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)

            # 插件2：环境判断（使用配置动态判定）
            std_dev = np.std(gray)
            results['env'] = "Normal"

            # --- 💥 核心防呆拦截逻辑 ---
            if results['br'] < cfg['min_brightness']:
                results['env'] = "Too Dark"
            elif results['br'] > cfg['max_brightness']:
                results['env'] = "Harsh Light"
            elif results['bl'] < cfg['min_blur_score']:
                results['env'] = "Blurry / Out of Focus"  # 👈 专门抓刚才那种模糊废片
            elif std_dev < cfg['min_contrast']:
                results['env'] = "Low Contrast"
            elif std_dev > cfg['max_contrast']:
                results['env'] = "High Contrast"

            # 插件3：机器人运动抖动
            results['jitter'] = 0.0
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                results['jitter'] = round(float(np.mean(diff)), 2)
                # 使用配置中的抖动阈值
                if results['jitter'] > cfg['max_jitter']:
                    results['env'] = "High Jitter"

            return results, gray
        except Exception as e:
            return {"br": 0, "bl": 0, "jitter": 0, "env": f"Error: {str(e)}"}, None

    @staticmethod
    def generate_json_manifest(data_list: List[Any], target_path: str):
        """零件2：数字化底账机"""
        json_file = os.path.join(target_path, "manifest.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            # 这里是 PyCharm 报黄线的地方，我们显式调用 f
            content = json.dumps(data_list, indent=4, ensure_ascii=False)
            f.write(content)
        return json_file

    @classmethod
    def generate_html_report(cls, data_list, target_path, batch_id, mode):
        html_file = os.path.join(target_path, "quality_report.html")

        # 1. 建立 DataFrame
        df = pd.DataFrame(data_list)
        total = len(df)

        # --- 🚀 核心消红：改用 Python 内置函数，不给 IDE 报错的机会 ---
        # 统计 'env' 列里有多少个 'Normal'
        normal_count = len(df[df['env'] == 'Normal'])
        pass_rate = (normal_count / total * 100) if total > 0 else 0

        # 2. 视频分项统计 (改用另一种写法，消灭 Mean 报错)
        video_report = df.groupby('source')['br'].agg('mean')

        # 💡 这里是将统计表转为 HTML 的关键一步
        stats_table_html = video_report.to_frame(name='Avg Brightness').to_html(
            classes='table',
            float_format=lambda x: f"{x:.2f}"
        )

        # 3. 提取图表数据
        brs = df['br'].tolist()
        bls = df['bl'].tolist()
        bad_cases = df[df['env'] != 'Normal'].to_dict('records')

        html_content = f"""
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Datafactory Quality Report</title>
                    <style>
                        body {{ font-family: sans-serif; margin: 40px; background: #f4f7f6; color: #333; }}
                        .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }}
                        .kpi-box {{ display: flex; gap: 20px; }}
                        .kpi {{ flex: 1; text-align: center; padding: 20px; border-radius: 8px; color: white; }}
                        .pass {{ background: #2ecc71; }}
                        .fail {{ background: #e74c3c; }}
                        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                        th {{ background: #34495e; color: white; }}
                        .status-bad {{ color: #e74c3c; font-weight: bold; }}
                    </style>
                </head>
                <body>
                    <h1>🏗️ Datafactory Production Report ({mode})</h1>
                    <p>Batch ID: {batch_id} | Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

                    <div class="kpi-box">
                        <div class="kpi {'pass' if pass_rate > 80 else 'fail'}">
                            <h3>Pass Rate</h3>
                            <h2 style="font-size: 40px;">{pass_rate:.2f}%</h2>
                        </div>
                        <div class="kpi" style="background: #3498db;">
                            <h3>Total Samples</h3>
                            <h2 style="font-size: 40px;">{total}</h2>
                        </div>
                    </div>

                    <div class="card">
                        <h3>📽️ Per-Video Quality Overview (Average Brightness)</h3>
                        {stats_table_html}
                    </div>

                    <div class="card">
                        <h3>📊 Quality Distribution Chart</h3>
                        {cls._get_plot_base64(brs, bls)}
                    </div>

                    <div class="card">
                        <h3>🚫 Bad Case Traceability ({len(bad_cases)} items)</h3>
                        <table>
                            <thead>
                                <tr>
                                    <th>Source Video</th>
                                    <th>Frame ID</th>
                                    <th>Brightness (BR)</th>
                                    <th>Blur (BL)</th>
                                    <th>Jitter</th>
                                    <th>Judgment</th>
                                    <th>Filename</th>
                                </tr>
                            </thead>
                            <tbody>
                                {"".join([f'''
                                <tr>
                                    <td>{c['source']}</td>
                                    <td>{c['frame_id']}</td>
                                    <td>{c['br']:.1f}</td>
                                    <td>{c['bl']:.1f}</td>
                                    <td>{c['jitter']:.1f}</td>
                                    <td class="status-bad">{c['env']}</td>
                                    <td><code>{c['filename']}</code></td>
                                </tr>
                                ''' for c in bad_cases])}
                            </tbody>
                        </table>
                    </div>
                </body>
                </html>
                """
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        return html_file

    @classmethod
    def _get_plot_base64(cls, brs, bls):
        """核心绘图零件：将Matplotlib图表直接转化为HTML可读的字符串"""

        # 创建一个 10x4 的画布
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

        # 1. 亮度分布直方图 (保持昨天的配色一致性)
        ax1.hist(brs, bins=20, color='skyblue', edgecolor='white')
        ax1.set_title("Brightness Dist")
        ax1.set_xlabel("Value")
        ax1.set_ylabel("Count")

        # 2. 模糊度分布直方图 (保持昨天的配色一致性)
        ax2.hist(bls, bins=20, color='salmon', edgecolor='white')
        ax2.set_title("Blur Dist")
        ax2.set_xlabel("Value")

        plt.tight_layout()

        # 将图片保存到内存缓冲区，不产生任何实体 png 文件
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close(fig)

        # 编码为 Base64
        base64_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f'<img src="data:image/png;base64,{base64_str}" style="width:100%;">'

    @classmethod
    def start_production(cls, video_paths: List[str], target_dir: str, batch_id: str, limit_seconds: int = None):
        """主传送带（升级版）：支持字典扩展与帧缓存"""
        all_stats = list()
        os.makedirs(target_dir, exist_ok=True)

        for v_path in video_paths:
            v_name = os.path.basename(v_path)
            cap = cv2.VideoCapture(v_path)
            fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25

            # --- 💥 新增：初始化上一帧缓存，用于抖动检测 ---
            prev_gray_cache = None

            limit = fps * limit_seconds if limit_seconds else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            pbar = tqdm(total=limit, desc=f"⚙️ 加工: {v_name[:15]}")

            f_idx = 0
            while cap.isOpened() and f_idx < limit:
                ret, frame = cap.read()
                if not ret:
                    break

                if f_idx % fps == 0:
                    h, w = frame.shape[:2]
                    new_h = int(h * 1280 / w)
                    frame = cv2.resize(frame, (1280, new_h))

                    # --- 💥 核心修改 1：调用 qc_sensor 并传入缓存 ---
                    # 现在的 qc_sensor 返回两个东西：一个是数据字典，一个是当前的灰度图
                    qc_res, current_gray = cls.qc_sensor(frame, prev_gray_cache)
                    prev_gray_cache = current_gray  # 👈 把现在的灰度图存起来，留给下一秒用

                    img_name = f"{v_name}_f{f_idx:05d}.jpg"
                    cv2.imwrite(os.path.join(target_dir, img_name), frame)

                    # --- 💥 核心修改 2：使用 ** 解包字典 ---
                    record = {
                        "frame_id": f_idx,
                        "filename": img_name,
                        "source": v_name
                    }
                    record.update(qc_res)  # 👈 将字典里的 br, bl, jitter, env 全部合并进来
                    all_stats.append(record)

                f_idx += 1
                pbar.update(1)
            cap.release()
            pbar.close()

        cls.generate_json_manifest(all_stats, target_dir)
        cls.generate_html_report(all_stats, target_dir, batch_id, "Pilot" if limit_seconds else "Production")
        return len(all_stats)