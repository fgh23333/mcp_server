import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
llm_model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
API_KEY= os.getenv("API_KEY")
ENDPOINT = os.getenv("ENDPOINT")

# 服务器端口
SERVER_PORT = 8000

# 热重载工具存放目录
TOOLS_DIRECTORY = "tools"

# 默认工具存放目录
DEFAULT_TOOLS_DIRECTORY = "static_tools"

if not GOOGLE_API_KEY:
    raise ValueError("未找到 GOOGLE_API_KEY 环境变量。请在 .env 文件中设置。")
if not COHERE_API_KEY:
    raise ValueError("未找到 COHERE_API_KEY 环境变量。请在 .env 文件中设置。")
