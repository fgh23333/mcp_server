from typing import Dict, Any
from server import mcp
import asyncio
import subprocess

async def _run_git_command(command: list, cwd: str):
    """Asynchronously runs a git command."""
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
    return stdout.decode().strip()

@mcp.tool()
async def branch_content_sync(
    git_repo_path: str,
    source_branch: str,
    target_branch: str
) -> Dict[str, Any]:
    """
    Synchronizes content from a source branch to a target branch in a Git repository.

    This tool checks out the target branch, attempts to cherry-pick commits from the source branch that modify the same files,
    and handles potential conflicts.

    Args:
        git_repo_path: The absolute path to the Git repository.
        source_branch: The name of the branch to sync content from.
        target_branch: The name of the branch to sync content to.

    Returns:
        A dictionary containing the result of the synchronization process, including:
            - 'status': 'success' or 'failure'.
            - 'message': A descriptive message about the outcome.
            - 'details': Any relevant details, such as cherry-pick output or conflict information.
    """
    try:
        # Checkout the target branch
        await _run_git_command(['git', 'checkout', target_branch], git_repo_path)

        # Find common files modified in both branches
        diff_output = await _run_git_command(['git', 'diff', '--name-only', source_branch, target_branch], git_repo_path)
        modified_files = diff_output.strip().split('\n')

        if not modified_files or modified_files == ['']:
            return {
                'status': 'success',
                'message': f'No common files modified between {source_branch} and {target_branch}.',
                'details': ''
            }

        # Cherry-pick commits from source_branch to target_branch for each modified file
        cherry_pick_results = []
        for file in modified_files:
            # Find commits in source_branch that modify the file
            log_output = await _run_git_command(['git', 'log', '--pretty=format:%H', source_branch, '--', file], git_repo_path)
            commits = log_output.strip().split('\n')

            if not commits or commits == ['']:
                cherry_pick_results.append(f"No commits found in {source_branch} modifying {file}")
                continue

            for commit in commits:
                try:
                    cherry_pick_output = await _run_git_command(['git', 'cherry-pick', commit], git_repo_path)
                    cherry_pick_results.append(f"Cherry-picked commit {commit} for file {file}: {cherry_pick_output}")
                except subprocess.CalledProcessError as e:
                    # Handle conflicts
                    cherry_pick_results.append(f"Conflict cherry-picking commit {commit} for file {file}: {e.stderr.decode().strip()}")
                    # Attempt to resolve conflicts (e.g., using git merge-tool or manual resolution)
                    # For simplicity, we'll just abort the cherry-pick
                    await _run_git_command(['git', 'cherry-pick', '--abort'], git_repo_path)
                    return {
                        'status': 'failure',
                        'message': f'Conflicts encountered while cherry-picking commits for file {file}. Aborted cherry-pick.',
                        'details': cherry_pick_results
                    }

        return {
            'status': 'success',
            'message': f'Successfully synchronized content from {source_branch} to {target_branch}.',
            'details': cherry_pick_results
        }

    except subprocess.CalledProcessError as e:
        return {
            'status': 'failure',
            'message': f'Failed to synchronize content: {e.stderr.decode().strip()}',
            'details': ''
        }
    except Exception as e:
        return {
            'status': 'failure',
            'message': f'An unexpected error occurred: {str(e)}',
            'details': ''
        }
