from pydantic import BaseModel
from typing import List
from server import mcp  # 确保引用的是 server.py 中的实例
import asyncio
from logger import log as logger

class HanoiTowerArgs(BaseModel):
    """汉诺塔问题的参数"""
    num_disks: int

def _solve_hanoi_tower_sync(num_disks: int, source: str, destination: str, auxiliary: str) -> List[str]:
    """解决汉诺塔问题，返回每一步的移动步骤。"""
    if num_disks == 1:
        return [f"将盘 1 从 {source} 移动到 {destination}"]
    
    steps = _solve_hanoi_tower_sync(num_disks - 1, source, auxiliary, destination)
    steps.append(f"将盘 {num_disks} 从 {source} 移动到 {destination}")
    steps.extend(_solve_hanoi_tower_sync(num_disks - 1, auxiliary, destination, source))
    return steps

@mcp.tool()
async def hanoi_tower_solver(num_disks: int) -> str:
    """
    解决汉诺塔问题的工具。

    输入汉诺塔的层数，输出解决汉诺塔问题的每一步。
    """
    logger.info(f"Solving Tower of Hanoi for {num_disks} disks.")
    if not isinstance(num_disks, int) or num_disks <= 0:
        error_msg = "请输入一个大于0的整数作为汉诺塔的层数。"
        logger.warning(f"Invalid input for hanoi_tower_solver: {num_disks}. Returning error message.")
        return error_msg
    
    # This is a CPU-bound operation, run in a thread to be non-blocking
    steps = await asyncio.to_thread(_solve_hanoi_tower_sync, num_disks, "A", "C", "B")
    logger.success(f"Successfully generated {len(steps)} steps for {num_disks}-disk Tower of Hanoi.")
    return "\n".join(steps)
