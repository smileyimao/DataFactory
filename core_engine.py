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
    # [配置存储器] 默认值
    config = {
        "min_brightness": 40.0,
        "max_brightness": 220.0,
        "min_blur_score": 15.0,
        "min_contrast": 15.0,
        "max_contrast": 95.0,
        "max_jitter": 35.0,
        "trial_limit_seconds": 5,
        "pass_rate_gate": 80.0,
        "save_normal": True,  # 是否保存合格品
        "save_warning": True  # 是否保存废片
    }

    email_config = {}

    @classmethod
    def load_config(cls, config_path="factory_config.yaml"):
        """加载配置逻辑保持不变，但增加对新开关的支持"""
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                    if content:
                        if 'quality_thresholds' in content:
                            cls.config.update(content['quality_thresholds'])
                        if 'production_setting' in content:
                            cls.config.update(content['production_setting'])
                        if 'email_setting' in content:
                            cls.email_config = content['email_setting']
                        print(f"✅ [配置中心] 同步成功！")
            except Exception as e:
                print(f"⚠️ [配置中心] 加载失败: {e}")

    @classmethod
    def qc_sensor(cls, frame: np.ndarray, prev_gray=None):
        """传感器逻辑：保持高灵敏度检测"""
        results: dict = {}
        cfg = cls.config
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            results['br'] = round(float(np.mean(gray)), 2)
            results['bl'] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)
            std_dev = np.std(gray)
            results['env'] = "Normal"

            if results['br'] < cfg['min_brightness']:
                results['env'] = "Too Dark"
            elif results['br'] > cfg['max_brightness']:
                results['env'] = "Harsh Light"
            elif results['bl'] < cfg['min_blur_score']:
                results['env'] = "Blurry"
            elif std_dev < cfg['min_contrast']:
                results['env'] = "Low Contrast"
            elif std_dev > cfg['max_contrast']:
                results['env'] = "High Contrast"

                # --- 💥 插件3：运动抖动检测与“赦免逻辑” ---
                results['jitter'] = 0.0
                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray)
                    results['jitter'] = round(float(np.mean(diff)), 2)

                    # 核心逻辑：如果抖动超标
                    if results['jitter'] > cfg['max_jitter']:
                        # 💡 检查是否足够清晰（赦免权：清晰度是及格线的 2.5 倍以上）
                        pardon_threshold = cfg['min_blur_score'] * 2.5
                        if results['bl'] > pardon_threshold:
                            results['env'] = "Normal (Jitter Pardoned)"
                        else:
                            results['env'] = "High Jitter"

            return results, gray
        except Exception as e:
            return {"br": 0, "bl": 0, "jitter": 0, "env": f"Error: {str(e)}"}, None


    @classmethod
    def start_production(cls, video_paths: List[str], target_dir: str, batch_id: str, limit_seconds: int = None):
        """
        V2.0 主传送带：引入【物理分拣立库】逻辑
        """
        all_stats = []

        # 1. 建立分拣立库文件夹
        normal_dir = os.path.join(target_dir, "Normal")
        warning_dir = os.path.join(target_dir, "Warning")
        os.makedirs(normal_dir, exist_ok=True)
        os.makedirs(warning_dir, exist_ok=True)

        for v_path in video_paths:
            v_name = os.path.basename(v_path)
            cap = cv2.VideoCapture(v_path)
            fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
            prev_gray_cache = None

            limit = fps * limit_seconds if limit_seconds else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            pbar = tqdm(total=limit, desc=f"⚙️ 加工: {v_name[:15]}")

            f_idx = 0
            while cap.isOpened() and f_idx < limit:
                ret, frame = cap.read()
                if not ret: break

                if f_idx % fps == 0:
                    # 质量诊断
                    qc_res, current_gray = cls.qc_sensor(frame, prev_gray_cache)
                    prev_gray_cache = current_gray

                    # --- 💥 V2.0 物理分拣逻辑 ---
                    img_name = f"{v_name}_f{f_idx:05d}.jpg"

                    if qc_res['env'] == "Normal":
                        save_path = os.path.join(normal_dir, img_name)
                        if cls.config.get('save_normal'):
                            cv2.imwrite(save_path, frame)
                    else:
                        # 废片打标并存入 Warning 仓
                        save_path = os.path.join(warning_dir, img_name)
                        if cls.config.get('save_warning'):
                            cv2.imwrite(save_path, frame)

                    # 记录信息
                    record = {"frame_id": f_idx, "filename": img_name, "source": v_name}
                    record.update(qc_res)
                    all_stats.append(record)

                f_idx += 1
                pbar.update(1)
            cap.release()
            pbar.close()

            # --- 💥 核心修改：加装“报表防火墙” ---
        try:
            # 2. 生成底账：数字化清单
            cls.generate_json_manifest(all_stats, target_dir)

            # 3. 筛选并生成“错题本”
            # 💡 这里的 item.get('env') 也是一种防呆，防止没有 env 键
            warning_list = [item for item in all_stats if item.get('env') != "Normal"]
            cls.generate_json_manifest(warning_list, target_dir, filename="warning_list.json")

            # 4. 生产报告
            cls.generate_html_report(all_stats, target_dir, batch_id, "Pilot" if limit_seconds else "Production")
            print(f"✅ [产线日志] 数字化清单与质量报告已生成完毕。")

        except Exception as e:
            # 即使上面这几步全崩了，也会抓取错误并打印，而不会停止程序
            print(f"⚠️ [产线告警] 报告生成环节出现异常，但图片分拣已完成: {e}")

        # 只要走到这一步，说明图片已经保存成功了，必须给厂长返回结果
        return len(all_stats)


    @staticmethod
    def generate_json_manifest(data_list: List[Any], target_path: str, filename="manifest.json"):
        """零件2：支持自定义文件名的底账机"""
        json_file = os.path.join(target_path, filename)
        with open(json_file, 'w', encoding='utf-8') as f:
            # 强制将 content 转为字符串再写入，或者直接使用 json.dump
            json_data = json.dumps(data_list, indent=4, ensure_ascii=False)
            f.write(str(json_data))  # 👈 显式转 str 确保兼容性
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

        # --- 💥 核心修复：防崩表格生成逻辑 ---
        # 使用 .get() 确保即便数据缺失（缺失 jitter 键）也不会崩掉
        rows_html = "".join([f'''
            <tr>
                <td>{c.get('source', 'Unknown')}</td>
                <td>{c.get('frame_id', 0)}</td>
                <td>{c.get('br', 0):.1f}</td>
                <td>{c.get('bl', 0):.1f}</td>
                <td>{c.get('jitter', 0):.1f}</td>
                <td class="status-bad">{c.get('env', 'Unknown')}</td>
                <td><code>{c.get('filename', 'N/A')}</code></td>
            </tr>
            ''' for c in bad_cases])

        # 4. 获取当前及格线，用于报告颜色显示
        current_gate = cls.config.get('pass_rate_gate', 80.0)

        # 5. 生成 HTML 字符串 (注意里面的 {rows_html} 引用)
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
                            <div class="kpi {'pass' if pass_rate >= current_gate else 'fail'}">
                                <h3>Pass Rate (Gate: {current_gate}%)</h3>
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
                                    {rows_html}
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
