# mcp_server/default_tools/rag_tool.py
import os
import requests
import json
from langchain_community.vectorstores import Chroma # 备注：如果OS RAG内部处理向量存储，这个可能不会直接使用
from langchain_google_genai import GoogleGenerativeAIEmbeddings # 备注：如果OS RAG内部处理嵌入，这个可能不会直接使用
from langchain_cohere import CohereRerank
from langchain.docstore.document import Document
from typing import List, Dict, Any
from server import mcp

# 从 config.py 导入 COHERE_API_KEY
try:
    from config import COHERE_API_KEY
except ImportError:
    print("Warning: config.py not found or COHERE_API_KEY not set. Attempting to use environment variable.")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY", "YOUR_FALLBACK_COHERE_API_KEY_IF_ENV_NOT_SET")

@mcp.tool()
def retrieve_knowledge_and_rerank(query: str) -> List[Dict[str, Any]]:
    """
    【核心知识检索工具】从企业知识库（通过外部RAG服务）中检索、筛选并重排序与问题最相关的文档。
    它只返回经过验证的高质量信息片段。
    
    Args:
        query (str): 需要从知识库中检索信息的主题或问题。
        
    Returns:
        List[Dict[str, Any]]: 一个包含相关文档信息的字典列表。每个字典代表一个文档，
                               至少包含 'page_content' 字段，以及可选的 'metadata' 字段。
    """
    print(f"--- [核心知识检索工具 - 默认工具] 开始处理查询: '{query}' ---")
    
    if not COHERE_API_KEY or COHERE_API_KEY == "YOUR_FALLBACK_COHERE_API_KEY_IF_ENV_NOT_SET":
        error_msg = "COHERE_API_KEY 未设置或为默认值，无法使用 Cohere Rerank。"
        print(f"--- [核心知识检索工具 - 默认工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]
    
    try:
        response = requests.post(
            "https://osrag.635262140.xyz/agent",
            json={"query": query},
            timeout=20
        )
        response.raise_for_status()
        result = response.json()
        
        initial_docs_data = result.get("data", [])
        print(f"    -> 步骤 1/2: 初始检索到 {len(initial_docs_data)} 篇文档。")

        print(initial_docs_data)
        documents_for_rerank = []
        for doc_item in initial_docs_data:
            if isinstance(doc_item, dict):
                # 合并所有 content 段的 text 字段
                content_list = doc_item.get("content", [])
                if isinstance(content_list, list):
                    page_content = "\n".join(
                        c.get("text", "") for c in content_list if isinstance(c, dict)
                    )
                else:
                    page_content = ""
                # 构建 metadata，包含 file_id, filename, score, attributes
                metadata = {
                    "file_id": doc_item.get("file_id"),
                    "filename": doc_item.get("filename"),
                    "score": doc_item.get("score"),
                    "attributes": doc_item.get("attributes"),
                }
                documents_for_rerank.append(Document(page_content=page_content, metadata=metadata))
            else:
                print(f"Warning: Unexpected document format from OS RAG: {type(doc_item)}")

    except requests.exceptions.Timeout:
        error_msg = f"连接 OS RAG 服务超时"
        print(f"--- [核心知识检索工具 - 默认工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]
    except requests.exceptions.RequestException as e:
        error_msg = f"调用 OS RAG 服务失败: {e}"
        print(f"--- [核心知识检索工具 - 默认工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]
    except json.JSONDecodeError as e:
        error_msg = f"解析 OS RAG 服务响应失败: {e}. 响应内容: {response.text}"
        print(f"--- [核心知识检索工具 - 默认工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]
    except Exception as e:
        error_msg = f"OS RAG 服务响应处理异常: {e}"
        print(f"--- [核心知识检索工具 - 默认工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]

    if not documents_for_rerank:
        print("    -> 没有文档进行重排序，返回空列表。")
        return []
        
    print("    -> 步骤 2/2: 使用Cohere Rerank进行重排序和筛选...")
    try:
        reranker = CohereRerank(cohere_api_key=COHERE_API_KEY, model="rerank-multilingual-v3.0", top_n=5)
        reranked_docs = reranker.compress_documents(documents=documents_for_rerank, query=query)
        print(f"    -> 重排序后剩下 {len(reranked_docs)} 篇高相关性文档。")

        final_results = []
        for doc in reranked_docs:
            final_results.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata
            })
        
        return final_results

    except Exception as e:
        error_msg = f"使用 Cohere Rerank 失败: {e}"
        print(f"--- [核心知识检索工具 - 默认工具 ERROR] {error_msg} ---")
        return [{"error": error_msg}]