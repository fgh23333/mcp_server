import sys
from loguru import logger

# 移除默认的处理器
logger.remove()

# 添加一个新的处理器，用于将日志输出到控制台
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 添加一个文件处理器，用于将日志记录到文件
logger.add(
    "logs/app.log",
    rotation="10 MB",  # 每10MB创建一个新文件
    retention=False,  # 禁用日志过期，永久保存
    compression="zip",  # 压缩旧的日志文件
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    encoding="utf-8"
)

# 导出配置好的 logger
log = logger
