"""
supervisor.py - 策略路由智能体
根据用户问题特征，选择最佳检索策略
源自原 step08_multi_agent.py
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import LLM_CONFIG
from src.logger import logger


class Supervisor:
    """Supervisor：LLM 分析问题，选择检索策略"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(**LLM_CONFIG)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "分析问题特征，选择最佳检索策略：\n"
             "- vector：概念性、描述性问题\n"
             "- keyword：专有名词、缩写、代码\n"
             "- hybrid：通用场景\n"
             "只输出策略名，不要其他内容。"),
            ("human", "{question}"),
        ])

    def decide(self, question: str, available_strategies: list[str]) -> str:
        """返回选中的策略名"""
        msg = self.prompt.format_messages(question=question)
        strategy = self.llm.invoke(msg).content.strip().lower()
        if strategy not in available_strategies:
            strategy = "hybrid"
        logger.info(f"Supervisor 策略: {strategy}")
        return strategy
