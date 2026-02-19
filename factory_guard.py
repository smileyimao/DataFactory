def boot_system():
    import os
    import sys
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['PYTHONUNBUFFERED'] = '1'
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.append(project_root)


# 执行引导
boot_system()

import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from main_factory import run_smart_factory
# 👈 [新增]：引入档案馆零件
from db_manager import init_db, get_file_md5


class VideoFolderHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_triggered = 0
        self.debounce_seconds = 2
        # 这里的 processed_files 依然保留，作为内存里的“第一道防线”，防止系统虚警
        self.processed_files = set()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        file_name = os.path.basename(file_path)

        # --- 保险 A：后缀过滤 & 黑名单校验 ---
        if file_name.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            if file_name in self.processed_files:
                return

            current_time = time.time()
            if current_time - self.last_triggered < self.debounce_seconds:
                return
            self.last_triggered = current_time

            print(f"\n📡 [保安报告]: 监测到新物料进入 -> {file_name}")

            # --- 保险 B：动态稳定检查 ---
            print("⏳ 正在检查物料完整性（确保文件传输完成）...")
            last_size = -1
            while True:
                try:
                    current_size = os.path.getsize(file_path)
                    if current_size == last_size and current_size > 0:
                        break
                    last_size = current_size
                    time.sleep(1)
                except (FileNotFoundError, OSError):
                    break

            # 👈 [新增]：采集指纹 (MD5)
            # 在唤醒工厂前，先拿到文件的身份证号
            print(f"🧬 [指纹采集]: 正在生成物料数字指纹...")
            fingerprint = get_file_md5(file_path)

            # --- 执行：唤醒工厂 ---
            try:
                # 👈 [修改]：将指纹作为参数传递给工厂
                run_smart_factory(file_md5=fingerprint)

                # 确认任务移交后，再加入内存黑名单
                self.processed_files.add(file_name)
                print(f"✅ [保安报告]: {file_name} 任务已移交。")
                print(f"💡 [名单状态]: 目前内存黑名单中有 {len(self.processed_files)} 个文件。")
            except Exception as e:
                print(f"❌ [保安异常]: 唤醒工厂失败: {e}")

            print(f"\n{'=' * 50}\n🛡️  保安继续巡逻中...")


if __name__ == "__main__":
    # 👈 [新增]：系统启动时，档案馆长先检查数据库状态
    init_db()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WATCH_PATH = os.path.join(BASE_DIR, "raw_video")

    if not os.path.exists(WATCH_PATH):
        os.makedirs(WATCH_PATH)

    event_handler = VideoFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_PATH, recursive=False)

    print(f"🚀 [DataFactory 自动工厂启动]")
    print(f"📍 监控路径: {WATCH_PATH}")
    print(f"🤖 运行模式: 自动感应 & 指纹识别")  # 👈 小改动
    print(f"📢 厂长提示: 只要往 raw_video 丢视频，产线就会自动跑起来！")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 保安已安全下班。")
    observer.join()