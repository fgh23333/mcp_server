import os
import importlib.util
import tempfile
import traceback
import re
import datetime
from typing import Dict, Any, Optional, List

from server import mcp # 保证引用的是 server.py 中的 mcp 实例
from loguru import logger

# LangChain 和 LangGraph 相关的导入
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END, START
from pydantic import BaseModel, Field, ValidationError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from config import API_KEY, ENDPOINT

# 从你的项目配置中导入 GOOGLE_API_KEY
try:
    from config import GOOGLE_API_KEY
except ImportError:
    logger.warning("config.py not found or GOOGLE_API_KEY not set. Attempting to use environment variable.")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_FALLBACK_GOOGLE_API_KEY_IF_ENV_NOT_SET")

# --- LangGraph Agent State Definition ---
class SimpleMetaToolAgentState(BaseModel):
    messages: List[HumanMessage] = Field(default_factory=list, description="Agent的对话历史和当前输入/输出。")
    generated_code: Optional[str] = Field(default=None, description="上一次生成的工具代码。")
    tool_name: Optional[str] = Field(default=None, description="本次要生成的工具名称。")
    retries: int = Field(default=0, description="代码生成和测试的重试次数。")
    max_retries: int = Field(default=3, description="最大重试次数。")


# --- SimpleMetaToolAgent Class (Internal Logic) ---
class SimpleMetaToolAgent:
    # 构造函数不再接收 ctx
    def __init__(self, api_key: str):
        self.api_key = api_key

        if not self.api_key or self.api_key == "YOUR_FALLBACK_GOOGLE_API_KEY_IF_ENV_NOT_SET":
            logger.error("api_key 未设置或为默认值，SimpleMetaToolAgent 将无法正常工作。")
            self.model = None
        else:
            self.model = ChatOpenAI(
                model="google/gemini-2.5-pro", 
                temperature=0.1,
                api_key=API_KEY, 
                base_url=ENDPOINT
            )
            # self.model = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.1, google_api_key=self.google_api_key)
        
        self.graph = self._build_graph()
        logger.info("SimpleMetaToolAgent 初始化完成。") # 仅打印到服务器终端

    def _generate_tool_name(self, user_request: str) -> str:
        """
        使用大模型根据用户需求自动生成合理的工具名称。
        """
        if self.model is None:
            # 回退到时间戳命名
            return f"generated_tool_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        prompt = (
            "你是一位专业的Python工具命名专家。请根据以下工具需求，为该工具生成一个简洁、专业、易懂的英文函数名（仅小写字母、数字和下划线，必须以字母开头，不能有空格，不能有中文，不能有特殊字符，不能以test、tmp、demo等无意义词开头，不能超过30字符），直接输出函数名即可，不要加任何解释说明：\n"
            f"{user_request}\n"
        )
        try:
            response = self.model.invoke([HumanMessage(content=prompt)]).content.strip()
            # 只取首行，去除多余内容
            tool_name = response.splitlines()[0]
            tool_name = tool_name.strip()
            # 规范化
            tool_name = re.sub(r'[^a-zA-Z0-9_]', '', tool_name)
            tool_name = tool_name.lower()
            if tool_name and tool_name[0].isalpha() and len(tool_name) <= 30:
                return tool_name
        except Exception as e:
            logger.warning(f"LLM命名失败，回退到时间戳命名。错误: {e}")
        return f"generated_tool_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _tool_writer_node(self, state: SimpleMetaToolAgentState) -> SimpleMetaToolAgentState:
        # 不再使用 self.ctx，直接在 state.messages 中记录
        logger.info(f"节点: 1. 编写工具代码 (重试次数: {state.retries})")
        
        if self.model is None:
            # 直接返回包含错误消息的状态
            return state.copy(update={"messages": state.messages + [HumanMessage(content="错误：SimpleMetaToolAgent 未能初始化，因为 GOOGLE_API_KEY 未设置。")]})

        user_request = state.messages[0].content
        current_messages = state.messages

        tool_name = state.tool_name
        if not tool_name:
            tool_name = self._generate_tool_name(user_request)
            logger.info(f"    -> 生成工具名称：{tool_name}")

        system_prompt_content = (
             "你是一位顶级的Python开发专家，精通MCP（Model Context Protocol）工具的封装。\n"
             "你的任务是根据用户的描述和任何错误反馈，生成一段高质量、完整、可以直接保存为.py文件的Python代码。\n"
             "**代码生成规则和强制要求:**\n"
             "1. 你的回答必须**只包含**Python代码，且必须被包裹在 ```python ... ``` 标记中。**绝不能有任何额外的解释性文字**。\n"
             "2. **【强制】工具必须定义为一个独立的函数**，例如 `def {tool_name}(...) -> ...:`。\n"
             "3. **【强制】必须使用 `from server import mcp` 并用 `@mcp.tool()` 装饰你的工具函数。**\n"
             "4. **【强制】工具函数必须包含清晰的类型注解 (type hints)，例如 `def my_tool(arg1: str) -> Dict:`。**\n"
             "5. **【强制】工具函数必须包含清晰的文档字符串(docstring)**，它将作为工具的描述。\n"
             "6. 确保所有必要的 `import` 语句都包含在内。如果你使用了其他库（如 `requests`, `json`, `os`, `typing` 等），也必须导入。\n"
             "7. 确保代码是独立的，可以直接保存为 `.py` 文件并运行。\n"
             "8. **【禁止】绝对禁止使用 `class YourToolName(BaseTool):` 的方式来定义工具。**\n"
             "9. **【禁止】绝不能在生成的代码中包含任何单例模式的逻辑。**\n"
             "10. **【禁止】绝不能在生成的代码中包含对 `config` 模块的导入，API 密钥或配置应通过工具参数传递或由调用方注入。**\n"
             "11. **【禁止】绝不能在生成的代码中包含 `print` 语句，只返回最终结果。**\n"
             "请严格遵守所有规则。如果你不确定如何为复杂类型（如 List[Dict[str, Any]]）定义 `parameters` 或 `returns` 的 JSON Schema，请查阅 JSON Schema 的 `array` 和 `object` 定义。\n"
        )
        
        user_prompt_messages = []
        user_prompt_messages.append(HumanMessage(content=f"请为我创建一个名为 `{tool_name}` 的新工具，功能是：{user_request}"))

        if len(current_messages) > 1:
            error_feedback = current_messages[-1].content 
            user_prompt_messages.append(HumanMessage(content=f"\n之前尝试的代码未能通过测试，请修正以下问题并重新生成：\n```\n{error_feedback}\n```\n\n请严格按照要求重新生成完整的Python代码。"))

        full_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt_content.format(tool_name=tool_name)),
            *user_prompt_messages
        ])

        chain = full_prompt | self.model
        raw_response = chain.invoke({}).content
        
        code_match = re.search(r"```python\s*\n(.*?)\n```", raw_response, re.DOTALL)
        if code_match:
            generated_code = code_match.group(1).strip()
            logger.info("    -> 已成功从LLM响应中提取Python代码块。")
        else:
            logger.warning("    -> 未在LLM响应中找到 ```python ... ``` 代码块，将尝试直接使用全部内容。")
            generated_code = raw_response.strip()

        new_state = state.copy(update={
            "messages": state.messages + [HumanMessage(content=generated_code)], 
            "generated_code": generated_code, 
            "tool_name": tool_name,
            "retries": state.retries + 1
        })
        return new_state
    
    def _test_and_save_node(self, state: SimpleMetaToolAgentState) -> SimpleMetaToolAgentState:
        logger.info(f"节点: 2. 测试并保存代码 (重试次数: {state.retries-1})")
        code_to_test = state.generated_code
        tool_name = state.tool_name

        if not code_to_test or not tool_name:
            error_message = "内部错误：没有可测试的代码或工具名称缺失。"
            logger.error(error_message)
            return state.copy(update={"messages": state.messages + [HumanMessage(content=error_message)]})

        temp_dir = os.path.join(tempfile.gettempdir(), "mcp_generated_tools_test")
        os.makedirs(temp_dir, exist_ok=True)
        tmp_path = os.path.join(temp_dir, f"temp_{tool_name}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}.py")

        try:
            with open(tmp_path, 'w', encoding='utf-8') as tmp_file:
                tmp_file.write(code_to_test)

            spec = importlib.util.spec_from_file_location("temp_tool_test_module", tmp_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, tool_name) or not callable(getattr(module, tool_name)):
                raise ValueError(f"生成的代码中未找到预期的工具函数 '{tool_name}' 或它不是一个可调用对象。")

            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
            output_dir = os.path.abspath(output_dir)
            os.makedirs(output_dir, exist_ok=True)
            file_path = os.path.join(output_dir, f"{tool_name}.py")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code_to_test)
            
            success_message = f"新工具 '{tool_name}.py' 已成功生成并保存到 '{output_dir}'。服务器已自动重载该工具。"
            logger.info(success_message)
            # 将成功消息添加到状态中，以便最终返回
            return state.copy(update={"messages": state.messages + [HumanMessage(content=success_message)], "generated_code": code_to_test})

        except Exception as e:
            error_message = f"代码未能通过内部测试。错误: {e}. 详细堆栈: {traceback.format_exc()}"
            logger.error(error_message)
            # 将错误消息添加到状态中，以便最终返回
            return state.copy(update={"messages": state.messages + [HumanMessage(content=error_message)], "generated_code": None})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _should_continue_generating(self, state: SimpleMetaToolAgentState) -> str:
        """根据测试结果和重试次数决定是否继续重写或结束。"""
        latest_message_content = state.messages[-1].content
        if "已成功生成并保存到" in latest_message_content:
            return "end" # 成功，结束

        if state.retries >= state.max_retries:
            return "fail" # 达到最大重试次数，失败结束

        return "rewrite" # 否则，继续重写

    def _build_graph(self):
        workflow = StateGraph(SimpleMetaToolAgentState)
        
        workflow.add_node("write_tool", self._tool_writer_node)
        workflow.add_node("test_and_save", self._test_and_save_node)

        workflow.set_entry_point("write_tool")

        workflow.add_edge("write_tool", "test_and_save")
        
        workflow.add_conditional_edges(
            "test_and_save",
            self._should_continue_generating,
            {
                "rewrite": "write_tool",
                "fail": END,
                "end": END
            }
        )
        return workflow.compile()

    # invoke 方法优化：直接使用 graph.invoke()
    def invoke(self, initial_state: SimpleMetaToolAgentState) -> SimpleMetaToolAgentState:
        logger.info("正在调用 LangGraph invoke 获取最终状态...")
        try:
            # LangGraph 的 invoke 可能会返回一个字典（代表最终状态的更新），
            # 而不是直接的 Pydantic 模型实例。我们需要将其显式地转换回来。
            raw_final_state_output = self.graph.invoke(initial_state)
            
            # 尝试将 LangGraph 的输出（通常是 dict 或 AddableValuesDict）
            # 转换为你的 SimpleMetaToolAgentState 模型
            if isinstance(raw_final_state_output, dict):
                # Pydantic 可以从字典创建实例
                final_state = SimpleMetaToolAgentState(**raw_final_state_output)
            elif isinstance(raw_final_state_output, SimpleMetaToolAgentState):
                # 如果它已经直接是 SimpleMetaToolAgentState，则直接使用
                final_state = raw_final_state_output
            else:
                # 记录详细错误，并包装成 SimpleMetaToolAgentState 返回
                error_msg = f"LangGraph invoke 返回了非预期的类型: {type(raw_final_state_output)}. 预期 dict 或 SimpleMetaToolAgentState."
                logger.error(error_msg)
                return SimpleMetaToolAgentState(
                    messages=[HumanMessage(content=f"错误：AI工具构建大师核心执行失败: {error_msg}")]
                )

            if final_state.messages:
                logger.info(f"Invoke 完成。最终消息: {final_state.messages[-1].content[:200]}...")
            else:
                logger.warning("Invoke 完成，但 final_state.messages 为空。")
            
            return final_state
        except Exception as e:
            error_msg = f"LangGraph invoke 调用失败: {e}. Traceback: {traceback.format_exc()}"
            logger.error(error_msg)
            return SimpleMetaToolAgentState(
                messages=[HumanMessage(content=f"错误：AI工具构建大师核心执行失败: {e}. 详情请看服务器日志。")]
            )

