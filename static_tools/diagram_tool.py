import os
from mcp.server.fastmcp import Context
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from config import GOOGLE_API_KEY
from server import mcp  # 保证引用的是 server.py 中的实例

@mcp.tool()
def generate_mermaid_diagram(description: str, ctx: Context) -> str:
    """
    【图表专家工具】接收一段关于流程或结构的描述，并生成相应的Mermaid.js图表代码。
    例如，你可以要求它'画一个用户登录系统的流程图'。
    """
    key = GOOGLE_API_KEY or os.getenv("GOOGLE_API_KEY")
    if not key:
        ctx.error("GOOGLE_API_KEY 未配置")
        return "Error: API key not set"

    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "你是一位精通Mermaid.js的图表绘制专家。"
         "你的任务是将用户提供的文本描述，转换成一段完整、有效、可以直接渲染的Mermaid.js代码。"
         "规则:\n"
         "- 只输出Mermaid代码本身，不要包含任何解释性文字或Markdown代码块标记（例如 ```mermaid ... ```）。\n"
         "- 优先使用 `graph TD;` (从上到下) 的流程图布局。\n"
         "- 确保节点名称和连接关系准确地反映了用户的描述。"),
        ("user", "请为以下描述生成Mermaid代码: {description}")
    ])
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash", temperature=0, google_api_key=key
        )
        chain = prompt | llm
        res = chain.invoke({"description": description})
        code = res.content.strip()
        for mk in ("```mermaid", "```"):
            code = code.strip().strip(mk).strip()
        ctx.info("生成完毕")
        return code
    except Exception as e:
        ctx.error(f"生成失败：{e}")
        return f"Error: {e}"
