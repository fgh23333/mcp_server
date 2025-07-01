import uuid
import asyncio
import socket
from pathlib import Path
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field
from loguru import logger

# 从 server.py 导入共享的 mcp 实例
from server import mcp

# --- Pydantic Models ---
class Slide(BaseModel):
    title: Optional[str] = Field(None, description="幻灯片的可选标题。")
    content: str = Field(..., description="幻灯片的 Markdown 内容。")
    notes: Optional[str] = Field(None, description="演讲者备注。")

class GenerateMarkdownArgs(BaseModel):
    slides: List[Slide] = Field(..., description="幻灯片对象数组。")
    title: str = Field(..., description="演示文稿标题。")
    author: Optional[str] = Field(None, description="作者。")
    output_path: Optional[str] = Field(None, description="输出路径。如果未提供，则生成临时文件。")

class ServePresentationArgs(BaseModel):
    file_path: str = Field(..., description="要展示的 Markdown 文件路径。")
    port: int = Field(8080, description="用户本地启动服务的端口。")


def _get_local_ip():
    """获取本机的局域网IP地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 不需要真正发送数据
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# --- MCP Tools ---
@mcp.tool()
async def generate_nodeppt_markdown(args: GenerateMarkdownArgs) -> Dict[str, Any]:
    """
    生成 NodePPT 演示文稿的 Markdown 内容。
    此工具仅生成 Markdown 文本，不写入文件，以便客户端可以在本地保存。
    """
    async def _generate_content(data: GenerateMarkdownArgs) -> str:
        metadata_lines = [f"title: {data.title}"]
        if data.author:
            metadata_lines.append(f"author: {data.author}")
        
        full_content_for_check = "".join(s.content for s in data.slides)
        if "```mermaid" in full_content_for_check:
            metadata_lines.append("plugins:\n  - mermaid")
            
        metadata_section = "\n".join(metadata_lines)

        slides_markdown = []
        for slide in data.slides:
            slide_header = f"## {slide.title}\n\n" if slide.title else ""
            slide_notes = f"<note>\n{slide.notes}\n</note>" if slide.notes else ""
            
            full_slide_content = f"{slide_header}{slide.content}"
            if slide_notes:
                full_slide_content += f"\n\n{slide_notes}"
            
            slides_markdown.append(f"<slide>\n{full_slide_content}\n</slide>")
        slides_section = "\n\n".join(slides_markdown)
        
        return f"{metadata_section}\n\n{slides_section}"

    try:
        markdown_content = await _generate_content(args)
        
        # 生成一个建议的文件名，但不创建文件
        suggested_filename = f"presentation_{uuid.uuid4().hex}.md"
        
        logger.info(f"成功生成 NodePPT Markdown 内容，建议文件名: {suggested_filename}")
        return {
            "success": True,
            "markdown_content": markdown_content,
            "suggested_filename": suggested_filename,
            "message": "Markdown 内容已生成。请在客户端保存并使用 'serve_nodeppt_presentation' 工具启动服务。"
        }
    except Exception as e:
        logger.error(f"生成 Markdown 内容时出错: {e}")
        return {"success": False, "error": f"生成 Markdown 内容时出错: {e}"}

@mcp.tool()
async def serve_nodeppt_presentation(args: ServePresentationArgs) -> Dict[str, Any]:
    """
    为本地启动 NodePPT 服务生成指令。

    此工具不直接启动服务，而是返回一个完整的 npx 命令，
    用户可以在自己的终端中执行该命令来启动演示文稿服务。
    """
    try:
        # 确保文件路径是绝对路径，以便在命令中正确使用
        abs_file_path = Path(args.file_path).resolve()
        
        # 构建 npx 命令
        command_to_run = (
            f'npx -y -p node@16.20.0 -p nodeppt '
            f'nodeppt serve "{abs_file_path}" -p {args.port}'
        )
        
        local_ip = _get_local_ip()
        server_url = f"http://{local_ip}:{args.port}"
        
        logger.info(f"为 {args.file_path} 生成的 NodePPT 启动命令: {command_to_run}")
        
        return {
            "success": True,
            "message": "请在您的本地终端中执行以下命令来启动演示服务:",
            "command": command_to_run,
            "server_url": server_url
        }
    except Exception as e:
        logger.error(f"生成 NodePPT 命令时出错: {e}")
        return {"success": False, "error": f"生成 NodePPT 命令时出错: {e}"}
