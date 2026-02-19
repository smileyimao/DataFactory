def boot_system():
    import os
    import sys
    # 强制后端
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['PYTHONUNBUFFERED'] = '1'

    # 动态路径挂载
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


class VideoFolderHandler(FileSystemEventHandler):
    def __init__(self):
        # 记录最后一次处理的时间，防止某些系统快速重复触发 created 事件
        self.last_triggered = 0
        self.debounce_seconds = 2

    def on_created(self, event):
        # 1. 过滤：只看文件，不看文件夹
        if event.is_directory:
            return

        # 2. 识别：只处理视频后缀
        if event.src_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            current_time = time.time()
            if current_time - self.last_triggered < self.debounce_seconds:
                return

            self.last_triggered = current_time

            print(f"\n📡 [保安报告]: 监测到新物料进入 -> {os.path.basename(event.src_path)}")

            # 3. 稳健性等待：
            # 文件刚创建时可能还在写入（特别是大视频或网络传输）
            # 我们等 5 秒，确保文件被锁定释放，工厂能正常打开视频
            print("⏳ 正在等待物料稳定入库 (5s)...")
            time.sleep(5)

            # 4. 执行：调用工厂指挥部
            try:
                # 传入 is_auto=True，确保不合格时自动熔断不卡住
                run_smart_factory(is_auto=True)
                print("\n✅ [保安报告]: 产线任务已移交工厂处理。")
                print("💡 [逻辑说明]: 原始文件应已被工厂搬运至 Batch 归档目录。")
            except Exception as e:
                print(f"❌ [保安异常]: 唤醒工厂失败: {e}")

            print(f"\n{'=' * 50}\n🛡️  保安继续巡逻中...")


if __name__ == "__main__":
    # 获取当前项目的 raw_video 路径
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WATCH_PATH = os.path.join(BASE_DIR, "raw_video")

    # 防呆：如果文件夹不存在则创建
    if not os.path.exists(WATCH_PATH):
        os.makedirs(WATCH_PATH)

    event_handler = VideoFolderHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_PATH, recursive=False)

    print(f"🚀 [DataFactory 自动工厂启动]")
    print(f"📍 监控路径: {WATCH_PATH}")
    print(f"🤖 运行模式: 自动感应 & 自动归档")
    print(f"📢 厂长提示: 只要往 raw_video 丢视频，产线就会自动跑起来！")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 保安已安全下班。")
    observer.join()