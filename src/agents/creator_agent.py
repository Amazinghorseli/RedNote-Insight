"""
creator_agent.py — 自媒体选题引擎

与 InsightGenerator 并行：同一份 DemandAggregator 输出，不同的 prompt 模板。
把用户评论数据变成选题 + 脚本大纲 + 封面方案。
"""
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.config import LLM_CONFIG
from src.core.prompt_loader import get_prompt_loader


class CreatorGenerator:
    """基于评论区数据生成内容创作方案"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(**LLM_CONFIG)
        self.prompt_loader = get_prompt_loader()

    def _get_prompt(self):
        return self.prompt_loader.load("creator_report", "v1")

    def _build_msg(self, aggregated: dict, category: str = "") -> list:
        complaints_str = "\n".join(
            f"  {i+1}. 「{c}」出现 {f} 次"
            for i, (c, f) in enumerate(aggregated["top_complaints"][:10])
        ) or "  暂无"

        intents_str = "\n".join(
            f"  {i+1}. 「{t}」出现 {f} 次"
            for i, (t, f) in enumerate(aggregated["top_purchase_intents"][:10])
        ) or "  暂无"

        comparisons_str = "\n".join(
            f"  - {c}" for c in aggregated["comparison_patterns"][:10]
        ) or "  暂无"

        brands_str = ", ".join(aggregated["related_brands"]) or "暂无"
        differentiations_str = ", ".join(aggregated.get("differentiation_directions", [])) or "暂无"

        msg = self._get_prompt().format_messages(
            category=category or "未分类",
            note_count=aggregated["note_count"],
            avg_likes=aggregated["avg_likes"],
            total_ask_link=aggregated["total_ask_link"],
            evergreen_ratio=int(aggregated.get("evergreen_ratio", 0.8) * 100),
            avg_price=aggregated.get("avg_price", 0),
            avg_cost=aggregated.get("avg_cost", 0),
            price_cost_ratio=aggregated.get("price_cost_ratio", 3),
            profit_margin=int(aggregated.get("avg_profit_margin", 0.6) * 100),
            complaints=complaints_str,
            intents=intents_str,
            comparisons=comparisons_str,
            brands=brands_str,
            differentiations=differentiations_str,
        )
        return msg

    async def agenerate(self, aggregated: dict, category: str = "") -> str:
        """异步生成选题方案"""
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成选题方案。"

        msg = self._build_msg(aggregated, category)
        response = await self.llm.ainvoke(msg)
        return response.content.strip()

    async def astream(self, aggregated: dict, category: str = ""):
        """异步流式输出"""
        if aggregated["note_count"] == 0:
            yield "没有足够的评论数据生成选题方案。"
            return

        msg = self._build_msg(aggregated, category)
        async for chunk in self.llm.astream(msg):
            if chunk.content:
                yield chunk.content

    def generate_fallback(self, aggregated: dict, category: str = "") -> str:
        """无 LLM 时的兜底模板"""
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成选题方案。"

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🎬 自媒体选题方案 — {category or '未分类'}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        lines.append("【数据亮点】")
        pain_count = len(aggregated["top_complaints"])
        intent_count = len(aggregated["top_purchase_intents"])
        lines.append(f"  📊 {aggregated['note_count']}篇笔记 → {pain_count}个痛点 + {intent_count}个需求信号")
        lines.append("")

        lines.append("【核心选题方向】")
        if aggregated["top_complaints"]:
            top_pain, count = aggregated["top_complaints"][0]
            lines.append(f"  🔥 避坑选题：{top_pain}（{count}次提及）→ 《别再买{category}踩坑了，{top_pain}》")
        if len(aggregated["top_complaints"]) >= 2:
            second_pain, _ = aggregated["top_complaints"][1]
            lines.append(f"  📝 测评选题：{second_pain} → 《我测了N款{category}，告诉你哪款不{second_pain}》")
        if aggregated["related_brands"]:
            brands = aggregated["related_brands"][:3]
            lines.append(f"  ⚔️ 对比选题：{', '.join(brands)} → 《{', '.join(brands)}到底选哪个？》")
        lines.append("")

        lines.append("【脚本结构参考】")
        lines.append('  前5秒：用数据钩子 — "每天X人搜索这个问题"')
        if aggregated["top_complaints"]:
            top_pain, _ = aggregated["top_complaints"][0]
            lines.append(f"  5-15秒：痛点共鸣 — 引用真实评论「{top_pain}」")
        lines.append("  核心段：实测/对比/推荐")
        lines.append("  结尾：金句 + 引导评论「你踩过这个坑吗？」")
        lines.append("")

        lines.append("【发布建议】")
        lines.append("  🕐 黄金发布：工作日晚 19:00-21:00")
        lines.append("  🏷️ 核心标签：#避坑 #真实测评 #好物推荐")
        lines.append("")

        return "\n".join(lines)