# --- MCP Tool Function ---
@mcp.tool()
# create_simple_mcp_tool 不再接收 ctx 参数
async def create_simple_mcp_tool(tool_description_request: str) -> str:
    """
    【AI工具构建大师】根据您的自然语言描述，动态地设计、编写、测试并发布一个新的MCP工具。
    新工具将被保存到 'tools/' 目录下（如果该目录是热重载的），并可能被服务器自动重载。
    此工具不在内部使用 MCP Context 进行日志记录，所有日志将输出到服务器终端，
    并且最终的执行结果和错误会通过返回字符串的形式传递。
    在重试几次后，如果仍无法生成有效工具，将返回失败信息。
    
    Args:
        tool_description_request (str): 您对所需新工具功能的详细自然语言描述。
                                        例如："一个可以计算两个数字和的工具", 
                                        "一个可以根据城市名查询当前天气的工具，返回温度和天气描述。"
    
    Returns:
        str: 新工具的Python代码（如果成功），或详细的错误信息，其中可能包含多条消息以说明执行过程。
    """
    logger.info(f"调用 'create_simple_mcp_tool'。请求: '{tool_description_request[:100]}...'")
    
    # 每次调用工具时都创建 SimpleMetaToolAgent 的新实例
    agent = SimpleMetaToolAgent(GOOGLE_API_KEY)
        
    if agent.model is None:
        return "错误：AI工具构建大师未能初始化，因为 GOOGLE_API_KEY 未设置。请检查您的配置。"

    try:
        initial_state = SimpleMetaToolAgentState(
            messages=[HumanMessage(content=tool_description_request)],
            retries=0
        )
        
        # 调用 LangGraph 代理链来执行任务
        final_state = await agent.invoke(initial_state)
        
        # 返回最终的所有消息内容，拼接起来作为结果
        # 这样调用者可以获取到执行过程中的所有日志和错误信息
        all_messages_content = "\n".join([msg.content for msg in final_state.messages])
        logger.info(f"'create_simple_mcp_tool' 完成。最终返回: {all_messages_content[:200]}...")
        return all_messages_content
    except Exception as e:
        error_msg = f"AI工具构建大师执行过程中发生未预期错误: {e}. 详细堆栈: {traceback.format_exc()}"
        logger.error(error_msg)
        return f"AI工具构建大师核心工具发生未预期错误: {e}. 详情请查看服务器日志。"
