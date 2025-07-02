from typing import Dict
from server import mcp
import asyncio
from logger import log as logger

@mcp.tool()
async def greet_user(name: str) -> Dict:
    """
    Greets the user with a personalized message.

    Args:
        name: The name of the user to greet.

    Returns:
        A dictionary containing the greeting message.
    """
    logger.info(f"Generating greeting for user: {name}")
    greeting = f"Hello, {name}! Welcome!"
    logger.success(f"Generated greeting: '{greeting}'")
    return {"message": greeting}
