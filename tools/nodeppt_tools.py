import os
import subprocess
import asyncio
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from pydantic import BaseModel, Field

# 确保引用的是 server.py 中的 mcp 实例
# 假设你的 `serve.py` 将 `mcp` 暴露为全局变量，并且此文件会由 `serve.py` 导入。
from server import mcp # 此处假设 mcp 实例存在

# --- Pydantic Models for Tool Inputs ---

class Slide(BaseModel):
    title: Optional[str] = Field(None, description="幻灯片的可选标题 (在幻灯片内容中会是一个 <h2> 标签)。")
    content: str = Field(..., description="幻灯片的 Markdown 内容, 包括原始的 Mermaid 代码块 (例如 ```mermaid\\n...\\n```)。")
    css_class: Optional[str] = Field(None, description="<slide> 标签的可选 CSS 类 (例如 'dark', 'center')。")
    notes: Optional[str] = Field(None, description="幻灯片的演讲者备注 (可选)。")

class GenerateMarkdownArgs(BaseModel):
    """生成 NodePPT markdown 文件的参数。"""
    slides: List[Slide] = Field(..., description="一个幻灯片对象数组，每个对象包含内容（Markdown，包括原始 Mermaid 代码）、可选的标题、CSS 类和备注。")
    title: str = Field(..., description="整个演示文稿的标题。")
    author: Optional[str] = Field(None, description="演示文稿的作者 (可选)。")
    output_path: Optional[str] = Field(None, description="保存生成的 markdown 文件的完整路径。如果未提供，将在 'generated_nodeppts' 子目录中创建一个临时文件。")
    theme: Optional[str] = Field(None, description="演示文稿的主题 (例如 'moon', 'simple')。")
    transition: Optional[str] = Field(None, description="幻灯片之间的切换效果 (例如 'fade', 'slide')。")

class ServePresentationArgs(BaseModel):
    """启动本地 NodePPT 服务器的参数。"""
    file_path: str = Field(..., description="要展示的 NodePPT markdown 文件的完整路径。")
    port: Optional[int] = Field(8080, description="NodePPT 服务器运行的端口 (默认为 8080)。")

# --- Helper Functions ---

# MODIFIED: 此函数已更新，以生成不带 '---' 分隔符的元数据。
async def _generate_nodeppt_markdown_content(data: GenerateMarkdownArgs) -> str:
    """
    将幻灯片数据转换为 NodePPT 兼容的 Markdown 字符串。
    元数据（标题、作者等）直接以 "key: value" 格式写在文件顶部，不使用 '---' 包裹。
    直接包含 Mermaid 代码块。
    """
    # 1. 构建元数据部分，作为一个 "key: value" 字符串列表。
    metadata_lines = [f"title: {data.title}"]
    metadata_lines.append("plugins:\n  - mermaid\n - echarts")  # 确保包含 Mermaid 插件
    if data.author:
        metadata_lines.append(f"author: {data.author}")
    if data.theme:
        metadata_lines.append(f"theme: {data.theme}")
    if data.transition:
        metadata_lines.append(f"transition: {data.transition}")
    
    metadata_section = "\n".join(metadata_lines)

    # 2. 构建幻灯片部分。
    slides_markdown = []
    for slide in data.slides:
        slide_header = f"## {slide.title}\n\n" if slide.title else ""
        slide_class_attr = f' class="{slide.css_class}"' if slide.css_class else ""
        
        # 修正：使用 <note> 标签来正确处理演讲者备注。
        slide_notes = f"<note>\n{slide.notes}\n</note>" if slide.notes else ""

        # 将标题、内容和备注组合在 <slide> 标签内。
        full_slide_content = f"{slide_header}{slide.content}"
        if slide_notes:
            full_slide_content += f"\n\n{slide_notes}" # 在内容和备注间添加空行
            
        slides_markdown.append(f"<slide{slide_class_attr}>\n{full_slide_content}\n</slide>")

    slides_section = "\n\n".join(slides_markdown) # 使用两个换行符分隔幻灯片，以提高可读性

    # 3. 组合元数据和幻灯片内容。
    # 在元数据和第一张幻灯片之间添加两个换行符。
    return f"{metadata_section}\n\n{slides_section}"

import os
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

