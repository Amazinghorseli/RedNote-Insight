"""
mcp_tools.py — 小红书爆款雷达的 MCP 工具封装

把项目中 CommentAnalyzer / DemandAggregator / InsightGenerator
三个 Agent 类的能力暴露为标准的 MCP 工具。

运行方式：
  uv run python src/mcp_tools.py
  → 启动 MCP Server，等待 Client 连接
"""

import json

# ============================================================
# 导入 MCP 核心
# ============================================================
from mcp.server.fastmcp import FastMCP

# ============================================================
# 导入项目已有的 Agent 类
# ============================================================
from src.agents.comment_agent import CommentAnalyzer
from src.agents.demand_agent import DemandAggregator
from src.agents.insight_agent import InsightGenerator
from src.crawler import CrawlerInterface
from src.config import RAW_DIR

# ============================================================
# 创建 MCP Server 实例
# ============================================================
mcp = FastMCP(
    "xiaohongshu-insight",
    instructions="""我提供小红书电商选品的分析工具：
    1. 分析笔记评论区，提取投诉和需求信号
    2. 聚合多条评论数据，统计高频需求和热度评分
    3. 基于聚合数据生成选品洞察报告
    4. 当知识库缺乏某品类数据时，自动生成该品类的小红书笔记并入库
    """
)


# ============================================================
# 工具 1：分析笔记评论区
# ============================================================
@mcp.tool()
async def analyze_comments(category: str, max_notes: int = 5) -> str:
    """
    搜索某品类的笔记并分析评论区，提取用户投诉和购买意向

    Args:
        category: 品类名称（如"磁吸感应灯"、"健身服"）
        max_notes: 最多分析的笔记数（默认 5 篇）

    Returns:
        结构化的评论分析结果 JSON
    """
    from src.ingestion import rebuild_all_chunks, load_vectorstore
    from src.retrievers import HybridRetriever, APIReranker
    from src.config import RERANKER_THRESHOLD

    chunks = rebuild_all_chunks(RAW_DIR)
    if not chunks:
        return json.dumps({"error": "知识库为空，请先生成数据"}, ensure_ascii=False)

    try:
        vectorstore = load_vectorstore()
    except Exception:
        return json.dumps({"error": "向量库加载失败"}, ensure_ascii=False)

    retriever = HybridRetriever(vectorstore, chunks)
    reranker = APIReranker()

    docs = retriever.hybrid_search(category, k=10, bm25_k=25, final_k=10)
    if not docs:
        return json.dumps({"category": category, "notes": [], "message": "未找到相关笔记"}, ensure_ascii=False)

    scores = reranker.rerank(category, docs)
    relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD][:max_notes]

    if not relevant:
        return json.dumps({"category": category, "notes": [], "message": "未找到相关内容"}, ensure_ascii=False)

    analyzer = CommentAnalyzer(raw_dir=RAW_DIR)
    analyses = analyzer.analyze(relevant)

    return json.dumps({
        "category": category,
        "note_count": len(analyses),
        "analyses": analyses
    }, ensure_ascii=False, indent=2)


# ============================================================
# 工具 2：聚合多条评论分析结果
# ============================================================
@mcp.tool()
async def aggregate_demands(analyses_json: str) -> str:
    """
    聚合多条评论分析数据，统计高频投诉、需求信号、计算热度评分

    Args:
        analyses_json: analyze_comments 工具输出的 JSON 字符串

    Returns:
        聚合后的需求洞察 JSON
    """
    data = json.loads(analyses_json)
    analyses = data.get("analyses", data) if isinstance(data, dict) else data

    aggregator = DemandAggregator()
    result = aggregator.aggregate(analyses)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
# 工具 3：生成选品洞察报告
# ============================================================
@mcp.tool()
async def generate_insight_report(aggregated_json: str, category: str) -> str:
    """
    基于聚合后的需求数据生成结构化的选品洞察报告

    Args:
        aggregated_json: aggregate_demands 输出的 JSON 字符串
        category: 品类名称

    Returns:
        结构化的文本报告
    """
    aggregated = json.loads(aggregated_json)
    generator = InsightGenerator()

    try:
        report = generator.generate(aggregated, category=category)
    except Exception as e:
        report = generator.generate_fallback(aggregated, category=category)
        report += f"\n\n（注：LLM 生成失败，已自动降级为模板。错误：{str(e)}）"

    return report


# ============================================================
# 工具 4：按需抓取品类数据
# ============================================================
@mcp.tool()
async def fetch_category_data(category: str, count: int = 30) -> str:
    """
    当知识库缺少某品类数据时，从小红书真实抓取笔记和评论并入库。
    首次使用需先在命令行运行 `uv run python src/real_crawler.py \"品类名\"` 登录。

    Args:
        category: 品类名称（如"健身服"、"蓝牙耳机"）
        count: 要抓取的笔记数量（默认 30 篇）

    Returns:
        抓取结果说明
    """
    crawler = CrawlerInterface(raw_dir=RAW_DIR)

    if not crawler.is_available:
        return json.dumps({
            "success": False,
            "category": category,
            "generated_count": 0,
            "message": f"爬虫未登录。请先在命令行运行: uv run python src/real_crawler.py \"{category}\" 登录后重试"
        }, ensure_ascii=False)

    result = crawler.crawl(category, count=count)

    return json.dumps({
        "success": result["count"] > 0,
        "category": category,
        "generated_count": result["count"],
        "method": result["method"],
        "message": f"已从小红书抓取 {result['count']} 篇「{category}」真实笔记，存放在 data/raw/"
    }, ensure_ascii=False)


# ============================================================
# 启动入口（永远在最后）
# ============================================================
if __name__ == "__main__":
    print("🚀 小红书爆款雷达 MCP Server 启动中...")
    print("   可用工具将在 Client 连接时自动发现")
    mcp.run()
