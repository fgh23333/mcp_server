from typing import Dict
from server import mcp
import asyncio
from typing import Dict

@mcp.tool()
async def greet_user(name: str) -> Dict:
    """
    Greets the user with a personalized message.

    Args:
        name: The name of the user to greet.

    Returns:
        A dictionary containing the greeting message.
    """
    greeting = f"Hello, {name}! Welcome!"
    return {"message": greeting}
