import structlog
import logging
from src.config import settings


def setup_logging() -> structlog.BoundLogger:
    """配置 structlog，返回全局 logger 实例"""

    # 1. 确定输出格式
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # 2. 配置处理器管道
    structlog.configure(
        processors=[
            # ① 注入 contextvars 中的变量（request_id 等）
            structlog.contextvars.merge_contextvars,
            # ② 添加日志级别
            structlog.processors.add_log_level,
            # ③ 添加时间戳
            structlog.processors.TimeStamper(fmt="iso"),
            # ④ 如果日志记录里有异常，格式化堆栈
            structlog.processors.ExceptionPrettyPrinter(),
            # ⑤ 最终输出
            renderer,
        ],
        # 包装标准库 logging，让 FastAPI/Uvicorn 的日志也走 structlog
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


# ── 模块级 logger 实例 ────────────────────────────
logger = setup_logging()