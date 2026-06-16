"""
test_demand_agent.py — DemandAggregator 单元测试
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.demand_agent import DemandAggregator


def _make_analysis(
    complaints: list[str] = None,
    purchase_intent: list[str] = None,
    comparison_mentions: list[str] = None,
    related_brands: list[str] = None,
    ask_link_count: int = 0,
    likes: int = 50,
    price: float = 100,
    cost: float = 30,
    weight: float = 0.3,
    profit_margin: float = 0.7,
    competition_level: str = "中",
    entry_difficulty: str = "中",
    estimated_monthly_sales: int = 200,
    category_type: str = "常青款",
    return_rate: float = 0.05,
) -> dict:
    return {
        "complaints": complaints or [],
        "purchase_intent": purchase_intent or [],
        "comparison_mentions": comparison_mentions or [],
        "related_brands": related_brands or [],
        "ask_link_count": ask_link_count,
        "likes": likes,
        "price": price,
        "cost": cost,
        "weight": weight,
        "profit_margin": profit_margin,
        "competition_level": competition_level,
        "entry_difficulty": entry_difficulty,
        "estimated_monthly_sales": estimated_monthly_sales,
        "category_type": category_type,
        "return_rate": return_rate,
    }


class TestDemandAggregator:
    """DemandAggregator.aggregate() 测试"""

    def test_empty_input_returns_empty_result(self):
        agg = DemandAggregator()
        result = agg.aggregate([])
        assert result["note_count"] == 0
        assert result["top_complaints"] == []
        assert result["selection_score"] == 0

    def test_single_analysis_basic_stats(self):
        agg = DemandAggregator()
        result = agg.aggregate([
            _make_analysis(
                complaints=["太贵了", "质量差"],
                purchase_intent=["想买"],
                related_brands=["品牌A"],
                ask_link_count=3,
                likes=100,
            )
        ])
        assert result["note_count"] == 1
        assert result["avg_likes"] == 100.0
        assert result["total_ask_link"] == 3
        assert len(result["related_brands"]) == 1

    def test_multiple_analyses_avg_price(self):
        agg = DemandAggregator()
        analyses = [
            _make_analysis(price=80, cost=20),
            _make_analysis(price=120, cost=40),
            _make_analysis(price=100, cost=30),
        ]
        result = agg.aggregate(analyses)
        assert result["avg_price"] == 100.0
        assert result["avg_cost"] == 30.0

    def test_complaint_frequency_aggregation(self):
        agg = DemandAggregator()
        analyses = [
            _make_analysis(complaints=["太贵", "质量差"]),
            _make_analysis(complaints=["太贵", "不实用"]),
            _make_analysis(complaints=["太贵", "质量差", "售后差"]),
        ]
        result = agg.aggregate(analyses)
        top_complaints = result["top_complaints"]
        # "太贵" 出现 3 次，排第一
        assert top_complaints[0][0] == "太贵"
        assert top_complaints[0][1] == 3

    def test_profit_score_high_margin(self):
        """高利润率应得高利润分"""
        agg = DemandAggregator()
        result = agg.aggregate([
            _make_analysis(price=100, cost=10, profit_margin=0.9),
        ])
        assert result["profit_score"] >= 70

    def test_profit_score_low_margin(self):
        """低利润率应得低利润分"""
        agg = DemandAggregator()
        result = agg.aggregate([
            _make_analysis(price=50, cost=45, profit_margin=0.1),
        ])
        assert result["profit_score"] < 60

    def test_weight_affects_logistics_score(self):
        """重量越大物流分越低"""
        agg_light = DemandAggregator()
        r_light = agg_light.aggregate([
            _make_analysis(weight=0.1),
        ])
        agg_heavy = DemandAggregator()
        r_heavy = agg_heavy.aggregate([
            _make_analysis(weight=2.0),
        ])
        assert r_light["logistics_score"] >= r_heavy["logistics_score"]

    def test_low_competition_boosts_score(self):
        """低竞争品类竞争分更高"""
        agg = DemandAggregator()
        result = agg.aggregate([
            _make_analysis(competition_level="低", entry_difficulty="低"),
            _make_analysis(competition_level="低", entry_difficulty="低"),
        ])
        assert result["competition_score"] >= 60

    def test_evergreen_ratio_calculation(self):
        agg = DemandAggregator()
        result = agg.aggregate([
            _make_analysis(category_type="常青款"),
            _make_analysis(category_type="常青款"),
            _make_analysis(category_type="季节性"),
        ])
        assert result["evergreen_ratio"] == pytest.approx(2 / 3, abs=0.01)

    def test_empty_analysis_produces_fallback(self):
        """确保 _empty_result() 被正确调用"""
        agg = DemandAggregator()
        result = agg.aggregate(None)  # type: ignore
        assert result["note_count"] == 0
        assert result["selection_score"] == 0
