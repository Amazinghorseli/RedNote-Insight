"""
insight_agent.py - 选品洞察智能体
基于 DemandAggregator 的聚合结果，用 LLM 生成可执行的市场洞察报告。
是 Phase 3 的最终输出环节。
"""
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.config import LLM_CONFIG
from src.core.prompt_loader import get_prompt_loader


THREE_TIER_HINT = HumanMessage(
    content="⚠️ 重要：在【选品综合评分】之后，必须输出【三档价位选品】章节！"
    "按低价/中价/高价三档展开，每档包含：价格带、产品方向、功能亮点、目标人群、预估利润。"
    "这是硬性要求！"
)


class InsightGenerator:
    """生成可执行的选品建议和市场需求洞察"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(**LLM_CONFIG)
        self.prompt_loader = get_prompt_loader()

    def _get_prompt(self):
        """获取报告 Prompt（从 YAML 加载，v2）"""
        return self.prompt_loader.load("insight_report", "v2")

    def _build_msg(self, aggregated: dict, category: str = "") -> list:
        """构建消息列表（含三档价位强制指令）"""
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
            avg_weight=aggregated.get("avg_weight", 0.3),
            profit_score=aggregated.get("profit_score", 0),
            logistics_score=aggregated.get("logistics_score", 0),
            competition_score=aggregated.get("competition_score", 0),
            demand_score=aggregated.get("demand_score", 0),
            selection_score=aggregated.get("selection_score", 0),
            complaints=complaints_str,
            intents=intents_str,
            comparisons=comparisons_str,
            brands=brands_str,
            differentiations=differentiations_str,
            monthly_sales=aggregated.get("estimated_monthly_sales", 0),
        )
        # 追加三档价位强制指令
        msg.append(THREE_TIER_HINT)
        return msg

    async def agenerate(self, aggregated: dict, category: str = "") -> str:
        """异步版本：输入聚合结果，输出结构化洞察报告"""
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成洞察报告。"

        msg = self._build_msg(aggregated, category)
        response = await self.llm.ainvoke(msg)
        return response.content.strip()

    async def astream(self, aggregated: dict, category: str = ""):
        """异步流式版本：逐 token 生成洞察报告。"""
        if aggregated["note_count"] == 0:
            yield "没有足够的评论数据生成洞察报告。"
            return

        msg = self._build_msg(aggregated, category)
        async for chunk in self.llm.astream(msg):
            if chunk.content:
                yield chunk.content

    def generate_stream(self, aggregated: dict, category: str = "") -> str:
        """流式版本（同步）"""
        if aggregated["note_count"] == 0:
            yield "没有足够的评论数据生成洞察报告。"
            return

        msg = self._build_msg(aggregated, category)
        for chunk in self.llm.stream(msg):
            if chunk.content:
                yield chunk.content

    def generate_fallback(self, aggregated: dict, category: str = "") -> str:
        """
        无 LLM 时的兜底方案：模板化生成电商选品报告
        """
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成洞察报告。"

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📊 电商选品洞察报告 — {category or '未分类'}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        lines.append("【市场概况】")
        lines.append(f"品类：{category or '未分类'}")
        lines.append(f"分析笔记数：{aggregated['note_count']} 篇")
        lines.append(f"平均点赞：{aggregated['avg_likes']} | 总求链接：{aggregated['total_ask_link']}")
        evergreen = aggregated.get("evergreen_ratio", 0.8)
        lines.append(f"季节特性：{'✅ 常青款为主' if evergreen > 0.5 else '⚠️ 偏季节性'}")
        lines.append("")

        lines.append("【利润空间评估】")
        avg_price = aggregated.get("avg_price", 0)
        avg_cost = aggregated.get("avg_cost", 0)
        ratio = aggregated.get("price_cost_ratio", 0)
        margin = aggregated.get("avg_profit_margin", 0)
        profit_score = aggregated.get("profit_score", 0)
        if avg_price > 0:
            lines.append(f"平均售价：¥{avg_price} | 平均成本：¥{avg_cost}")
            lines.append(f"定价倍率：{ratio}x {'✅ 达标(≥3x)' if ratio >= 3 else '⚠️ 偏低(<3x)'}")
            lines.append(f"预估利润率：{margin*100:.0f}%")
            lines.append(f"利润评分：{profit_score}/100")
        else:
            lines.append("（暂无售价数据，建议参考1688/拼多多比价）")
        lines.append("")

        lines.append("【物流友好度】")
        avg_weight = aggregated.get("avg_weight", 0)
        logistics_score = aggregated.get("logistics_score", 0)
        if avg_weight > 0:
            weight_level = "轻量级" if avg_weight < 0.3 else ("中量级" if avg_weight < 1.0 else "重量级")
            lines.append(f"平均重量：{avg_weight}kg（{weight_level}）")
            lines.append(f"物流评分：{logistics_score}/100")
            if logistics_score >= 70:
                lines.append("✅ 适合一件代发，运费可控")
            elif logistics_score >= 40:
                lines.append("⚠️ 注意控制运费和包装成本")
            else:
                lines.append("❌ 物流成本偏高，建议慎入")
        else:
            lines.append("（暂无重量数据）")
        lines.append("")

        lines.append("【竞争格局】")
        comp_score = aggregated.get("competition_score", 50)
        if aggregated["related_brands"]:
            lines.append(f"涉及品牌：{', '.join(aggregated['related_brands'])}")
        lines.append(f"竞争评分：{comp_score}/100（{'✅ 蓝海' if comp_score >= 60 else '⚠️ 中等' if comp_score >= 35 else '❌ 红海'}）")
        if aggregated["comparison_patterns"]:
            lines.append("用户对比：")
            for c in aggregated["comparison_patterns"][:5]:
                lines.append(f"  - {c}")
        lines.append("")

        lines.append(f"【用户痛点 TOP {min(len(aggregated['top_complaints']), 5)}】")
        if aggregated["top_complaints"]:
            for i, (c, f) in enumerate(aggregated["top_complaints"][:5]):
                lines.append(f"  {i+1}. {c}（出现 {f} 次）")
        else:
            lines.append("  暂无明显投诉")
        lines.append("")

        lines.append("【需求信号】")
        if aggregated["top_purchase_intents"]:
            for i, (t, f) in enumerate(aggregated["top_purchase_intents"][:5]):
                lines.append(f"  {i+1}. {t}（出现 {f} 次）")
        else:
            lines.append("  暂无明确信号")
        lines.append("")

        lines.append("【差异化机会】")
        diffs = aggregated.get("differentiation_directions", [])
        if diffs:
            for d in diffs:
                lines.append(f"  • {d}")
        else:
            lines.append("  建议从差评中挖掘：材质升级、功能组合、场景细分")
        lines.append("")

        # 【三档价位选品】- 兜底版
        lines.append("【三档价位选品】")
        sel_score = aggregated.get("selection_score", 0)
        if avg_price > 0:
            low_price = max(30, int(avg_price * 0.4))
            mid_price = int(avg_price * 0.8)
            high_price = int(avg_price * 1.5)
            lines.append(f"  💰 低价位（走量引流款）：¥{low_price}-{int(low_price*1.5)}")
            lines.append(f"     - 基础功能款，锁定价格敏感用户，利润率约{int(margin*100*0.7)}%")
            lines.append(f"  💰 中价位（利润主力款）：¥{mid_price}-{int(mid_price*1.4)}")
            lines.append(f"     - 主流功能+品质升级，利润率约{int(margin*100)}%")
            lines.append(f"  💰 高价位（品牌形象款）：¥{high_price}-{int(high_price*1.6)}")
            lines.append(f"     - 高端材质/设计，利润率约{int(margin*100*1.2)}%")
        else:
            lines.append("  （需补充价格数据后生成）")
        lines.append("")

        lines.append("【选品综合评分】")
        lines.append(f"┌─────────────────────┬──────┐")
        lines.append(f"│       维度          │ 评分  │")
        lines.append(f"├─────────────────────┼──────┤")
        lines.append(f"│ 利润空间            │ {aggregated.get('profit_score', 0):>3}  │")
        lines.append(f"│ 物流友好            │ {aggregated.get('logistics_score', 0):>3}  │")
        lines.append(f"│ 竞争强度(分越高越好) │ {aggregated.get('competition_score', 0):>3}  │")
        lines.append(f"│ 市场需求            │ {aggregated.get('demand_score', 0):>3}  │")
        lines.append(f"├─────────────────────┼──────┤")
        lines.append(f"│ 选品综合评分         │ {sel_score:>3}  │")
        lines.append(f"└─────────────────────┴──────┘")
        if sel_score >= 70:
            lines.append("✅ 推荐进入，综合条件良好")
        elif sel_score >= 45:
            lines.append("⚠️ 可尝试，注意控制风险")
        else:
            lines.append("❌ 不建议，综合条件不理想")
        lines.append("")

        lines.append("【避坑提醒】")
        avg_return = aggregated.get("avg_return_rate", 0.05)
        warnings = []
        if sel_score < 45:
            warnings.append("综合评分偏低，建议寻找替代品类")
        if avg_return > 0.08:
            warnings.append(f"退货率偏高({avg_return*100:.0f}%)，注意控制品质")
        if comp_score < 35:
            warnings.append("竞争激烈，可能需要大量广告投入")
        if evergreen < 0.5:
            warnings.append("季节性较强，需提前1.5-2个月布局")
        if aggregated.get("avg_weight", 0) > 1.0:
            warnings.append("重量较大，注意运费成本")
        if not warnings:
            warnings.append("暂无明显风险，按正常选品流程推进即可")
        for w in warnings:
            lines.append(f"  ⚠ {w}")
        lines.append("")

        est_sales = aggregated.get("estimated_monthly_sales", 0)
        if est_sales > 0:
            lines.append(f"📈 市场参考：预估月销量 {est_sales} 件")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if sel_score >= 70:
            lines.append("💡 一句话点评：值得入局，快速测款！")
        elif sel_score >= 45:
            lines.append("💡 一句话点评：有空间，但需做差异化。")
        else:
            lines.append("💡 一句话点评：谨慎再谨慎，找找其他赛道。")

        return "\n".join(lines)
