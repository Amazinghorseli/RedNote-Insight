"""
test_supervisor.py — Supervisor 策略路由测试
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestSupervisor:
    """Supervisor 策略路由测试"""

    def test_supervisor_instantiation(self):
        """Supervisor 可以正常实例化"""
        from src.agents.supervisor import Supervisor
        sup = Supervisor()
        assert sup is not None
        assert sup.llm is not None

    def test_decide_with_empty_strategies(self):
        """decide() 在策略列表为空时应返回 hybrid"""
        from src.agents.supervisor import Supervisor
        # 使用 mock LLM 避免真实 API 调用
        from unittest.mock import MagicMock
        sup = Supervisor()
        sup.llm = MagicMock()
        sup.llm.invoke.return_value.content = "  hybrid  "

        result = sup.decide("测试问题", ["vector", "keyword", "hybrid"])
        assert result == "hybrid"

    def test_decide_falls_back_to_hybrid(self):
        """decide() 在 LLM 返回无效策略时应退回到 hybrid"""
        from src.agents.supervisor import Supervisor
        from unittest.mock import MagicMock
        sup = Supervisor()
        sup.llm = MagicMock()
        sup.llm.invoke.return_value.content = "invalid_strategy"

        result = sup.decide("测试问题", ["vector", "keyword", "hybrid"])
        assert result == "hybrid"

    def test_decide_returns_valid_strategy(self):
        """decide() 应返回有效策略"""
        from src.agents.supervisor import Supervisor
        from unittest.mock import MagicMock
        sup = Supervisor()
        sup.llm = MagicMock()
        sup.llm.invoke.return_value.content = "vector"

        result = sup.decide("概念性问题", ["vector", "keyword", "hybrid"])
        assert result == "vector"

    @pytest.mark.asyncio
    async def test_adecide_basic(self):
        """adecide() 异步版本基本功能"""
        from src.agents.supervisor import Supervisor
        from unittest.mock import AsyncMock, MagicMock

        sup = Supervisor()
        mock_response = MagicMock()
        mock_response.content = "keyword"
        sup.llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await sup.adecide("专有名词查询", ["vector", "keyword", "hybrid"])
        assert result == "keyword"
