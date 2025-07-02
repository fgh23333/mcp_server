# mcp_server/default_tools/rag_tool.py
import os
import httpx
import json
import asyncio
from langchain_cohere import CohereRerank
from langchain_core.documents import Document
from typing import List, Dict, Any
from server import mcp
from logger import log as logger

# 从 config.py 导入 COHERE_API_KEY
try:
    from config import COHERE_API_KEY
except ImportError:
    logger.warning("config.py not found or COHERE_API_KEY not set. Attempting to use environment variable.")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY", "YOUR_FALLBACK_COHERE_API_KEY_IF_ENV_NOT_SET")

@mcp.tool()
async def retrieve_os_knowledge(query: str) -> List[Dict[str, Any]]:
    """
    【操作系统知识检索工具】从外部RAG服务中检索与问题最相关的原始文档。
    
    Args:
        query (str): 需要从知识库中检索信息的主题或问题。
        
    Returns:
        List[Dict[str, Any]]: 一个包含原始文档信息的字典列表，或在出错时返回包含错误信息的列表。
    """
    logger.info(f"--- [OS知识检索工具] 开始处理查询: '{query}' ---")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://osrag.635262140.xyz/agent",
                json={"query": query},
                timeout=20
            )
            response.raise_for_status()
            result = response.json()
        
        initial_docs_data = result.get("data", [])
        logger.success(f"    -> 成功检索到 {len(initial_docs_data)} 篇原始文档。")

        # 将原始数据直接返回，让下一个工具处理
        return initial_docs_data

    except httpx.TimeoutException:
        error_msg = "连接 OS RAG 服务超时"
        logger.error(f"--- [OS知识检索工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]
    except httpx.RequestError as e:
        error_msg = f"调用 OS RAG 服务失败: {e}"
        logger.error(f"--- [OS知识检索工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]
    except json.JSONDecodeError as e:
        error_msg = f"解析 OS RAG 服务响应失败: {e}. 响应内容: {response.text}"
        logger.error(f"--- [OS知识检索工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]
    except Exception as e:
        error_msg = f"OS RAG 服务响应处理异常: {e}"
        logger.error(f"--- [OS知识检索工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]

@mcp.tool()
async def rerank_documents_with_cohere(query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    【Cohere文档重排工具】使用Cohere Rerank API对输入的文档列表进行重排序和筛选。
    
    Args:
        query (str): 用于重排序的原始查询。
        documents (List[Dict[str, Any]]): 从 retrieve_os_knowledge 工具获取的原始文档列表。
        
    Returns:
        List[Dict[str, Any]]: 一个包含重排序后文档信息的字典列表，或在出错时返回包含错误信息的列表。
    """
    logger.info(f"--- [Cohere重排工具] 开始为查询 '{query}' 重排 {len(documents)} 篇文档 ---")

    if not COHERE_API_KEY or COHERE_API_KEY == "YOUR_FALLBACK_COHERE_API_KEY_IF_ENV_NOT_SET":
        error_msg = "COHERE_API_KEY 未设置或为默认值，无法使用 Cohere Rerank。"
        logger.error(f"--- [Cohere重排工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]

    if not documents:
        logger.warning("输入的文档列表为空，无需重排。")
        return []

    # 将字典列表转换为 LangChain 的 Document 对象
    documents_for_rerank = []
    for doc_item in documents:
        if isinstance(doc_item, dict):
            content_list = doc_item.get("content", [])
            if isinstance(content_list, list):
                page_content = "\n".join(
                    c.get("text", "") for c in content_list if isinstance(c, dict)
                )
            else:
                page_content = ""
            metadata = {
                "file_id": doc_item.get("file_id"),
                "filename": doc_item.get("filename"),
                "score": doc_item.get("score"),
                "attributes": doc_item.get("attributes"),
            }
            documents_for_rerank.append(Document(page_content=page_content, metadata=metadata))
        else:
            logger.warning(f"检测到非预期的文档格式: {type(doc_item)}")

    if not documents_for_rerank:
        logger.warning("转换后没有可用于重排的文档。")
        return []

    logger.info(f"    -> 使用Cohere Rerank进行重排序和筛选...")
    try:
        reranker = CohereRerank(cohere_api_key=COHERE_API_KEY, model="rerank-multilingual-v3.0", top_n=5)
        # reranker.compress_documents 是一个同步方法，需要在线程中运行以避免阻塞
        reranked_docs = await asyncio.to_thread(
            reranker.compress_documents,
            documents=documents_for_rerank, 
            query=query
        )
        logger.success(f"    -> 重排序后剩下 {len(reranked_docs)} 篇高相关性文档。")

        # 将重排后的 Document 对象转换回字典列表
        final_results = []
        for doc in reranked_docs:
            final_results.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata
            })
        
        return final_results

    except Exception as e:
        error_msg = f"使用 Cohere Rerank 失败: {e}"
        logger.error(f"--- [Cohere重排工具 ERROR] {error_msg} ---", exception=True)
        return [{"error": error_msg}]