async def _start_nodeppt_server_process(file_path: str, port: int) -> str:
    """
    启动 NodePPT 服务器进程，确保命令能在 PowerShell 中正确运行。

    此函数通过显式调用 'powershell -Command' 来执行命令，
    这解决了直接在 subprocess 中运行复杂 shell 命令的问题，
    并确保了跨环境的兼容性（只要安装了 PowerShell）。
    """
    if not Path(file_path).is_file():
        raise FileNotFoundError(f"Markdown 文件未找到: {file_path}")

    print(f"正在尝试在端口 {port} 上为 {file_path} 启动 NodePPT 服务器...")

    # 1. 构建将在 PowerShell 中执行的完整命令字符串。
    #    - `$env:NODE_OPTIONS=...` 是 PowerShell 设置环境变量的语法。
    #    - 使用分号 (;) 在 PowerShell 中分隔多个命令。
    #    - 将 file_path 用双引号包裹，以正确处理路径中可能存在的空格。
    command_string = f'$env:NODE_OPTIONS="--openssl-legacy-provider"; nodeppt serve "{file_path}" -p {port}'

    # 2. 构建最终传递给 Popen 的参数列表。
    #    我们显式调用 'powershell' 并使用 '-Command' 参数来传递完整的命令。
    #    这比使用 `shell=True` 更安全、更明确。
    #    这种方式会启动一个 PowerShell 进程，然后在该进程中执行我们的命令字符串。
    nodeppt_command_list = ["powershell", "-Command", command_string]
    
    # 确保 NodePPT 在文件所在目录启动，以便它能正确解析相对路径资源
    cwd = Path(file_path).parent

    try:
        # 使用 subprocess.Popen 在后台运行，并将输出重定向
        # `shell=False` 是默认且正确的选项，因为我们传递的是一个命令列表
        process = subprocess.Popen(
            nodeppt_command_list,
            cwd=cwd,
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            # 在 Windows 上，为了完全分离进程，建议使用 CREATE_NEW_CONSOLE 标志
            # start_new_session=True 主要用于 POSIX 系统
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0,
            start_new_session=True
        )
        print(f"NodePPT 服务器进程已启动，PID: {process.pid}")

        # 给服务器一点时间启动。实际应用中可能需要更高级的健康检查。
        # 可以适当延长此时间，如果服务器启动较慢。
        await asyncio.sleep(3) 

        server_url = f"http://localhost:{port}"
        return server_url
    except FileNotFoundError:
        # 如果捕获到这个异常，现在它意味着 'powershell' 命令本身未找到。
        raise RuntimeError("`powershell` 命令未找到。请确保 PowerShell 已安装并已添加到系统的 PATH 环境变量中。")
    except Exception as e:
        raise RuntimeError(f"启动 NodePPT 服务器进程失败: {e}")
# --- MCP Tools ---
# 假设 mcp 实例已在别处定义 (例如 server.py)
@mcp.tool()
async def generate_nodeppt_markdown(args: GenerateMarkdownArgs) -> Dict[str, Any]:
    """
    生成 NodePPT 演示文稿的 Markdown 文件。

    输入幻灯片内容、标题和可选的作者、主题、过渡效果，并指定或自动生成输出路径。
    幻灯片内容可以直接包含 Mermaid 代码块 (` ```mermaid\\n...\\n``` `)，
    NodePPT 在渲染时会自行处理。如果有 Mermaid 代码块，则需要在文件顶部添加 
    `plugins:
        - mermaid`。

    Args:
        args (GenerateMarkdownArgs): 包含生成 Markdown 所需所有参数的对象。

    Returns:
        Dict[str, Any]: 包含生成文件路径和成功消息的字典，或错误信息。
    """
    try:
        if args.output_path:
            output_path = Path(args.output_path)
        else:
            temp_dir = Path.cwd() / "generated_nodeppts"
            temp_dir.mkdir(parents=True, exist_ok=True) # 确保目录存在
            output_path = temp_dir / f"presentation_{uuid.uuid4().hex}.md"
        
        markdown_content = await _generate_nodeppt_markdown_content(args)
        # 使用 aiofiles 异步写入文件会更好，但为保持简单使用 to_thread
        await asyncio.to_thread(lambda: output_path.write_text(markdown_content, encoding='utf-8'))
        
        print(f"NodePPT Markdown 已生成: {output_path}")
        return {
            "file_path": str(output_path),
            "message": f"NodePPT markdown 已成功生成于 {output_path}"
        }
    except Exception as e:
        print(f"generate_nodeppt_markdown 出错: {e}", flush=True)
        return {
            "message": "生成 NodePPT markdown 失败。",
            "error": str(e)
        }

@mcp.tool()
async def serve_nodeppt_presentation(args: ServePresentationArgs) -> Dict[str, Any]:
    """
    在本地启动 NodePPT 服务器以展示指定的 Markdown 演示文稿。

    Args:
        args (ServePresentationArgs): 包含要服务的文件路径和可选端口的对象。

    Returns:
        Dict[str, Any]: 包含服务器 URL 和成功消息的字典，或错误信息。
    """
    try:
        server_url = await _start_nodeppt_server_process(args.file_path, args.port)
        print(f"NodePPT 服务器已启动: {server_url}")
        return {
            "server_url": server_url,
            "message": f"NodePPT 服务器已在 {server_url} 成功启动。您现在可以查看您的演示文稿了。"
        }
    except Exception as e:
        print(f"serve_nodeppt_presentation 出错: {e}", flush=True)
        return {
            "message": "启动 NodePPT 服务器失败。",
            "error": str(e)
        }