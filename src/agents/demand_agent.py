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
        输出：聚合后的需求洞察

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
        }
        """
        if not analyses:
            return self._empty_result()

        # ---- 统计 ----
        all_complaints = []
        all_intents = []
        all_comparisons = []
        all_brands = set()
        total_ask = 0
        total_likes = 0

        for a in analyses:
            all_complaints.extend(a.get("complaints", []))
            all_intents.extend(a.get("purchase_intent", []))
            all_comparisons.extend(a.get("comparison_mentions", []))
            all_brands.update(a.get("related_brands", []))
            total_ask += a.get("ask_link_count", 0)
            total_likes += a.get("likes", 0)

        # 频次统计
        complaint_freq = Counter(all_complaints).most_common(10)
        intent_freq = Counter(all_intents).most_common(10)

        # 去重后保留前 10 条对比提及
        unique_comparisons = list(dict.fromkeys(all_comparisons))[:10]

        n = len(analyses)
        avg_likes = total_likes / n if n > 0 else 0

        # ---- 需求热度评分 ----
        # 基于：投诉多样性 + 求链接密度 + 互动量
        complaint_diversity = len(set(all_complaints))
        ask_density = total_ask / max(n, 1)
        demand_score = min(
            100,
            int(
                complaint_diversity * 5          # 投诉种类越多 → 需求越丰富
                + min(ask_density / 10, 30)      # 求链接越多 → 购买意向强
                + min(avg_likes / 20, 20)        # 平均点赞高 → 热度高
                + len(all_brands) * 3            # 品牌多 → 竞争激烈
            ),
        )

        return {
            "note_count": n,
            "top_complaints": complaint_freq,
            "top_purchase_intents": intent_freq,
            "comparison_patterns": unique_comparisons,
            "related_brands": sorted(all_brands),
            "total_ask_link": total_ask,
            "avg_likes": round(avg_likes, 1),
            "demand_score": demand_score,
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
        }
