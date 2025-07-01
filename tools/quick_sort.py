from server import mcp
from typing import List, Any
import asyncio

@mcp.tool()
async def quick_sort(arr: List[Any]) -> List[Any]:
    """
    使用快速排序算法对列表进行排序。

    Args:
        arr (List[Any]): 需要排序的列表，列表中的元素必须是可比较的（例如，全是数字或全是字符串）。

    Returns:
        List[Any]: 排序后的新列表。
    """
    if len(arr) <= 1:
        return arr
    
    # For CPU-bound operations like sorting, run in a separate thread
    # to avoid blocking the event loop.
    return await asyncio.to_thread(_quick_sort_sync, arr)

def _quick_sort_sync(arr: List[Any]) -> List[Any]:
    """Synchronous implementation of quicksort."""
    if len(arr) <= 1:
        return arr
    else:
        pivot = arr[len(arr) // 2]
        left = [x for x in arr if x < pivot]
        middle = [x for x in arr if x == pivot]
        right = [x for x in arr if x > pivot]
        return _quick_sort_sync(left) + middle + _quick_sort_sync(right)
