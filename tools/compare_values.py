from server import mcp
from typing import Dict, Union
import asyncio
from logger import log as logger

@mcp.tool()
async def compare_values(value1: Union[int, float], value2: Union[int, float]) -> Dict[str, str]:
    """
    Compares two numerical values and returns the result.

    :param value1: The first numerical value for comparison.
    :param value2: The second numerical value for comparison.
    :return: A dictionary containing a string that describes whether the first value is greater than, less than, or equal to the second value.
    """
    logger.info(f"Comparing values: {value1} and {value2}")
    if value1 > value2:
        result = f"{value1} is greater than {value2}."
    elif value1 < value2:
        result = f"{value1} is less than {value2}."
    else:
        result = f"{value1} is equal to {value2}."
    
    logger.success(f"Comparison result: {result}")
    return {"comparison_result": result}
