# mcp_server/default_tools/output_parser.py
import re
from markdown_it import MarkdownIt
import asyncio
from server import mcp  # 确保引用的是 server.py 中的实例
from logger import log as logger  # 从中央日志记录器导入

@mcp.tool()
async def parse_and_format_output(answer_content: str) -> str:
    """
    【输出格式化工具】接收最终的、可能包含Markdown和Mermaid代码的答复字符串，
    并将其转换为一个功能完整的、自包含的HTML页面。
    
    Args:
        answer_content (str): 包含Markdown和Mermaid代码的原始文本。
    
    Returns:
        str: 一个包含渲染后的文本和Mermaid图（如果存在）的HTML字符串。
    """
    logger.info("--- [输出工具] 正在将最终答案转换为HTML... ---")
    
    mermaid_code = ""
    text_content = answer_content

    # 使用正则表达式提取Mermaid代码块，并将其从原文中移除
    mermaid_match = re.search(r"```mermaid\s*\n(.*?)\n```", text_content, re.DOTALL)
    if mermaid_match:
        mermaid_code = mermaid_match.group(1).strip()
        text_content = text_content.replace(mermaid_match.group(0), "").strip()
    
    # 将剩余的Markdown文本转换为HTML
    md = MarkdownIt()
    text_html = await asyncio.to_thread(md.render, text_content)
    
    # 构建最终的HTML页面
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>AI Agent 答复报告</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; margin: 0; padding: 0; background-color: #f8f9fa; color: #212529; }}
            .container {{ max-width: 1200px; margin: 40px auto; padding: 30px; background-color: white; border-radius: 12px; box-shadow: 0 8px 16px rgba(0,0,0,0.1); }}
            h1, h2 {{ color: #0056b3; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }}
            .content-section {{ margin-bottom: 30px; }}
            .mermaid {{ text-align: center; }}
            #downloadBtn {{ margin-top: 20px; padding: 10px 20px; font-size: 16px; cursor: pointer; border-radius: 5px; border: none; background-color: #28a745; color: white; transition: background-color 0.3s; }}
            #downloadBtn:hover {{ background-color: #218838; }}
        </style>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>智能体答复报告</h1>
            <div class="content-section">
                <h2>文字答复</h2>
                {text_html}
            </div>
            {"".join([f'''
            <div class="content-section">
                <h2>生成图表</h2>
                <div class="mermaid">
                    {mermaid_code}
                </div>
                <div style="text-align:center;">
                    <button id="downloadBtn">导出为 PNG</button>
                </div>
            </div>
            ''' if mermaid_code else ""])}
        </div>

        <script>
            if (document.querySelector('.mermaid')) {{
                mermaid.initialize({{ "theme": "forest" }});

                async function renderAndDownload() {{
                    const svgElement = document.querySelector('.mermaid svg');
                    if (!svgElement) {{
                        console.error("Mermaid SVG 未找到!");
                        return;
                    }}

                    const svgWidth = svgElement.viewBox.baseVal.width || svgElement.width.baseVal.value;
                    const svgHeight = svgElement.viewBox.baseVal.height || svgElement.height.baseVal.value;

                    const clonedSvgElement = svgElement.cloneNode(true);

                    const svgXML = new XMLSerializer().serializeToString(clonedSvgElement);
                    const svgDataUrl = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgXML);

                    const img = new Image();
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');

                    img.onload = function () {{
                        const padding = 20;
                        canvas.width = svgWidth + padding * 2;
                        canvas.height = svgHeight + padding * 2;

                        ctx.fillStyle = 'white';
                        ctx.fillRect(0, 0, canvas.width, canvas.height);

                        ctx.drawImage(img, padding, padding, svgWidth, svgHeight);

                        const pngUrl = canvas.toDataURL('image/png');
                        const downloadLink = document.createElement('a');
                        downloadLink.href = pngUrl;
                        downloadLink.download = 'diagram.png';
                        document.body.appendChild(downloadLink);
                        downloadLink.click();
                        document.body.removeChild(downloadLink);
                    }};

                    // Set image source after onload, to trigger load event
                    img.src = svgDataUrl;
                }}

                document.addEventListener('DOMContentLoaded', () => {{
                    mermaid.run({{ nodes: document.querySelectorAll('.mermaid') }});
                    document.getElementById('downloadBtn').addEventListener('click', renderAndDownload);
                }});
            }}
        </script>
    </body>
    </html>
    """
    return html_template
