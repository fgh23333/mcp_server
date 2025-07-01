import os
import glob
import importlib.util
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

os.environ["FASTMCP_PORT"] = "8000"
from mcp.server.fastmcp import FastMCP

# 初始化 MCP 服务器实例
mcp = FastMCP("Demo")

# 定义工具目录
# 不会热重载的静态工具目录（例如你的元工具）
STATIC_TOOLS_DIR = "static_tools"  
# 会被热重载的工具目录（例如 AI 生成的工具）
HOT_RELOAD_TOOLS_DIR = "tools"     

def load_tools_from_dir(dir_path: str):
    """
    从指定目录加载工具模块。
    这个函数会在服务器启动时和热重载时被调用。
    """
    full_dir = os.path.join(os.path.dirname(__file__), dir_path)
    if not os.path.isdir(full_dir):
        print(f"警告: 未找到工具目录: {full_dir}")
        return

    print(f"正在从以下目录加载工具: {full_dir}")
    for path in glob.glob(os.path.join(full_dir, "*.py")):
        name = os.path.splitext(os.path.basename(path))[0]
        if name.startswith("_"):
            continue  # 忽略私有文件 (例如 __init__.py)

        try:
            # 创建一个唯一的模块名来避免重载时的冲突
            # 这对于 Python 的导入系统识别变化至关重要
            module_name = f"{dir_path}.{name}.{time.time_ns()}" 
            spec = importlib.util.spec_from_file_location(module_name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            print(f"成功加载工具模块: {dir_path}/{name}.py")
        except Exception as e:
            print(f"[错误] 加载 {dir_path}/{name}.py 失败: {e}")

### 热重载事件处理器 (Watchdog)

class ToolReloaderHandler(FileSystemEventHandler):
    def __init__(self, mcp_instance: FastMCP, hot_reload_dir: str):
        super().__init__()
        self.mcp_instance = mcp_instance
        self.hot_reload_dir = hot_reload_dir
        self.last_reload_time = time.time()
        # 防抖时间，防止单次保存操作触发多次重载
        self.reload_debounce_seconds = 0.5 

    def on_any_event(self, event):
        # 只关心 Python 文件的创建、修改或删除事件
        if event.is_directory:
            return
        if not event.src_path.endswith(".py"):
            return
        
        # 防抖处理：在短时间内只进行一次重载
        current_time = time.time()
        if current_time - self.last_reload_time < self.reload_debounce_seconds:
            return
        
        print(f"\n--- 检测到 {event.src_path} 文件变化，正在重载工具... ---")
        self.last_reload_time = current_time

        # 执行重载逻辑：
        # 最简单的方法是重新初始化 FastMCP 实例，这样会清除所有旧的工具注册。
        # 对于生产环境，如果 MCP 实例维护了其他重要状态，可能需要更精细的
        # unregister/re-register 机制 (例如 mcp.unregister_tool(tool_name))。
        global mcp
        print("重新初始化 FastMCP 以清除旧工具...")
        mcp = FastMCP("Demo") # 重新创建 FastMCP 实例

        # load_tools_from_dir(STATIC_TOOLS_DIR)
        load_tools_from_dir(HOT_RELOAD_TOOLS_DIR)
        print("--- 工具重载成功！ ---")

### 服务器启动和运行

# --- 初始加载工具 ---
print("--- 正在进行初始工具加载... ---")
load_tools_from_dir(STATIC_TOOLS_DIR)
load_tools_from_dir(HOT_RELOAD_TOOLS_DIR)
print("--- 初始工具加载完成。 ---")

# --- 设置热重载 (Watchdog) ---
event_handler = ToolReloaderHandler(mcp, HOT_RELOAD_TOOLS_DIR)
observer = Observer()
# 监听 HOT_RELOAD_TOOLS_DIR 目录，recursive=True 表示递归监听子目录
observer.schedule(event_handler, HOT_RELOAD_TOOLS_DIR, recursive=True)
observer.start()
print(f"正在递归监听目录 '{HOT_RELOAD_TOOLS_DIR}' 的文件变化...")

# --- 运行 MCP 服务器 ---
try:
    print("\n--- 正在启动 MCP 服务器... ---")
    mcp.run(transport="sse")
except KeyboardInterrupt:
    print("\n--- 正在停止 MCP 服务器... ---")
    observer.stop() # 停止 watchdog 观察者
observer.join() # 等待观察者线程结束
print("--- 服务器已停止，监视器已终止。 ---")
