import subprocess
import json
import os
import requests
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel, Field

# 模拟从您的服务器导入 mcp 实例
# 在您的实际环境中，请确保 server.py 和 mcp 实例是可用的
from server import mcp
from config import GOOGLE_API_KEY

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"


# --- Pydantic Argument Schema ---
class MergeBranchArgs(BaseModel):
    """AI辅助合并工具的参数模型。"""
    source_branch: str = Field(..., description="要合并到当前分支的功能分支的名称。")
    context_commits: Optional[str] = Field(None, description="可选。一个Git提交范围（例如 'HEAD~5..HEAD'），用于为AI提供额外的上下文。")


# --- Core Logic Modules (Helper Classes) ---

class GitExecutor:
    """
    负责执行所有与本地Git仓库交互的实际操作。
    相当于方案中的 mcp-git-executor 模块。
    """
    def __init__(self, repo_path: str, logs: List[str]):
        """
        初始化Git执行器。
        :param repo_path: 本地Git仓库的路径。
        :param logs: 用于记录操作日志的列表。
        """
        if not os.path.isdir(os.path.join(repo_path, '.git')):
            raise ValueError(f"'{repo_path}' 不是一个有效的Git仓库。")
        self.repo_path = repo_path
        self.logs = logs

    def _run_git_command(self, command: List[str], check: bool = True) -> Tuple[int, str, str]:
        """
        在仓库路径下执行一个git命令。
        """
        try:
            process = subprocess.run(
                command,
                cwd=self.repo_path,
                check=check,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            return process.returncode, process.stdout.strip(), process.stderr.strip()
        except FileNotFoundError:
            raise RuntimeError("Git命令未找到。请确保Git已安装并在您的PATH中。")
        except subprocess.CalledProcessError as e:
            if check:
                error_message = f"""
                Git command failed with exit code {e.returncode}:
                Command: {' '.join(e.cmd)}
                Stdout: {e.stdout.strip()}
                Stderr: {e.stderr.strip()}
                """
                raise RuntimeError(error_message) from e
            return e.returncode, e.stdout.strip(), e.stderr.strip()


    def check_for_conflicts(self, source_branch: str) -> Tuple[bool, List[str]]:
        """
        尝试进行一次“试合并”，以检查是否存在冲突。
        """
        self.logs.append(f"INFO: 正在通过试合并检查分支 '{source_branch}' 是否存在冲突...")
        _, status, _ = self._run_git_command(['git', 'status', '--porcelain'])
        if status:
            raise RuntimeError("工作目录不干净。请提交或储藏您的更改。")

        return_code, _, _ = self._run_git_command(['git', 'merge', '--no-commit', '--no-ff', source_branch], check=False)

        if return_code == 0:
            self.logs.append("INFO: 未检测到冲突。正在中止试合并。")
            self._run_git_command(['git', 'merge', '--abort'])
            return False, []
        else:
            self.logs.append("INFO: 检测到冲突。")
            _, stdout, _ = self._run_git_command(['git', 'diff', '--name-only', '--diff-filter=U'])
            conflicted_files = stdout.splitlines()
            self.logs.append(f"INFO: 冲突文件列表: {conflicted_files}")
            return True, conflicted_files
    
    def get_file_content_with_markers(self, file_path: str) -> str:
        """
        获取包含冲突标记的文件的内容。
        """
        full_path = os.path.join(self.repo_path, file_path)
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"ERROR: 文件未找到: {file_path}"
        except Exception as e:
            return f"ERROR: 无法读取文件 {file_path}: {e}"

    def apply_ai_solution_and_commit(self, source_branch: str, resolved_files: Dict[str, str]) -> str:
        """
        将AI生成的解决方案应用到文件中，并创建合并提交。
        """
        self.logs.append("INFO: 正在应用AI生成的解决方案...")
        for file_path, content in resolved_files.items():
            full_path = os.path.join(self.repo_path, file_path)
            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.logs.append(f"INFO: 已将解决方案应用到 {file_path}")
                self._run_git_command(['git', 'add', file_path])
            except Exception as e:
                raise RuntimeError(f"将解决方案应用到 {file_path} 时失败: {e}")

        commit_message = f"Merge branch '{source_branch}' with AI-assisted conflict resolution"
        self.logs.append(f"INFO: 正在提交合并，提交信息: \"{commit_message}\"")
        self._run_git_command(['git', 'commit', '-m', commit_message])
        self.logs.append("INFO: 合并提交已成功创建。")
        _, commit_hash, _ = self._run_git_command(['git', 'rev-parse', 'HEAD'])
        return commit_hash

    def finalize_clean_merge(self, source_branch: str) -> str:
        """
        处理无冲突的合并，直接创建合并提交。
        """
        self.logs.append("INFO: 正在完成无冲突合并...")
        # 重新执行合并，这次是正式的
        self._run_git_command(['git', 'merge', '--no-ff', source_branch], check=False)
        commit_message = f"Merge branch '{source_branch}'"
        self._run_git_command(['git', 'commit', '-m', commit_message])
        self.logs.append("INFO: 无冲突合并已成功完成。")
        _, commit_hash, _ = self._run_git_command(['git', 'rev-parse', 'HEAD'])
        return commit_hash
        
    def abort_merge(self):
        """中止当前的合并操作，清理工作目录。"""
        self.logs.append("INFO: 正在中止合并流程...")
        self._run_git_command(['git', 'merge', '--abort'])
        self.logs.append("INFO: 合并已中止。工作目录已恢复。")


class GitContextExtractor:
    """
    负责从本地仓库提取AI决策所需的上下文信息。
    """
    def __init__(self, repo_path: str, logs: List[str]):
        self.executor = GitExecutor(repo_path, logs)
        self.logs = logs

    def extract_commit_history(self, commit_range: str) -> str:
        """
        提取指定范围内的提交历史作为上下文。
        """
        self.logs.append(f"INFO: 正在提取提交范围 '{commit_range}' 的历史记录...")
        if not commit_range:
            return "未提供用于上下文的特定提交范围。"
        
        log_format = "Commit: %H%nAuthor: %an%nDate: %ad%nSubject: %s%nBody: %b%n--GIT-LOG-END--"
        try:
            _, history, _ = self.executor._run_git_command(['git', 'log', f'--pretty=format:{log_format}', commit_range])
            return history if history else "在指定范围内未找到任何提交。"
        except RuntimeError as e:
            self.logs.append(f"WARN: 无法提取范围 '{commit_range}' 的git log。错误: {e}")
            return f"提取范围 '{commit_range}' 的日志时出错。"

    def extract_context_for_conflict(self, source_branch: str, context_commits: Optional[str]) -> Dict:
        """
        为冲突解决提取完整的上下文。
        """
        self.logs.append("INFO: 正在为AI解决器提取上下文...")
        _, current_branch, _ = self.executor._run_git_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        
        context_data = {
            "target_branch": current_branch,
            "source_branch": source_branch,
            "target_branch_context": self.extract_commit_history(context_commits),
            "source_branch_context": self.extract_commit_history(f"{current_branch}..{source_branch}")
        }
        return context_data


class AIResolver:
    """
    负责构建提示词并调用LLM来解决冲突。
    """
    def __init__(self, logs: List[str]):
        self.logs = logs

    def _build_prompt(self, context_data: Dict, conflicted_files_data: Dict[str, str]) -> str:
        # (此内部方法的实现与之前相同，为简洁起见此处省略，但代码中是完整的)
        prompt = """你是一名世界级的软件工程师，擅长通过分析代码的演化历史来解决复杂的Git合并冲突。你的任务是解决以下代码冲突。

## 1. 合并信息
- **目标分支 (Target Branch):** `{target_branch}`
- **源分支 (Source Branch):** `{source_branch}`

## 2. 需求与历史上下文
### 目标分支 `{target_branch}` 的相关历史:
```
{target_branch_context}
```

### 源分支 `{source_branch}` 的相关历史:
```
{source_branch_context}
```

## 3. 冲突详情
以下是需要解决的冲突文件列表和内容。请仔细分析每个文件中双方的意图。
""".format(**context_data)

        for file_path, content in conflicted_files_data.items():
            prompt += f"\n### 文件: `{file_path}`\n```\n{content}\n```\n"

        prompt += """
## 4. 你的任务
请基于你对双方开发历史和意图的理解，为**每一个**冲突文件生成一个全新的、解决了冲突的完整文件内容。
你的解决方案必须：
1. 语法正确，逻辑严谨。
2. 尽可能地融合双方的功能意图。
3. 不要包含任何Git冲突标记 (`<<<<<<<`, `=======`, `>>>>>>>`)。
4. **严格按照**以下JSON格式返回你的答案，不要包含任何额外的解释或注释。

```json
{
  "resolved_files": [
    {
      "file_path": "path/to/first/conflicted/file.py",
      "resolved_content": "..."
    },
    {
      "file_path": "path/to/second/conflicted/file.js",
      "resolved_content": "..."
    }
  ]
}
```
"""
        return prompt
    
    def resolve_conflicts(self, context_data: Dict, conflicted_files_data: Dict[str, str]) -> Dict[str, str]:
        """
        调用LLM API来解决冲突。
        """
        self.logs.append("INFO: 正在构建提示词并调用AI解决冲突...")
        prompt = self._build_prompt(context_data, conflicted_files_data)
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            }
        }

        try:
            response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload), timeout=180)
            response.raise_for_status()
            result = response.json()
            
            if (result.get("candidates") and 
                result["candidates"][0].get("content") and 
                result["candidates"][0]["content"].get("parts")):
                
                content_text = result["candidates"][0]["content"]["parts"][0]["text"]
                resolved_data = json.loads(content_text)
                resolved_files_list = resolved_data.get("resolved_files", [])
                resolved_files_dict = {item["file_path"]: item["resolved_content"] for item in resolved_files_list}
                
                if not resolved_files_dict:
                    raise ValueError("AI返回了一个空的已解决文件列表。")
                
                self.logs.append("INFO: 已成功接收AI解决方案。")
                return resolved_files_dict
            else:
                raise ValueError(f"API响应结构异常: {result}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API请求失败: {e}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raw_response = response.text if 'response' in locals() else 'No response'
            raise RuntimeError(f"解析AI响应失败: {e}。原始响应: {raw_response}")


# --- MCP Tool Definition ---

@mcp.tool()
def ai_assisted_merge(source_branch: str, context_commits: Optional[str] = None) -> str:
    """
    AI辅助合并工具。

    将给定的源分支合并到当前分支。如果检测到冲突，它将使用AI根据提交历史来解决它们。
    返回执行操作的日志。
    """
    repo_path = "."  # 假设服务器从仓库根目录运行
    logs = [f"===== 正在启动分支 '{source_branch}' 的AI辅助合并流程 ====="]

    git_executor = GitExecutor(repo_path, logs)

    try:
        # 0. 预检查
        logs.append("INFO: 正在执行预检查...")
        git_executor._run_git_command(['git', 'rev-parse', '--verify', source_branch])
        logs.append(f"INFO: 源分支 '{source_branch}' 存在。")

        # 1. 检查冲突
        has_conflicts, conflicted_files_list = git_executor.check_for_conflicts(source_branch)

        if not has_conflicts:
            # 2a. 无冲突，直接完成合并
            commit_hash = git_executor.finalize_clean_merge(source_branch)
            logs.append(f"SUCCESS: 无冲突合并完成。新的合并提交哈希为: {commit_hash}")
        else:
            # 2b. 有冲突，启动AI解决流程
            logs.append("INFO: 检测到冲突，正在启动AI解决工作流。")
            context_extractor = GitContextExtractor(repo_path, logs)
            ai_resolver = AIResolver(logs)

            # 3. 提取上下文
            context_data = context_extractor.extract_context_for_conflict(source_branch, context_commits)
            
            # 4. 获取冲突文件内容
            conflicted_files_content = {
                file: git_executor.get_file_content_with_markers(file)
                for file in conflicted_files_list
            }

            # 5. AI解决
            ai_solution = ai_resolver.resolve_conflicts(context_data, conflicted_files_content)

            # 6. 应用解决方案并提交
            commit_hash = git_executor.apply_ai_solution_and_commit(source_branch, ai_solution)
            logs.append(f"SUCCESS: AI辅助合并完成。新的合并提交哈希为: {commit_hash}")

    except (RuntimeError, ValueError) as e:
        logs.append(f"\nERROR: 合并流程失败: {e}")
        logs.append("INFO: 正在尝试通过中止任何待处理的合并来清理...")
        try:
            # 最后的保障，确保工作目录是干净的
            git_executor.abort_merge()
        except RuntimeError as abort_e:
            logs.append(f"ERROR: 中止合并失败。可能需要手动清理。错误: {abort_e}")
    finally:
        logs.append("===== AI辅助合并流程结束 =====")
    
    return "\n".join(logs)


# --- Example Usage for Standalone Testing ---
if __name__ == '__main__':
    # 这个部分仅用于独立测试，在您的服务器环境中不会被执行。
    # 它演示了如何调用这个工具。
    repo_directory = "."
    source_branch_to_merge = "feature/new-login" # 请替换为您仓库中真实存在的分支
    context_commit_range = "HEAD~3..HEAD"

    print("######################################################")
    print("#  MCP-TOOLS: AI-Assisted Git Merge (Standalone Test)  #")
    print("######################################################")

    try:
        # 在独立模式下，我们直接调用函数
        result_log = ai_assisted_merge(
            source_branch=source_branch_to_merge,
            context_commits=context_commit_range
        )
        print(result_log)
    except Exception as e:
        print(f"An unexpected error occurred during the standalone test: {e}")

