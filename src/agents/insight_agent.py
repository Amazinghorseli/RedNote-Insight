"""
insight_agent.py - 选品洞察智能体
基于 DemandAggregator 的聚合结果，用 LLM 生成可执行的市场洞察报告。
是 Phase 3 的最终输出环节。
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from src.config import LLM_CONFIG


class InsightGenerator:
    """生成可执行的选品建议和市场需求洞察"""

    def __init__(self, llm=None):
        self.llm = llm or ChatOpenAI(**LLM_CONFIG)
        self._build_prompts()

    def _build_prompts(self):
        """构建电商选品洞察报告 prompt（v2 升级版）"""
        self.report_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "你是小红书电商选品分析专家，同时也是有5年经验的电商小商家。"
                "根据用户提供的评论区数据和电商指标，生成一份专业的**电商选品市场洞察报告**。\n\n"
                "报告要求：\n"
                "1. 以电商小商家的视角来分析，关注**可执行性**和**利润**\n"
                "2. 每条洞察都要有数据支撑（频次、利润率、评分等）\n"
                "3. 选品建议要具体：价格带 + 功能点 + 目标人群 + 预估利润\n"
                "4. 指出竞争空白（用户想要但没有被满足的）和差异化机会\n"
                "5. 评估物流友好度和售后风险\n"
                "6. 数据量充足，尽量覆盖更多用户反馈\n\n"
                "报告格式（严格按以下结构输出）：\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "【市场概况】品类热度、分析笔记数、季节特性（常青/季节性）\n"
                "【利润空间评估】平均售价/成本、定价倍率、预估利润率、是否达到3-5倍选品标准\n"
                "【物流友好度】平均重量、破损风险、运费预估、仓储难度\n"
                "【竞争格局】主要品牌、品牌集中度、新卖家进入难度\n"
                "【用户痛点 TOP 5】列出最集中的投诉问题（至少5条，覆盖面要广）\n"
                "【需求信号】用户正在搜索/求购的方向（至少5条）\n"
                "【差异化机会】基于差评的升级方向：材质/功能/组合/场景/颜色等\n"
                "【选品综合评分】利润/物流/竞争/需求四维雷达评分 + 总分\n"
                "【选品建议】4-5条具体可执行方向，含价格带+功能点+目标人群+预估利润\n"
                "【避坑提醒】该品类的潜在风险（退货率、售后、侵权、季节性等）\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "最后加一句总结性的一句话点评。"
            ),
            (
                "human",
                "品类：{category}\n\n"
                "===== 数据概览 =====\n"
                "分析笔记数：{note_count} 篇\n"
                "平均点赞：{avg_likes} | 总求链接：{total_ask_link}\n"
                "常青款占比：{evergreen_ratio}%\n\n"
                "===== 电商指标 =====\n"
                "平均售价：¥{avg_price} | 平均成本：¥{avg_cost}\n"
                "定价倍率(售价/成本)：{price_cost_ratio}x\n"
                "平均利润率：{profit_margin}%\n"
                "平均重量：{avg_weight}kg\n\n"
                "===== 选品评分 =====\n"
                "利润评分：{profit_score}/100\n"
                "物流评分：{logistics_score}/100\n"
                "竞争评分：{competition_score}/100\n"
                "需求热度：{demand_score}/100\n"
                "选品综合评分：{selection_score}/100\n\n"
                "===== 用户反馈 =====\n"
                "用户投诉（按频次排序）：\n{complaints}\n\n"
                "用户需求信号（按频次排序）：\n{intents}\n\n"
                "品牌对比提及：\n{comparisons}\n\n"
                "涉及品牌：{brands}\n\n"
                "差异化方向参考：{differentiations}\n"
                "预估月销量参考：{monthly_sales} 件\n\n"
                "请输出电商选品洞察报告：",
            ),
        ])

    def generate(self, aggregated: dict, category: str = "") -> str:
        """
        输入：DemandAggregator 的聚合结果 + 品类名称
        输出：结构化电商选品洞察报告文本
        """
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成洞察报告。"

        # 格式化评论数据
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

        msg = self.report_prompt.format_messages(
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

        response = self.llm.invoke(msg)
        return response.content.strip()

    def generate_fallback(self, aggregated: dict, category: str = "") -> str:
        """
        无 LLM 时的兜底方案：模板化生成电商选品报告
        确保离线或 API 不可用时也能输出
        """
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成洞察报告。"

        lines = []
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📊 电商选品洞察报告 — {category or '未分类'}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # 【市场概况】
        lines.append("【市场概况】")
        lines.append(f"品类：{category or '未分类'}")
        lines.append(f"分析笔记数：{aggregated['note_count']} 篇")
        lines.append(f"平均点赞：{aggregated['avg_likes']} | 总求链接：{aggregated['total_ask_link']}")
        evergreen = aggregated.get("evergreen_ratio", 0.8)
        lines.append(f"季节特性：{'✅ 常青款为主' if evergreen > 0.5 else '⚠️ 偏季节性'}")
        lines.append("")

        # 【利润空间评估】
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

        # 【物流友好度】
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

        # 【竞争格局】
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

        # 【用户痛点 TOP 5】
        lines.append(f"【用户痛点 TOP {min(len(aggregated['top_complaints']), 5)}】")
        if aggregated["top_complaints"]:
            for i, (c, f) in enumerate(aggregated["top_complaints"][:5]):
                lines.append(f"  {i+1}. {c}（出现 {f} 次）")
        else:
            lines.append("  暂无明显投诉")
        lines.append("")

        # 【需求信号】
        lines.append("【需求信号】")
        if aggregated["top_purchase_intents"]:
            for i, (t, f) in enumerate(aggregated["top_purchase_intents"][:5]):
                lines.append(f"  {i+1}. {t}（出现 {f} 次）")
        else:
            lines.append("  暂无明确信号")
        lines.append("")

        # 【差异化机会】
        lines.append("【差异化机会】")
        diffs = aggregated.get("differentiation_directions", [])
        if diffs:
            for d in diffs:
                lines.append(f"  • {d}")
        else:
            lines.append("  建议从差评中挖掘：材质升级、功能组合、场景细分")
        lines.append("")

        # 【选品综合评分】
        lines.append("【选品综合评分】")
        sel_score = aggregated.get("selection_score", 0)
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

        # 【避坑提醒】
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

        # 销量参考
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
