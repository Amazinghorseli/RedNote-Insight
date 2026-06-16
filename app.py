"""
app.py - 小红书爆款雷达（Streamlit 入口）
Phase 1: 基础 RAG 问答
Phase 3: 评论区需求挖掘洞察模式
Phase 4: 查询时自动抓取 — 知识库没有就现场生成
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="小红书爆款雷达", page_icon="🎯", layout="wide")
st.title("🎯 小红书爆款雷达")
st.markdown("---")


# ======================================================================
# 第一部分：一次性初始化（缓存）
# ======================================================================

@st.cache_resource
def init_base():
    """缓存：Embedding / Reranker 等不需要随数据变化而变化的对象"""
    from src.ingestion import load_raw_documents, chunk_documents, load_vectorstore, build_vectorstore, rebuild_all_chunks
    from src.retrievers import APIReranker

    project_root = os.path.dirname(os.path.abspath(__file__))
    raw_dir = os.path.join(project_root, "data", "raw")
    chroma_dir = os.path.join(project_root, "data", "chroma_db")
    chroma_db_file = os.path.join(chroma_dir, "chroma.sqlite3")

    # 检查数据是否存在
    raw_files = [f for f in os.listdir(raw_dir) if f.endswith((".txt", ".md"))] if os.path.exists(raw_dir) else []
    if not raw_files:
        return None, "暂无数据，请用 generate_data.py 生成数据后刷新页面。"

    # 加载或构建向量库
    if os.path.exists(chroma_db_file):
        vectorstore = load_vectorstore()
    else:
        docs = load_raw_documents()
        chunks = chunk_documents(docs)
        vectorstore = build_vectorstore(chunks)

    # Reranker（CrossEncoder API，不随数据变化）
    reranker = APIReranker()

    return {
        "vectorstore": vectorstore,
        "reranker": reranker,
        "raw_dir": raw_dir,
        "chroma_dir": chroma_dir,
    }, None


# ======================================================================
# 第二部分：可变运行时状态（存储在 session_state，支持动态更新）
# ======================================================================

def build_runtime(base: dict):
    """从当前磁盘数据构建 BM25 / HybridRetriever / LangGraph"""
    from src.ingestion import rebuild_all_chunks
    from src.retrievers import HybridRetriever
    from src.graph import build_graph
    from rank_bm25 import BM25Okapi
    import jieba

    vectorstore = base["vectorstore"]
    raw_dir = base["raw_dir"]
    reranker = base["reranker"]

    # 加载全部文档 + chunk
    chunks = rebuild_all_chunks(raw_dir)

    # BM25 索引
    tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
    bm25 = BM25Okapi(tokenized)

    # HybridRetriever
    hybrid_retriever = HybridRetriever(vectorstore, chunks)

    # BM25 搜索函数
    def bm25_search(query: str, k: int = 3):
        tokenized_query = list(jieba.cut(query))
        scores = bm25.get_scores(tokenized_query)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [chunks[i] for i in top_idx]

    # LangGraph
    graph = build_graph(vectorstore, bm25_search, hybrid_retriever, reranker=reranker)

    return {
        "chunks": chunks,
        "bm25": bm25,
        "hybrid_retriever": hybrid_retriever,
        "bm25_search": bm25_search,
        "graph": graph,
    }


def reload_after_fetch():
    """
    当 fetcher 写入了新数据后调用此函数：
    增量入库 → 重建 chunk → 重建 BM25/Hybrid/Graph
    """
    from src.ingestion import incremental_ingest, rebuild_all_chunks
    from src.retrievers import HybridRetriever
    from src.graph import build_graph
    from rank_bm25 import BM25Okapi
    import jieba

    base = st.session_state.base
    vectorstore = base["vectorstore"]
    raw_dir = base["raw_dir"]
    reranker = base["reranker"]

    # 增量入库
    incremental_ingest(raw_dir, vectorstore)

    # 重建全部 chunks（新老数据一起）
    chunks = rebuild_all_chunks(raw_dir)

    # BM25
    tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
    bm25 = BM25Okapi(tokenized)

    # Hybrid
    hybrid_retriever = HybridRetriever(vectorstore, chunks)

    def bm25_search(query: str, k: int = 3):
        tokenized_query = list(jieba.cut(query))
        scores = bm25.get_scores(tokenized_query)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [chunks[i] for i in top_idx]

    # Graph
    graph = build_graph(vectorstore, bm25_search, hybrid_retriever, reranker=reranker)

    # 更新 session_state
    st.session_state.runtime = {
        "chunks": chunks,
        "bm25": bm25,
        "hybrid_retriever": hybrid_retriever,
        "bm25_search": bm25_search,
        "graph": graph,
    }
    st.session_state.data_version += 1


# ======================================================================
# 初始化入口
# ======================================================================

base, error = init_base()
if error:
    st.warning(error)
    st.info("提示: 运行 `python generate_data.py` 生成演示数据。")
    st.stop()

# 保持 base 在 session_state（供 reload_after_fetch 使用）
if "base" not in st.session_state:
    st.session_state.base = base

# 初次或刷新时构建运行时
if "runtime" not in st.session_state:
    st.session_state.runtime = build_runtime(base)
    st.session_state.data_version = 0

runtime = st.session_state.runtime
graph = runtime["graph"]
hybrid_retriever = runtime["hybrid_retriever"]
chunks = runtime["chunks"]
raw_dir = base["raw_dir"]
reranker = base["reranker"]


# ======================================================================
# 第三部分：洞察管道（核心变更：无匹配 → 自动抓取）
# ======================================================================

def run_insight_pipeline(query: str, status_placeholder=None, stream: bool = False):
    """
    完整的洞察流程。
    stream=False: 返回完整字符串（API 模式）
    stream=True: 返回生成器，在生成阶段逐 token yield（Streamlit 流式输出）
    """
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.config import RERANKER_THRESHOLD

    MIN_NOTES = 20
    generator = InsightGenerator()

    def _do_insight(docs, category):
        """文档 → 分析 → 聚合 → 报告（非流式）"""
        analyzer = CommentAnalyzer(raw_dir=raw_dir)
        analyses = analyzer.analyze(docs)
        if not analyses:
            return "没有找到评论分析数据。" if not stream else iter(["没有找到评论分析数据。"])
        aggregator = DemandAggregator()
        aggregated = aggregator.aggregate(analyses)
        if stream:
            return generator.generate_stream(aggregated, category=category)
        try:
            report = generator.generate(aggregated, category=category)
        except Exception as e:
            report = generator.generate_fallback(aggregated, category=category)
            report += f"\n\n（注：LLM 生成失败，使用模板兜底。错误：{e}）"
        return report

    # 1. 扩大检索范围（从 10 → 20 篇）
    docs = hybrid_retriever.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
    if not docs:
        return "检索失败，请刷新页面重试。"

    # 2. CrossEncoder 过滤
    scores = reranker.rerank(query, docs)
    relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]

    if len(relevant) >= MIN_NOTES:
        # ✅ 有足够数据（≥20 篇），正常走管道
        return _do_insight(relevant, query)

    # ❌ 数据不足（< 20 篇）→ 🔥 触发真实爬虫从小红书抓取
    current_count = len(relevant)
    fetch_target = max(MIN_NOTES - current_count + 5, 30)

    if status_placeholder:
        status_placeholder.info(
            f"🔍 品类「**{query}**」当前只有 {current_count} 篇相关笔记，"
            f"正在从小红书实时抓取 {fetch_target} 篇笔记..."
        )

    from src.crawler import CrawlerInterface

    cookies_json = ""
    try:
        cookies_json = st.secrets.get("XHS_COOKIES", "")
    except Exception:
        pass

    crawler = CrawlerInterface(raw_dir=raw_dir, cookies_json=cookies_json)
    if not crawler.is_available:
        if crawler.is_cloud:
            return (f"知识库无「{query}」数据，且云端爬虫未配置 Cookie。\n\n"
                    f"💡 本地运行 `uv run python scripts/export_cookies.py` 导出 cookie，"
                    f"粘贴到 Streamlit Secrets → XHS_COOKIES")
        return (f"知识库无「{query}」数据，且爬虫未登录。\n\n"
                f"💡 请先在命令行运行: `uv run python src/real_crawler.py \"{query}\"` 登录后重试。")

    result = crawler.crawl(query, count=fetch_target)
    count = result["count"]

    if count == 0:
        return f"抱歉，无法从小红书获取「{query}」的数据。请检查网络连接后重试。"

    if status_placeholder:
        status_placeholder.success(f"✅ 已从小红书抓取 {count} 篇「{query}」真实笔记，正在入库并分析...")

    # 增量入库 + 重建索引
    reload_after_fetch()

    # 用更新后的 retriever 重新查询
    import time
    time.sleep(0.5)  # 等 chromadb 落盘
    fresh_docs = st.session_state.runtime["hybrid_retriever"].hybrid_search(
        query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES
    )
    fresh_scores = reranker.rerank(query, fresh_docs)
    fresh_relevant = [doc for doc, s in zip(fresh_docs, fresh_scores) if s >= RERANKER_THRESHOLD]

    if not fresh_relevant:
        return f"已从小红书抓取 {count} 篇「{query}」笔记，但检索仍未匹配。请稍后重试或更换关键词。"

    # 用新数据生成洞察
    report = _do_insight(fresh_relevant, query)
    report = (
        f"（📥 已从小红书实时抓取「{query}」{count} 篇真实笔记，"
        f"当前共 {len(fresh_relevant)} 篇相关笔记）\n\n{report}"
    )
    return report


# ======================================================================
# 第四部分：Streamlit UI
# ======================================================================

# ---- 侧边栏 ----
with st.sidebar:
    st.subheader("模式选择")
    mode = st.radio(
        "运行模式",
        ["问答模式", "洞察模式"],
        index=0,
        help="问答模式：基于知识库回答问题。洞察模式：分析评论区挖掘选品机会。",
    )

    st.markdown("---")
    st.caption(
        f"📊 当前知识库：{len(chunks)} 个 chunk"
        + (f" · 🆕 有新数据" if st.session_state.data_version > 0 else "")
    )

    st.markdown("**使用提示**")
    if mode == "问答模式":
        st.caption(
            "输入产品相关的问题，例如：\n"
            "- 磁吸感应灯哪个品牌好\n"
            "- 学生寝室平价好物推荐\n"
            "- 收纳盒怎么选"
        )
    else:
        st.caption(
            "输入品类名称获取市场洞察，例如：\n"
            "- 磁吸感应灯\n"
            "- 寝室改造\n"
            "- 桌面收纳\n"
            "- 健身服（知识库没有？自动抓取！）"
        )

    if mode == "问答模式":
        st.markdown("---")
        st.subheader("检索策略")
        strategy = st.radio(
            "策略",
            ["auto", "vector", "keyword", "hybrid"],
            index=0,
            help="auto: Supervisor 自动选择",
            label_visibility="collapsed",
        )


# ---- 主界面 ----
if mode == "问答模式":
    # ========== 问答模式 ==========
    st.subheader("💬 问答")

    if "qa_messages" not in st.session_state:
        st.session_state.qa_messages = []

    for msg in st.session_state.qa_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("输入你的问题..."):
        st.session_state.qa_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            status = st.empty()
            with st.spinner("思考中..."):
                result = graph.invoke({
                    "question": prompt,
                    "rewritten_question": "",
                    "strategy": strategy if strategy != "auto" else "",
                    "documents": [],
                    "relevant_docs": [],
                    "generation": "",
                    "retry_count": 0,
                })
                response = result["generation"]

                # 🚀 如果没有答案 → 自动从小红书抓取真实数据 → 重新检索回答
                if "无法回答" in response or "根据现有资料" in response:
                    from src.crawler import CrawlerInterface

                    category = prompt  # 直接用问题作为品类名
                    status.info(f"🔍 知识库中暂无「{category}」相关信息，正在从小红书实时抓取...")

                    cookies_json = ""
                    try:
                        cookies_json = st.secrets.get("XHS_COOKIES", "")
                    except Exception:
                        pass

                    crawler = CrawlerInterface(raw_dir=raw_dir, cookies_json=cookies_json)
                    if not crawler.is_available:
                        status.warning("⚠️ 爬虫未登录，请先在命令行运行: uv run python src/real_crawler.py \"品类名\"")
                    else:
                        result = crawler.crawl(category, count=30)
                        count = result["count"]

                        if count > 0:
                            status.success(f"✅ 已从小红书抓取 {count} 篇「{category}」真实笔记，正在重新检索回答...")
                            reload_after_fetch()

                            import time
                            time.sleep(0.5)

                            # 使用更新后的 graph 重新问答
                            fresh_graph = st.session_state.runtime["graph"]
                            result = fresh_graph.invoke({
                                "question": prompt,
                                "rewritten_question": "",
                                "strategy": strategy if strategy != "auto" else "",
                                "documents": [],
                                "relevant_docs": [],
                                "generation": "",
                                "retry_count": 0,
                            })
                            response = result["generation"]

                            if "无法回答" in response or "根据现有资料" in response:
                                response = (
                                    f"（📥 已从小红书抓取 {count} 篇真实笔记，"
                                    f"但检索仍未匹配到相关信息）\n\n{response}"
                                )
                            else:
                                response = (
                                    f"（📥 已从小红书实时抓取 {count} 篇真实笔记作为知识补充）\n\n{response}"
                                )
                        else:
                            response = f"抱歉，无法从小红书获取「{category}」的数据。请检查网络连接后重试。"

                st.markdown(response)

        st.session_state.qa_messages.append({"role": "assistant", "content": response})

else:
    # ========== 洞察模式 ==========
    st.subheader("📊 选品洞察")

    if "insight_messages" not in st.session_state:
        st.session_state.insight_messages = []

    for msg in st.session_state.insight_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("输入品类名称，例如：磁吸感应灯、健身服..."):
        st.session_state.insight_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            status = st.empty()
            report_container = st.empty()
            with st.spinner("分析评论区数据中..."):
                stream_gen = run_insight_pipeline(prompt, status_placeholder=status, stream=True)
                # 流式输出
                full_report = ""
                for chunk in stream_gen:
                    full_report += chunk
                    report_container.markdown(full_report + "▌")
                report_container.markdown(full_report)

        st.session_state.insight_messages.append({"role": "assistant", "content": full_report})


# ---- 底部 ----
st.markdown("---")
st.caption(f"🎯 小红书爆款雷达 v0.3 · 问答 + 洞察 + 自动抓取 · 数据版本 {st.session_state.data_version}")
