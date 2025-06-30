# mcp_server/default_tools/file_analysis_tool.py
import pandas as pd
import os
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from typing import Dict, Any
from server import mcp  # 保证引用的是 server.py 中的实例

from config import API_KEY, ENDPOINT

# 从你的项目配置中导入 API_KEY

try:
    from config import GOOGLE_API_KEY
except ImportError:
    print("Warning: config.py not found or GOOGLE_API_KEY not set. Attempting to use environment variable.")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_FALLBACK_GOOGLE_API_KEY_IF_ENV_NOT_SET")

@mcp.tool()
def analyze_csv_file(file_path: str, question: str) -> str:
    """
    【文件分析工具】此工具用于从指定的CSV文件中加载数据，并回答关于该数据的问题。
    它使用LangChain的Pandas DataFrame Agent来执行数据分析。

    Args:
        file_path (str): 需要被分析的CSV文件的本地路径。
        question (str): 关于该CSV文件内容的自然语言问题。

    Returns:
        str: 数据分析的结果，或错误信息。
    """
    print(f"--- [文件分析工具(Gemini) - 默认工具] 正在分析文件 '{file_path}'，问题: '{question}' ---")

    # 检查 GOOGLE_API_KEY 是否设置
    if not API_KEY or API_KEY == "YOUR_FALLBACK_GOOGLE_API_KEY_IF_ENV_NOT_SET":
        error_msg = "API_KEY 未设置或为默认值，无法调用模型进行文件分析。"
        print(f"--- [文件分析工具(Gemini) - 默认工具 ERROR] {error_msg} ---")
        return f"错误: {error_msg}"

    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"--- [文件分析工具(Gemini) ERROR] 文件未找到: '{file_path}' ---")
        return f"错误: 文件未找到，路径: '{file_path}'。"
    except Exception as e:
        print(f"--- [文件分析工具(Gemini) ERROR] 读取CSV文件时出错: {e} ---")
        return f"错误: 读取CSV文件时出错: {e}"

    llm = ChatOpenAI(
        model="google/gemini-2.5-pro",  # 使用最新的Gemini 2.5 Pro 模型
        temperature=0.1,
        api_key=API_KEY,
        base_url=ENDPOINT
    )
    # llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, google_api_key=GOOGLE_API_KEY)
    
    # 创建Pandas DataFrame Agent
    pandas_agent_executor = create_pandas_dataframe_agent(
        llm=llm,
        df=df,
        verbose=False, # 设置为True可以在控制台查看LLM生成的Python代码
        agent_executor_kwargs={"handle_parsing_errors": True}
    )

    print("--- [文件分析工具 - 安全警告] 即将执行由LLM生成的Python代码进行数据分析。 ---")
    try:
        # 调用 agent 执行分析
        result = pandas_agent_executor.invoke({"input": question})
        
        # Pandas DataFrame Agent 的结果通常在 "output" 键中
        output = result.get("output", "未能获得有效的输出。")
        print(f"--- [文件分析工具(Gemini)] 分析完成，结果: {output[:200]}... ---") # 截断部分结果日志
        return output
    except Exception as e:
        print(f"--- [文件分析工具(Gemini) ERROR] 执行Pandas代码分析时出错: {e} ---")
        return f"执行Pandas代码分析时出错: {e}"
