from server import mcp
from typing import List
import asyncio

def _generate_fibonacci_sync(n: int) -> List[int]:
    """Synchronous implementation of Fibonacci sequence generation."""
    if n < 0:
        return []
    if n == 0:
        return [0] # Corrected to return a list with the number 0
    
    sequence = []
    a, b = 1, 1
    for _ in range(n):
        sequence.append(a)
        a, b = b, a + b
    return sequence

@mcp.tool()
async def generate_fibonacci(n: int) -> List[int]:
    """
    生成斐波那契数列的前n个数字。

    Args:
        n (int): 要生成的斐波那契数列的长度。必须是大于0的整数。

    Returns:
        List[int]: 包含斐波那契数列前n个数字的列表。如果n小于等于0，则返回空列表。
    """
    # This is a CPU-bound operation, run in a thread to be non-blocking
    return await asyncio.to_thread(_generate_fibonacci_sync, n)

@mcp.tool()
async def fibonacci_sum(n: int) -> int:
    """
    计算斐波那契数列的前n个数字的和。

    Args:
        n (int): 要计算的斐波那契数列的长度。必须是大于0的整数。

    Returns:
        int: 斐波那契数列的前n个数字的和。如果n小于等于0，则返回0。
    """
    if n <= 0:
        return 0
    # Since generate_fibonacci is now async, we await it.
    sequence = await generate_fibonacci(n)
    return sum(sequence)
