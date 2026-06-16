"""
logger.py — 统一日志系统
=========================
替换项目中的 print() 调用，支持：
- 控制台 + 文件双输出
- 时间戳 + 级别 + 模块名
- DEBUG/INFO/WARNING/ERROR 四级
"""
import logging
import os

LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)

logger = logging.getLogger("xhs-insight")
