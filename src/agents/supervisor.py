"""
supervisor.py - 策略路由智能体
根据用户问题特征，选择最佳检索策略
源自原 step08_multi_agent.py
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import LLM_CONFIG
from src.logger import logger
from src.core.prompt_loader import get_prompt_loader


class Supervisor:
    """Supervisor：LLM 分析问题，选择检索策略"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(**LLM_CONFIG)
        self.prompt_loader = get_prompt_loader()

    def _get_prompt(self):
        """获取 Supervisor prompt（从 YAML 加载）"""
        return self.prompt_loader.load("supervisor", "v1")

    async def adecide(self, question: str, available_strategies: list[str]) -> str:
        """返回选中的策略名（异步版本）"""
        prompt = self._get_prompt()
        msg = prompt.format_messages(question=question)
        response = await self.llm.ainvoke(msg)
        strategy = response.content.strip().lower()
        if strategy not in available_strategies:
            strategy = "hybrid"
        logger.info(f"Supervisor 策略(异步): {strategy}")
        return strategy
