from typing import Dict, Any
from server import mcp
import asyncio
import subprocess
from logger import log as logger

async def _run_git_command(command: list, cwd: str):
    """Asynchronously runs a git command."""
    logger.debug(f"Running command: {' '.join(command)} in {cwd}")
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(f"Command failed with exit code {process.returncode}: {' '.join(command)}")
        logger.error(f"Stderr: {stderr.decode().strip()}")
        raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
    logger.debug(f"Command successful: {' '.join(command)}")
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
    logger.info(f"Initiating content sync from '{source_branch}' to '{target_branch}' in repo: {git_repo_path}")
    try:
        # Checkout the target branch
        logger.info(f"Checking out target branch '{target_branch}'...")
        await _run_git_command(['git', 'checkout', target_branch], git_repo_path)
        logger.success(f"Successfully checked out branch '{target_branch}'.")

        # Find common files modified in both branches
        logger.info(f"Finding modified files between '{source_branch}' and '{target_branch}'...")
        diff_output = await _run_git_command(['git', 'diff', '--name-only', source_branch, target_branch], git_repo_path)
        modified_files = diff_output.strip().split('\n') if diff_output else []

        if not modified_files or modified_files == ['']:
            message = f'No common files modified between {source_branch} and {target_branch}.'
            logger.info(message)
            return {
                'status': 'success',
                'message': message,
                'details': ''
            }
        logger.info(f"Found {len(modified_files)} modified files to process: {modified_files}")

        # Cherry-pick commits from source_branch to target_branch for each modified file
        cherry_pick_results = []
        for file in modified_files:
            logger.info(f"Processing file: {file}")
            # Find commits in source_branch that modify the file
            log_output = await _run_git_command(['git', 'log', '--pretty=format:%H', source_branch, '--', file], git_repo_path)
            commits = log_output.strip().split('\n') if log_output else []

            if not commits or commits == ['']:
                no_commit_msg = f"No commits found in {source_branch} modifying {file}"
                logger.info(no_commit_msg)
                cherry_pick_results.append(no_commit_msg)
                continue
            
            logger.info(f"Found {len(commits)} commits for '{file}': {commits}")

            for commit in reversed(commits): # Cherry-pick from oldest to newest
                logger.info(f"Attempting to cherry-pick commit '{commit}' for file '{file}'...")
                try:
                    cherry_pick_output = await _run_git_command(['git', 'cherry-pick', commit], git_repo_path)
                    success_msg = f"Successfully cherry-picked commit {commit} for file {file}: {cherry_pick_output}"
                    logger.success(success_msg)
                    cherry_pick_results.append(success_msg)
                except subprocess.CalledProcessError as e:
                    # Handle conflicts
                    conflict_msg = f"Conflict cherry-picking commit {commit} for file {file}: {e.stderr.decode().strip()}"
                    logger.error(conflict_msg)
                    cherry_pick_results.append(conflict_msg)
                    
                    logger.warning(f"Aborting cherry-pick for commit '{commit}' due to conflict.")
                    await _run_git_command(['git', 'cherry-pick', '--abort'], git_repo_path)
                    
                    final_message = f'Conflicts encountered while cherry-picking commits for file {file}. Aborted cherry-pick.'
                    logger.error(final_message)
                    return {
                        'status': 'failure',
                        'message': final_message,
                        'details': cherry_pick_results
                    }
        
        final_success_message = f'Successfully synchronized content from {source_branch} to {target_branch}.'
        logger.success(final_success_message)
        return {
            'status': 'success',
            'message': final_success_message,
            'details': cherry_pick_results
        }

    except subprocess.CalledProcessError as e:
        error_message = f'Failed to synchronize content: {e.stderr.decode().strip()}'
        logger.error(error_message)
        return {
            'status': 'failure',
            'message': error_message,
            'details': ''
        }
    except Exception as e:
        error_message = f'An unexpected error occurred: {str(e)}'
        logger.error(error_message, exception=True)
        return {
            'status': 'failure',
            'message': error_message,
            'details': ''
        }
