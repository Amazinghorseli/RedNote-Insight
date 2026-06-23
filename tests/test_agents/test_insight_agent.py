"""
test_insight_agent.py — InsightGenerator 单元测试
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestInsightGenerator:
    """InsightGenerator 测试"""

    def _make_aggregated(self, **overrides):
        data = {
            "note_count": 5,
            "avg_likes": 120.0,
            "total_ask_link": 8,
            "top_complaints": [("太贵了", 3), ("质量差", 2)],
            "top_purchase_intents": [("想买", 4), ("求链接", 3)],
            "comparison_patterns": ["品牌A vs 品牌B"],
            "related_brands": ["品牌A", "品牌B"],
            "differentiation_directions": ["材质升级", "功能组合"],
            "evergreen_ratio": 0.8,
            "avg_price": 89.0,
            "avg_cost": 25.0,
            "price_cost_ratio": 3.56,
            "avg_profit_margin": 0.72,
            "avg_weight": 0.3,
            "profit_score": 85,
            "logistics_score": 78,
            "competition_score": 62,
            "demand_score": 90,
            "selection_score": 79,
            "estimated_monthly_sales": 500,
            "avg_return_rate": 0.05,
        }
        data.update(overrides)
        return data

    def test_instantiation(self):
        from src.agents.insight_agent import InsightGenerator
        gen = InsightGenerator()
        assert gen is not None
        assert gen.llm is not None

    def test_generate_fallback_basic(self):
        from src.agents.insight_agent import InsightGenerator
        gen = InsightGenerator()
        aggregated = self._make_aggregated()
        report = gen.generate_fallback(aggregated, category="磁吸感应灯")
        assert "磁吸感应灯" in report
        assert "市场概况" in report
        assert "用户痛点" in report

    def test_generate_fallback_empty_data(self):
        from src.agents.insight_agent import InsightGenerator
        gen = InsightGenerator()
        report = gen.generate_fallback({"note_count": 0}, category="测试")
        assert "没有足够的评论数据" in report

    def test_generate_fallback_low_score_warning(self):
        from src.agents.insight_agent import InsightGenerator
        gen = InsightGenerator()
        aggregated = self._make_aggregated(selection_score=30, competition_score=20)
        report = gen.generate_fallback(aggregated, category="红海品类")
        assert "不建议" in report or "谨慎" in report

    @pytest.mark.asyncio
    async def test_agenerate_returns_report(self):
        """agenerate() 应返回报告文本"""
        from src.agents.insight_agent import InsightGenerator
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock()
        mock_llm.ainvoke.return_value.content = "测试报告内容"

        gen = InsightGenerator(llm=mock_llm)
        aggregated = self._make_aggregated()
        report = await gen.agenerate(aggregated, category="测试品类")
        assert report == "测试报告内容"

    @pytest.mark.asyncio
    async def test_astream_yields_tokens(self):
        """astream() 应逐 token yield"""
        from src.agents.insight_agent import InsightGenerator

        class MockChunk:
            def __init__(self, c):
                self.content = c

        async def mock_astream(msg):
            yield MockChunk("测")
            yield MockChunk("试")

        mock_llm = MagicMock()
        mock_llm.astream = mock_astream

        gen = InsightGenerator(llm=mock_llm)
        aggregated = self._make_aggregated()
        tokens = []
        async for token in gen.astream(aggregated, category="测试"):
            tokens.append(token)
        assert tokens == ["测", "试"]
