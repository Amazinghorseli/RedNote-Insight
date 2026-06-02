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
        """构建洞察报告 prompt"""
        self.report_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "你是小红书电商选品分析专家。根据用户提供的评论区分析数据，"
                "生成一份专业的市场洞察报告。\n\n"
                "报告要求：\n"
                "1. 用中文，简洁有力，不要套话\n"
                "2. 每条洞察都要有数据支撑（频次、数量）\n"
                "3. 选品建议要具体：价格带 + 功能点 + 目标人群\n"
                "4. 指出竞争空白（用户想要但没有被满足的）\n\n"
                "报告格式：\n"
                "【市场概况】品类热度、相关笔记数\n"
                "【用户痛点 TOP 3】列出最集中的投诉问题\n"
                "【需求信号】用户正在搜索/求购的方向\n"
                "【竞争格局】主要品牌及用户对比\n"
                "【选品建议】2-3 条具体可执行的方向\n"
                "【机会打分】0-100 分，说明理由\n"
            ),
            (
                "human",
                "品类：{category}\n\n"
                "数据概览：\n"
                "- 分析笔记数：{note_count}\n"
                "- 平均点赞：{avg_likes}\n"
                "- 总求链接次数：{total_ask_link}\n\n"
                "用户投诉（按频次排序）：\n{complaints}\n\n"
                "用户需求信号（按频次排序）：\n{intents}\n\n"
                "品牌对比提及：\n{comparisons}\n\n"
                "涉及品牌：{brands}\n\n"
                "需求热度评分：{demand_score}/100\n\n"
                "请输出选品洞察报告：",
            ),
        ])

    def generate(self, aggregated: dict, category: str = "") -> str:
        """
        输入：DemandAggregator 的聚合结果 + 品类名称
        输出：结构化洞察报告文本
        """
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成洞察报告。"

        # 格式化数据供 LLM
        complaints_str = "\n".join(
            f"  {i+1}. 「{c}」出现 {f} 次"
            for i, (c, f) in enumerate(aggregated["top_complaints"][:5])
        ) or "  暂无"

        intents_str = "\n".join(
            f"  {i+1}. 「{t}」出现 {f} 次"
            for i, (t, f) in enumerate(aggregated["top_purchase_intents"][:5])
        ) or "  暂无"

        comparisons_str = "\n".join(
            f"  - {c}" for c in aggregated["comparison_patterns"][:5]
        ) or "  暂无"

        brands_str = ", ".join(aggregated["related_brands"]) or "暂无"

        msg = self.report_prompt.format_messages(
            category=category or "未分类",
            note_count=aggregated["note_count"],
            avg_likes=aggregated["avg_likes"],
            total_ask_link=aggregated["total_ask_link"],
            complaints=complaints_str,
            intents=intents_str,
            comparisons=comparisons_str,
            brands=brands_str,
            demand_score=aggregated["demand_score"],
        )

        response = self.llm.invoke(msg)
        return response.content.strip()

    def generate_fallback(self, aggregated: dict, category: str = "") -> str:
        """
        无 LLM 时的兜底方案：模板化生成报告
        确保离线或 API 不可用时也能输出
        """
        if aggregated["note_count"] == 0:
            return "没有足够的评论数据生成洞察报告。"

        lines = []
        lines.append(f"【市场概况】")
        lines.append(f"品类：{category or '未分类'} | 分析笔记数：{aggregated['note_count']}")
        lines.append(f"平均点赞：{aggregated['avg_likes']} | 总求链接：{aggregated['total_ask_link']}")
        lines.append("")

        lines.append(f"【用户痛点 TOP {min(len(aggregated['top_complaints']), 3)}】")
        if aggregated["top_complaints"]:
            for i, (c, f) in enumerate(aggregated["top_complaints"][:3]):
                lines.append(f"  {i+1}. {c}（出现 {f} 次）")
        else:
            lines.append("  暂无明显投诉")
        lines.append("")

        lines.append("【需求信号】")
        if aggregated["top_purchase_intents"]:
            for i, (t, f) in enumerate(aggregated["top_purchase_intents"][:3]):
                lines.append(f"  {i+1}. {t}（出现 {f} 次）")
        else:
            lines.append("  暂无明确信号")
        lines.append("")

        lines.append("【竞争格局】")
        if aggregated["related_brands"]:
            lines.append(f"  涉及品牌：{', '.join(aggregated['related_brands'])}")
        if aggregated["comparison_patterns"]:
            lines.append("  用户对比：")
            for c in aggregated["comparison_patterns"][:3]:
                lines.append(f"    - {c}")
        lines.append("")

        lines.append(f"【机会打分】{aggregated['demand_score']}/100")
        if aggregated["demand_score"] >= 70:
            lines.append("评分偏高，建议优先关注该品类。")
        elif aggregated["demand_score"] >= 40:
            lines.append("评分中等，可进一步调研。")
        else:
            lines.append("评分偏低，建议暂缓进入。")

        return "\n".join(lines)
