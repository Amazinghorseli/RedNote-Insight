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
        """无 LLM 时的兜底模板（2-3个方案）"""
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成选题方案。"

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🎬 自媒体选题方案 — {category or '未分类'}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("【数据亮点】")
        lines.append(f"  📊 {aggregated['note_count']}篇笔记 → {len(aggregated['top_complaints'])}个痛点 + {len(aggregated['top_purchase_intents'])}个需求信号")
        lines.append("")

        # 提取数据
        pains = aggregated["top_complaints"]
        intents = aggregated["top_purchase_intents"]
        brands = aggregated.get("related_brands", [])
        avg_price = aggregated.get("avg_price", 0)
        avg_cost = aggregated.get("avg_cost", 0)

        # 方案1: 避坑/测评向
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【方案一】🔍 避坑测评")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if pains:
            pain = pains[0][0]
            lines.append(f"  标题：《{category}避坑指南：{pain}？实测N款告诉你真相》")
            lines.append("  类型：测评/避坑 | 平台：小红书+B站 | 预计互动：⭐⭐⭐⭐")
        else:
            lines.append(f"  标题：《{category}选购避坑指南，买前必看》")
        lines.append("")
        lines.append("  【脚本大纲】")
        lines.append(f"   前5秒：展示热门{category}产品，抛出问题「{pains[0][0] if pains else '买错等于浪费钱'}」")
        lines.append("   5-15秒：引用真实评论引发共鸣")
        if len(pains) >= 2:
            lines.append(f"         「{pains[0][0]}」「{pains[1][0]}」")
        lines.append(f"   核心段：选3款{category}横向对比 → 加分项 → 扣分项 → 推荐结论")
        lines.append("   结尾金句：「选品不跟风，跟着数据走」")
        lines.append("   互动引导：「你买过哪款踩坑了？评论区曝光它」")
        lines.append("")

        # 方案2: 推荐/种草向
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【方案二】🌟 好物种草")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if intents:
            intent = intents[0][0]
            lines.append(f"  标题：《{category}年度好物！解决{intent}的神器来了》")
            lines.append("  类型：种草/好物推荐 | 平台：小红书+抖音 | 预计互动：⭐⭐⭐⭐⭐")
        else:
            lines.append(f"  标题：《{category}年度好物大盘点》")
        lines.append("")
        lines.append("  【脚本大纲】")
        lines.append(f"   前5秒：直接展示{category}使用效果「这也太好用了吧」")
        if intents:
            lines.append(f"   5-15秒：抛出用户最大需求「{intents[0][0] if intents else '想要高性价比'}」")
        lines.append(f"   核心段：第1件→第2件→第3件，每件15秒展示+口播")
        lines.append("   结尾：「评论区告诉我你最想试哪款」")
        lines.append("   互动引导：收藏+关注，下期继续挖宝")
        lines.append("")

        # 方案3: 对比/横评向
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【方案三】⚔️ 品牌横评")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if len(brands) >= 2:
            lines.append(f"  标题：《{brands[0]} vs {brands[1]} vs {brands[2] if len(brands)>=3 else brands[1]}，{category}谁更强？》")
        else:
            lines.append(f"  标题：《{category}热门品牌横评，到底选哪个？》")
        lines.append("  类型：对比评测 | 平台：B站+小红书 | 预计互动：⭐⭐⭐⭐")
        lines.append("")
        lines.append("  【脚本大纲】")
        lines.append(f"   前5秒：三款{category}并排展示「今天不废话，直接上数据」")
        lines.append(f"   5-15秒：列出{len(pains)}个用户最关心的维度")
        lines.append("   核心段：同类对比→价格对比→真实体验→胜出者揭晓")
        lines.append("   结尾：「省钱攻略已备好，记得收藏」")
        lines.append("   互动引导：「你还想看我测什么？评论区点菜」")
        lines.append("")

        # 发布建议
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【发布策略】（适用于3个方案）")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("  🕐 推荐发布：工作日 19:00-21:00 或周末 10:00-12:00")
        lines.append(f"  🏷️ 核心标签：")
        lines.append(f"     方案一：#避坑 #真实测评 #购物踩雷")
        lines.append(f"     方案二：#好物推荐 #种草 #年度爱用")
        lines.append(f"     方案三：#对比评测 #理性消费 #品牌测评")
        if avg_price > 0:
            lines.append(f"  💰 客单价 ¥{avg_price}，适合新品牌用方案一打口碑，老品牌用方案二冲销量")
        lines.append("")

        return "\n".join(lines)
