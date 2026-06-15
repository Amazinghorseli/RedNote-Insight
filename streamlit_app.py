"""
streamlit_app.py — Streamlit Cloud 部署入口
============================================
独立版 Streamlit 界面，适配 Streamlit Cloud 部署环境。
初始化过程显示进度，避免白屏等待。
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# 必须先显示页面，再初始化（避免白屏）
# ============================================================
st.set_page_config(page_title="小红书爆款雷达", page_icon="🎯", layout="wide")
st.title("🎯 小红书爆款雷达")
st.caption("翻评论 · 找痛点 · 定方向 — AI 选品洞察引擎")

# ============================================================
# 初始化（带进度提示）
# ============================================================
@st.cache_resource(show_spinner=False)
def init_app():
    """初始化向量库和 LangGraph，缓存结果避免重复调用"""
    status = st.empty()
    progress = st.empty()

    try:
        from src.ingestion import load_raw_documents, chunk_documents, build_vectorstore, rebuild_all_chunks
        from src.retrievers import HybridRetriever, APIReranker
        from src.graph import build_graph
        from rank_bm25 import BM25Okapi
        import jieba

        project_root = os.path.dirname(os.path.abspath(__file__))
        raw_dir = os.path.join(project_root, "data", "raw")
        chroma_dir = os.path.join(project_root, "data", "chroma_db")

        # Step 1: 加载文档
        status.info("📂 正在加载笔记文档...")
        try:
            from src.ingestion import load_vectorstore
            vectorstore = load_vectorstore()
            status.success("✅ 向量库已加载")
        except Exception:
            status.info("🔨 正在构建向量库（首次部署需要 1-2 分钟）...")
            docs = load_raw_documents()
            chunks = chunk_documents(docs)
            progress.info(f"📊 共 {len(chunks)} 个文本块，正在向量化...")
            vectorstore = build_vectorstore(chunks)
            status.success(f"✅ 向量库构建完成（{len(chunks)} 个块）")

        # Step 2: 加载 Reranker
        reranker = APIReranker()

        # Step 3: 构建检索器
        chunks = rebuild_all_chunks(raw_dir)
        tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
        bm25 = BM25Okapi(tokenized)
        hybrid_retriever = HybridRetriever(vectorstore, chunks)

        def bm25_search(query: str, k: int = 3):
            tokenized_query = list(jieba.cut(query))
            scores = bm25.get_scores(tokenized_query)
            top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
            return [chunks[i] for i in top_idx]

        # Step 4: 构建 LangGraph
        graph = build_graph(vectorstore, bm25_search, hybrid_retriever, reranker=reranker)

        status.success("")
        progress.empty()
        return {
            "ok": True,
            "vectorstore": vectorstore,
            "chunks": chunks,
            "hybrid_retriever": hybrid_retriever,
            "bm25_search": bm25_search,
            "graph": graph,
            "reranker": reranker,
            "raw_dir": raw_dir,
            "total_chunks": len(chunks),
        }

    except Exception as e:
        status.error(f"❌ 初始化失败: {e}")
        return {"ok": False, "error": str(e)}


state = init_app()

if not state["ok"]:
    st.error(f"应用启动失败：{state['error']}")
    st.info("请检查 API Key 是否有效，或联系开发者。")
    st.stop()

st.success(f"✅ 知识库就绪 · {state['total_chunks']} 个文本块")

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    mode = st.radio("运行模式", ["问答模式", "洞察模式", "🕷️ 抓取数据"], index=0)
    st.caption(f"📊 {state['total_chunks']} 个 chunk 已就绪")
    st.caption("🕷️ 抓取模式仅限本地使用，首次需扫码登录")

# ============================================================
# 洞察管道
# ============================================================
def run_insight(query: str, status_placeholder=None) -> str:
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.config import RERANKER_THRESHOLD
    from src.crawler import CrawlerInterface

    MIN_NOTES = 10
    hr = state["hybrid_retriever"]
    reranker = state["reranker"]
    raw_dir = state["raw_dir"]

    def _do_insight(docs, category):
        analyzer = CommentAnalyzer(raw_dir=raw_dir)
        analyses = analyzer.analyze(docs)
        if not analyses:
            return "没有找到评论分析数据。"
        aggregator = DemandAggregator()
        aggregated = aggregator.aggregate(analyses)
        generator = InsightGenerator()
        try:
            return generator.generate(aggregated, category=category)
        except Exception as e:
            return generator.generate_fallback(aggregated, category=category) + f"\n\n（LLM 降级为模板。错误：{e}）"

    docs = hr.hybrid_search(query, k=MIN_NOTES, bm25_k=30, final_k=MIN_NOTES)
    if not docs:
        return "检索失败，请刷新重试。"

    scores = reranker.rerank(query, docs)
    relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]

    if len(relevant) >= 3:
        return _do_insight(relevant, query)
    else:
        if status_placeholder:
            status_placeholder.info(f"数据不足（{len(relevant)} 篇），正在自动抓取...")
        crawler = CrawlerInterface(raw_dir=raw_dir)
        result = crawler.crawl(query, count=15)
        count = result["count"]
        if count == 0:
            return f"无法获取「{query}」的数据。"
        # 增量入库
        from src.ingestion import incremental_ingest, rebuild_all_chunks
        incremental_ingest(raw_dir, state["vectorstore"])
        chunks = rebuild_all_chunks(raw_dir)
        from rank_bm25 import BM25Okapi
        import jieba
        tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
        state["bm25"] = BM25Okapi(tokenized)
        state["chunks"] = chunks
        hr2 = HybridRetriever(state["vectorstore"], chunks)
        state["hybrid_retriever"] = hr2
        fresh = hr2.hybrid_search(query, k=MIN_NOTES)
        fresh_rel = [d for d, s in zip(fresh, reranker.rerank(query, fresh)) if s >= RERANKER_THRESHOLD]
        if not fresh_rel:
            return f"已生成 {count} 篇笔记但检索未匹配。"
        return f"（📥 已生成 {count} 篇笔记）\n\n{_do_insight(fresh_rel, query)}"


# ============================================================
# 问答模式
# ============================================================
if mode == "问答模式":
    st.subheader("💬 智能问答")

    if "qa_msgs" not in st.session_state:
        st.session_state.qa_msgs = []
    for m in st.session_state.qa_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if q := st.chat_input("输入问题..."):
        st.session_state.qa_msgs.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                result = state["graph"].invoke({
                    "question": q, "rewritten_question": "",
                    "strategy": "", "documents": [], "relevant_docs": [],
                    "generation": "", "retry_count": 0,
                })
                ans = result["generation"]
                if "无法回答" in ans:
                    from src.fetcher import OnDemandFetcher
                    fetcher = OnDemandFetcher(raw_dir=state["raw_dir"])
                    c = fetcher.fetch(q, count=10)
                    if c > 0:
                        ans = f"（📥 已生成 {c} 篇笔记）\n\n{ans}"
                st.markdown(ans)
        st.session_state.qa_msgs.append({"role": "assistant", "content": ans})

# ============================================================
# 洞察模式
# ============================================================
elif mode == "洞察模式":
    st.subheader("📊 选品洞察")

    if "is_msgs" not in st.session_state:
        st.session_state.is_msgs = []
    for m in st.session_state.is_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if q := st.chat_input("输入品类，如：磁吸感应灯、健身服..."):
        st.session_state.is_msgs.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            s = st.empty()
            with st.spinner("分析中..."):
                report = run_insight(q, s)
                st.markdown(report)
        st.session_state.is_msgs.append({"role": "assistant", "content": report})

# ============================================================
# 抓取模式
# ============================================================
else:
    st.subheader("🕷️ 真实数据抓取")
    st.caption("打开浏览器抓取小红书真实笔记和评论。首次使用需扫码登录。")

    category = st.text_input("品类名称", placeholder="例如：健身服、蓝牙耳机、磁吸感应灯")
    col1, col2 = st.columns(2)
    with col1:
        count = st.number_input("抓取篇数", min_value=5, max_value=100, value=30)
    with col2:
        with_comments = st.checkbox("同时抓评论", value=True)

    if st.button("🚀 开始抓取", type="primary", disabled=not category):
        log_area = st.empty()
        progress_bar = st.progress(0)

        try:
            from src.real_crawler import XHSCrawler
            log_area.info(f"🕷️ 正在打开浏览器搜索「{category}」...")

            crawler = XHSCrawler()
            saved = crawler.crawl(category, count=count, with_comments=with_comments)
            crawler.close()

            if saved > 0:
                # 增量入库
                from src.ingestion import incremental_ingest, rebuild_all_chunks
                incremental_ingest(state["raw_dir"], state["vectorstore"])
                chunks = rebuild_all_chunks(state["raw_dir"])
                from rank_bm25 import BM25Okapi
                import jieba
                tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
                state["bm25"] = BM25Okapi(tokenized)
                state["chunks"] = chunks
                state["total_chunks"] = len(chunks)
                from src.retrievers import HybridRetriever
                hr = HybridRetriever(state["vectorstore"], chunks)
                state["hybrid_retriever"] = hr
                def bms(q2, k=3):
                    scores = state["bm25"].get_scores(list(jieba.cut(q2)))
                    return [chunks[i] for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]]
                state["bm25_search"] = bms
                from src.graph import build_graph
                state["graph"] = build_graph(state["vectorstore"], bms, hr, reranker=state["reranker"])

                log_area.success(f"✅ 完成！已抓取 {saved} 篇「{category}」笔记，知识库已更新。")
                progress_bar.progress(100)
            else:
                log_area.error("❌ 未抓取到任何笔记。请检查网络或重新登录。")
        except Exception as e:
            log_area.error(f"❌ 抓取出错: {e}")
            import traceback
            st.code(traceback.format_exc())
