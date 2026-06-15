"""
demand_agent.py - 需求聚合智能体
将 CommentAnalyzer 输出的多条评论分析结果进行聚合统计，
找出高频投诉、热门需求、品牌竞争格局等可行动的信号。
"""
from collections import Counter
from typing import List, Dict, Any


class DemandAggregator:
    """聚合多个文档的评论数据，提取高价值需求信号"""

    def aggregate(self, analyses: List[dict]) -> dict:
        """
        输入：CommentAnalyzer 输出的分析结果列表
        输出：聚合后的需求洞察 + 电商选品评分

        返回结构：
        {
            "note_count": 分析笔记数
            "category": 主要品类
            "top_complaints": [(投诉内容, 频次), ...]
            "top_purchase_intents": [(需求信号, 频次), ...]
            "comparison_patterns": [对比提及, ...]
            "related_brands": [品牌名, ...]
            "total_ask_link": 总求链接数
            "avg_likes": 平均点赞
            "demand_score": 需求热度评分 (0-100)

            # 🧾 新增：电商选品评分
            "avg_price": 平均售价
            "avg_cost": 平均成本
            "avg_profit_margin": 平均利润率
            "avg_weight": 平均重量
            "logistics_score": 物流友好度评分
            "competition_score": 竞争强度评分
            "profit_score": 利润空间评分
            "selection_score": 选品综合评分
            "differentiation_directions": 差异化方向
            "estimated_monthly_sales": 预估月销量
        }
        """
        if not analyses:
            return self._empty_result()

        # ---- 评论类统计（原有） ----
        all_complaints = []
        all_intents = []
        all_comparisons = []
        all_brands = set()
        total_ask = 0
        total_likes = 0

        # ---- 电商选品统计（新增） ----
        total_price = 0
        total_cost = 0
        total_weight = 0.0
        profit_margins = []
        logistics_scores = []
        competition_levels = []
        entry_difficulties = []
        differentiation_ops = []
        total_monthly_sales = 0
        total_return_rate = 0.0
        category_types = []

        for a in analyses:
            all_complaints.extend(a.get("complaints", []))
            all_intents.extend(a.get("purchase_intent", []))
            all_comparisons.extend(a.get("comparison_mentions", []))
            all_brands.update(a.get("related_brands", []))
            total_ask += a.get("ask_link_count", 0)
            total_likes += a.get("likes", 0)

            # 电商数据
            total_price += a.get("price", 0)
            total_cost += a.get("cost", 0)
            total_weight += a.get("weight", 0)
            total_return_rate += a.get("return_rate", 0.05)
            profit_margins.append(a.get("profit_margin", 0))
            competition_levels.append(a.get("competition_level", "中"))
            entry_difficulties.append(a.get("entry_difficulty", "中"))
            differentiation_ops.append(a.get("differentiation_opportunity", ""))
            total_monthly_sales += a.get("estimated_monthly_sales", 0)
            category_types.append(a.get("category_type", "常青款"))

        n = len(analyses)

        # 频次统计
        complaint_freq = Counter(all_complaints).most_common(10)
        intent_freq = Counter(all_intents).most_common(10)
        unique_comparisons = list(dict.fromkeys(all_comparisons))[:10]
        avg_likes = total_likes / n if n > 0 else 0

        # ---- 需求热度评分（原有，略调整） ----
        complaint_diversity = len(set(all_complaints))
        ask_density = total_ask / max(n, 1)
        demand_score = min(
            100,
            int(
                complaint_diversity * 5
                + min(ask_density / 10, 30)
                + min(avg_likes / 20, 20)
                + len(all_brands) * 3
            ),
        )

        # ========== 🧾 新增：电商选品评分 ==========

        avg_price = total_price / n if n > 0 else 0
        avg_cost = total_cost / n if n > 0 else 0
        avg_weight = total_weight / n if n > 0 else 0
        avg_margin = (sum(profit_margins) / len(profit_margins)) if profit_margins else 0.6
        avg_sales = total_monthly_sales // n if n > 0 else 0
        avg_return_rate = round(total_return_rate / n, 2) if n > 0 else 0.05

        # 1️⃣ 利润评分 (基于 3-5倍定价原则)
        if avg_price > 0 and avg_cost > 0:
            price_cost_ratio = avg_price / avg_cost
        else:
            price_cost_ratio = 3.0
        profit_score = min(100, int(
            min(price_cost_ratio / 5, 1.0) * 40 +      # 定价倍率 满分40
            min(avg_margin / 0.7, 1.0) * 40 +          # 利润率 满分40
            20                                          # 基础分
        ))

        # 2️⃣ 物流友好度评分
        logistics_score = min(100, int(
            (avg_weight < 0.3) * 30 +                   # 轻量
            (avg_weight < 1.0) * 15 +                   # 不太重
            35 +                                         # 基础分
            (competition_levels.count("高") < n * 0.5) * 10  # 偏低竞争加分
        ))

        # 3️⃣ 竞争强度评分（分越高越推荐进入）
        low_comp_ratio = competition_levels.count("低") / max(n, 1)
        easy_entry_ratio = entry_difficulties.count("低") / max(n, 1)
        brand_count = len(all_brands)
        competition_score = min(100, int(
            low_comp_ratio * 40 +                       # 低竞争占比
            easy_entry_ratio * 30 +                     # 低进入门槛
            min((5 - brand_count) * 5, 20) +            # 品牌少=机会大
            10                                           # 基础分
        ))

        # 4️⃣ 综合选品评分 (加权)
        selection_score = int(
            profit_score * 0.30 +                        # 利润权重 30%
            logistics_score * 0.20 +                     # 物流权重 20%
            competition_score * 0.20 +                   # 竞争权重 20%
            demand_score * 0.30                          # 需求权重 30%
        )

        # 5️⃣ 差异化方向（去重取前5）
        unique_diffs = list(dict.fromkeys([d for d in differentiation_ops if d]))[:5]

        # 6️⃣ 季节性判断
        evergreen_ratio = category_types.count("常青款") / max(n, 1)

        return {
            "note_count": n,
            "top_complaints": complaint_freq,
            "top_purchase_intents": intent_freq,
            "comparison_patterns": unique_comparisons,
            "related_brands": sorted(all_brands),
            "total_ask_link": total_ask,
            "avg_likes": round(avg_likes, 1),
            "demand_score": demand_score,

            # 电商选品评分
            "avg_price": round(avg_price, 1),
            "avg_cost": round(avg_cost, 1),
            "avg_profit_margin": round(avg_margin, 2),
            "price_cost_ratio": round(price_cost_ratio, 1),
            "avg_weight": round(avg_weight, 2),
            "avg_return_rate": avg_return_rate,
            "profit_score": profit_score,
            "logistics_score": logistics_score,
            "competition_score": competition_score,
            "selection_score": selection_score,
            "differentiation_directions": unique_diffs,
            "estimated_monthly_sales": avg_sales,
            "evergreen_ratio": evergreen_ratio,
        }

    def _empty_result(self) -> dict:
        return {
            "note_count": 0,
            "top_complaints": [],
            "top_purchase_intents": [],
            "comparison_patterns": [],
            "related_brands": [],
            "total_ask_link": 0,
            "avg_likes": 0,
            "demand_score": 0,

            "avg_price": 0,
            "avg_cost": 0,
            "avg_profit_margin": 0,
            "price_cost_ratio": 0,
            "avg_weight": 0,
            "avg_return_rate": 0,
            "profit_score": 0,
            "logistics_score": 0,
            "competition_score": 0,
            "selection_score": 0,
            "differentiation_directions": [],
            "estimated_monthly_sales": 0,
            "evergreen_ratio": 0,
        }
