"""
observability.py — LangFuse 可观测性集成
=============================================
提供 LangFuse CallbackHandler，注入 LangChain/LangGraph 调用链。

用法:
    from src.core.observability import get_langfuse_handler

    handler = get_langfuse_handler()
    result = await graph.ainvoke(state, config={"callbacks": [handler]})
"""

from src.config import settings
from src.logger import logger


_langfuse_handler = None


def get_langfuse_handler():
    """获取 LangFuse CallbackHandler（懒加载单例）

    如果未配置 LANGFUSE_PUBLIC_KEY，返回 None（不影响正常功能）。
    """
    global _langfuse_handler

    if _langfuse_handler is not None:
        return _langfuse_handler

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.info("langfuse_disabled", reason="no_api_keys")
        _langfuse_handler = None
        return None

    try:
        from langfuse.langchain import CallbackHandler

        _langfuse_handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("langfuse_initialized", host=settings.langfuse_host)
        return _langfuse_handler
    except ImportError:
        logger.warning("langfuse_not_installed", hint="pip install langfuse")
        _langfuse_handler = None
        return None
    except Exception as e:
        logger.error("langfuse_init_failed", error=str(e))
        _langfuse_handler = None
        return None


def is_langfuse_enabled() -> bool:
    """检查 LangFuse 是否可用"""
    handler = get_langfuse_handler()
    return handler is not None
