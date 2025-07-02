import subprocess
import json
import os
import httpx
import asyncio
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel, Field
from logger import log as logger

# Import the centralized MCP instance
from server import mcp
from config import GOOGLE_API_KEY

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"

class GitExecutor:
    """Handles all actual interactions with the local Git repository."""
    def __init__(self, repo_path: str):
        if not os.path.isdir(os.path.join(repo_path, '.git')):
            raise ValueError(f"'{repo_path}' is not a valid Git repository.")
        self.repo_path = repo_path

    async def _run_git_command(self, command: List[str], check: bool = True) -> str:
        """Asynchronously executes a git command."""
        logger.debug(f"Running git command: {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if check and process.returncode != 0:
            error_message = f"Git command failed: {stderr.decode()}"
            logger.error(error_message)
            raise RuntimeError(error_message)
        return stdout.decode().strip()

    async def check_for_conflicts(self, source_branch: str) -> Tuple[bool, List[str]]:
        """Performs a 'dry run' merge to check for conflicts."""
        logger.info(f"Checking for conflicts by attempting a test merge of '{source_branch}'...")
        status = await self._run_git_command(['git', 'status', '--porcelain'])
        if status:
            raise RuntimeError("Working directory is not clean. Please commit or stash your changes.")

        try:
            await self._run_git_command(['git', 'merge', '--no-commit', '--no-ff', source_branch])
            logger.info("No conflicts detected. Aborting test merge.")
            await self._run_git_command(['git', 'merge', '--abort'])
            return False, []
        except RuntimeError:
            logger.info("Conflicts detected.")
            stdout = await self._run_git_command(['git', 'diff', '--name-only', '--diff-filter=U'])
            conflicted_files = stdout.splitlines()
            logger.info(f"Conflicted files: {conflicted_files}")
            return True, conflicted_files
    
    async def get_file_content_with_markers(self, file_path: str) -> str:
        """Gets the content of a file with conflict markers."""
        full_path = os.path.join(self.repo_path, file_path)
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Could not read file {file_path}: {e}")
            return f"ERROR: Could not read file {file_path}: {e}"

    async def apply_ai_solution_and_commit(self, source_branch: str, resolved_files: Dict[str, str]) -> str:
        """Applies the AI-generated solution and creates the merge commit."""
        logger.info("Applying AI-generated solution...")
        for file_path, content in resolved_files.items():
            full_path = os.path.join(self.repo_path, file_path)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Applied solution to {file_path}")
            await self._run_git_command(['git', 'add', file_path])

        commit_message = f"Merge branch '{source_branch}' with AI-assisted conflict resolution"
        logger.info(f"Committing merge with message: \"{commit_message}\"")
        await self._run_git_command(['git', 'commit', '-m', commit_message])
        logger.success("Merge commit created successfully.")
        return await self._run_git_command(['git', 'rev-parse', 'HEAD'])

    async def finalize_clean_merge(self, source_branch: str) -> str:
        """Handles a conflict-free merge by creating the merge commit."""
        logger.info("Finalizing clean merge...")
        await self._run_git_command(['git', 'merge', '--no-ff', source_branch], check=False)
        commit_message = f"Merge branch '{source_branch}'"
        await self._run_git_command(['git', 'commit', '-m', commit_message], check=False)
        logger.success("Clean merge completed.")
        return await self._run_git_command(['git', 'rev-parse', 'HEAD'])
        
    async def abort_merge(self):
        """Aborts the current merge process."""
        logger.warning("Aborting merge process...")
        await self._run_git_command(['git', 'merge', '--abort'])
        logger.info("Merge aborted. Working directory restored.")

class GitContextExtractor:
    """Extracts context from the local repository for the AI."""
    def __init__(self, repo_path: str):
        self.executor = GitExecutor(repo_path)

    async def extract_commit_history(self, commit_range: str) -> str:
        """Extracts commit history for a given range."""
        logger.info(f"Extracting history for range '{commit_range}'...")
        if not commit_range:
            return "No specific commit range provided for context."
        
        log_format = "Commit: %H%nAuthor: %an%nDate: %ad%nSubject: %s%nBody: %b%n--GIT-LOG-END--"
        try:
            return await self.executor._run_git_command(['git', 'log', f'--pretty=format:{log_format}', commit_range])
        except RuntimeError as e:
            logger.warning(f"Could not extract git log for range '{commit_range}'. Error: {e}")
            return f"Error extracting log for range '{commit_range}'."

    async def extract_context_for_conflict(self, source_branch: str, context_commits: Optional[str]) -> Dict:
        """Extracts the full context for conflict resolution."""
        logger.info("Extracting context for AI resolver...")
        current_branch = await self.executor._run_git_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        
        return {
            "target_branch": current_branch,
            "source_branch": source_branch,
            "target_branch_context": await self.extract_commit_history(context_commits),
            "source_branch_context": await self.extract_commit_history(f"{current_branch}..{source_branch}")
        }

class AIResolver:
    """Builds the prompt and calls the LLM to resolve conflicts."""
    def __init__(self):
        pass

    def _build_prompt(self, context_data: Dict, conflicted_files_data: Dict[str, str]) -> str:
        # This is a placeholder. A real implementation would be much more complex.
        prompt = f"""
        You are an expert Git merge conflict resolver. Resolve the conflicts in the following files.
        Context: {json.dumps(context_data, indent=2)}
        Conflicted files: {json.dumps(conflicted_files_data, indent=2)}
        Respond with a JSON object with a single key "resolved_files", which is a list of objects, each with "file_path" and "resolved_content".
        """
        return prompt
    
    async def resolve_conflicts(self, context_data: Dict, conflicted_files_data: Dict[str, str]) -> Dict[str, str]:
        """Calls the LLM API to resolve conflicts."""
        logger.info("Building prompt and calling AI to resolve conflicts...")
        prompt = self._build_prompt(context_data, conflicted_files_data)
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(GEMINI_API_URL, headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            result = response.json()
            
            content_text = result["candidates"][0]["content"]["parts"][0]["text"]
            resolved_data = json.loads(content_text)
            resolved_files_list = resolved_data.get("resolved_files", [])
            resolved_files_dict = {item["file_path"]: item["resolved_content"] for item in resolved_files_list}
            
            if not resolved_files_dict:
                raise ValueError("AI returned an empty list of resolved files.")
            
            logger.success("Successfully received AI solution.")
            return resolved_files_dict
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            raise RuntimeError(f"API request failed: {e}")
        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
            raw_response = response.text if 'response' in locals() else 'No response'
            raise RuntimeError(f"Failed to parse AI response: {e}. Raw response: {raw_response}")

@mcp.tool()
async def ai_assisted_merge(source_branch: str, context_commits: Optional[str] = None) -> str:
    """
    AI-assisted merge tool. Merges the source branch into the current branch, using an AI to resolve conflicts if they arise.
    """
    repo_path = "."
    logs = [f"===== Starting AI-assisted merge for branch '{source_branch}' ====="]
    git_executor = GitExecutor(repo_path)

    try:
        logger.info("Performing pre-checks...")
        await git_executor._run_git_command(['git', 'rev-parse', '--verify', source_branch])
        logger.info(f"Source branch '{source_branch}' exists.")

        has_conflicts, conflicted_files = await git_executor.check_for_conflicts(source_branch)

        if not has_conflicts:
            commit_hash = await git_executor.finalize_clean_merge(source_branch)
            logs.append(f"SUCCESS: Clean merge completed. New commit hash: {commit_hash}")
            logger.success(f"Clean merge completed. New commit hash: {commit_hash}")
        else:
            logger.info("Conflicts detected. Starting AI resolution workflow.")
            context_extractor = GitContextExtractor(repo_path)
            ai_resolver = AIResolver()

            context_data = await context_extractor.extract_context_for_conflict(source_branch, context_commits)
            
            conflicted_content = {
                file: await git_executor.get_file_content_with_markers(file)
                for file in conflicted_files
            }

            ai_solution = await ai_resolver.resolve_conflicts(context_data, conflicted_content)
            commit_hash = await git_executor.apply_ai_solution_and_commit(source_branch, ai_solution)
            logs.append(f"SUCCESS: AI-assisted merge completed. New commit hash: {commit_hash}")
            logger.success(f"AI-assisted merge completed. New commit hash: {commit_hash}")

    except (RuntimeError, ValueError) as e:
        error_msg = f"ERROR: Merge process failed: {e}"
        logs.append(f"\n{error_msg}")
        logger.error(error_msg)
        
        logger.info("Attempting to clean up by aborting any pending merge...")
        try:
            await git_executor.abort_merge()
        except RuntimeError as abort_e:
            abort_error_msg = f"ERROR: Failed to abort merge. Manual cleanup may be required. Error: {abort_e}"
            logs.append(abort_error_msg)
            logger.critical(abort_error_msg)
    finally:
        logs.append("===== AI-assisted merge process finished =====")
        logger.info("===== AI-assisted merge process finished =====")
    
    return "\n".join(logs)
