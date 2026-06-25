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
        from src.graph import build_async_graph
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
        graph = build_async_graph(vectorstore, bm25_search, hybrid_retriever, reranker=reranker)

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
# 共用工具
# ============================================================
def _rebuild():
    """增量入库后重建所有检索器和 LangGraph"""
    from src.ingestion import incremental_ingest, rebuild_all_chunks
    from src.retrievers import HybridRetriever
    from rank_bm25 import BM25Okapi
    import jieba
    incremental_ingest(state["raw_dir"], state["vectorstore"])
    chunks = rebuild_all_chunks(state["raw_dir"])
    tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
    state["bm25"] = BM25Okapi(tokenized)
    state["chunks"] = chunks
    state["total_chunks"] = len(chunks)
    hr = HybridRetriever(state["vectorstore"], chunks)
    state["hybrid_retriever"] = hr
    def bms(q2, k=3):
        scores = state["bm25"].get_scores(list(jieba.cut(q2)))
        return [chunks[i] for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]]
    state["bm25_search"] = bms
    from src.graph import build_async_graph
    state["graph"] = build_async_graph(state["vectorstore"], bms, hr, reranker=state["reranker"])

def _auto_fetch(keyword: str, count: int = 30) -> int:
    """自动抓取：使用真实爬虫从小红书抓取笔记和评论。返回抓取篇数。"""
    from src.crawler import CrawlerInterface
    # 云端模式：从 Streamlit Secrets 读取 cookie
    cookies_json = ""
    try:
        cookies_json = st.secrets.get("XHS_COOKIES", "")
    except Exception:
        pass
    crawler = CrawlerInterface(raw_dir=state["raw_dir"], cookies_json=cookies_json)
    if not crawler.is_available:
        return 0
    result = crawler.crawl(keyword, count=count)
    c = result["count"]
    if c > 0:
        _rebuild()
    return c

def _should_fetch(answer: str) -> bool:
    triggers = ["无法回答", "根据现有资料", "无法找到", "抱歉", "没有找到"]
    return any(t in answer for t in triggers)

# ============================================================
# 洞察管道
# ============================================================
def run_insight(query: str, status_placeholder=None) -> str:
    """洞察管道（非流式，兼容旧调用）"""
    result = list(run_insight_stream(query, status_placeholder))
    return result[-1] if result else ""


def run_insight_stream(query: str, status_placeholder=None):
    """
    洞察管道（流式版本）。
    检索完成后，生成报告时逐 token yield，适配 st.write_stream。
    """
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.config import RERANKER_THRESHOLD

    MIN_NOTES = 10
    hr = state["hybrid_retriever"]
    reranker = state["reranker"]
    raw_dir = state["raw_dir"]

    def _do_insight(docs, category):
        analyzer = CommentAnalyzer(raw_dir=raw_dir)
        analyses = analyzer.analyze(docs)
        if not analyses:
            yield "没有找到评论分析数据。"
            return
        aggregator = DemandAggregator()
        aggregated = aggregator.aggregate(analyses)
        gen = InsightGenerator()
        try:
            yield from gen.generate_stream(aggregated, category=category)
        except Exception as e:
            fallback = gen.generate_fallback(aggregated, category=category)
            yield fallback + f"\n\n（LLM 降级为模板。错误：{e}）"

    docs = hr.hybrid_search(query, k=MIN_NOTES, bm25_k=30, final_k=MIN_NOTES)
    if not docs:
        docs = []

    scores = reranker.rerank(query, docs) if docs else []
    relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]

    if len(relevant) >= 3:
        yield from _do_insight(relevant, query)
        return

    # 无数据 → 自动抓取 → 重试
    if status_placeholder:
        status_placeholder.info(f"📊 知识库无「{query}」数据，正在自动抓取...")
    c = _auto_fetch(query, count=30)
    if c == 0:
        yield f"无法获取「{query}」的数据。\n\n💡 请先在「🕷️ 抓取数据」模式中登录小红书，或在命令行运行:\n`uv run python src/real_crawler.py \"{query}\"`"
        return

    import time; time.sleep(0.5)
    fresh = state["hybrid_retriever"].hybrid_search(query, k=MIN_NOTES, bm25_k=30, final_k=MIN_NOTES)
    fresh_scores = reranker.rerank(query, fresh) if fresh else []
    fresh_rel = [d for d, s in zip(fresh, fresh_scores) if s >= RERANKER_THRESHOLD]
    if not fresh_rel:
        yield f"已抓取 {c} 篇但未匹配到相关内容，请稍后重试。"
        return
    yield f"（📥 已从小红书抓取 {c} 篇真实笔记）\n\n"
    yield from _do_insight(fresh_rel, query)


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
            status = st.empty()

            def _qa_run(query):
                r = state["graph"].invoke({
                    "question": query, "rewritten_question": "",
                    "strategy": "", "documents": [], "relevant_docs": [],
                    "generation": "", "retry_count": 0,
                })
                return r["generation"]

            with st.spinner("检索中..."):
                ans = _qa_run(q)

            if _should_fetch(ans):
                status.info(f"📊 知识库无「{q}」数据，正在从小红书实时抓取...")
                c = _auto_fetch(q, count=30)
                if c > 0:
                    status.info(f"✅ 已抓取 {c} 篇真实笔记，重新检索...")
                    import time; time.sleep(0.5)
                    ans = _qa_run(q)
                    if _should_fetch(ans):
                        ans = f"（📥 已抓取 {c} 篇笔记，但仍未匹配）\n\n{ans}"
                    else:
                        ans = f"（📥 已从小红书抓取 {c} 篇真实笔记）\n\n{ans}"
                else:
                    ans = (f"{ans}\n\n"
                           f"💡 自动抓取未成功。\n"
                           f"   • 本地：`uv run python src/real_crawler.py \"{q}\"`\n"
                           f"   • 云端：配置 Streamlit Secrets → XHS_COOKIES（运行 scripts/export_cookies.py 导出）")

            status.empty()
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
            report_container = st.empty()
            with st.spinner("分析中..."):
                full_report = ""
                for chunk in run_insight_stream(q, s):
                    full_report += chunk
                    report_container.markdown(full_report + "▌")
                report_container.markdown(full_report)
        st.session_state.is_msgs.append({"role": "assistant", "content": full_report})

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
            log_area.info(f"🕷️ 正在打开浏览器...")

            # 云端模式：从 Secrets 读 cookie
            cookies_json = ""
            try:
                cookies_json = st.secrets.get("XHS_COOKIES", "")
            except Exception:
                pass

            crawler = XHSCrawler(cookies_json=cookies_json)

            # 检查登录状态
            if not crawler.is_logged_in:
                if crawler.is_cloud_mode:
                    log_area.warning("☁️ 云端模式未登录。请在 Streamlit Secrets 中配置 XHS_COOKIES")
                    log_area.info("💡 本地运行 scripts/export_cookies.py 导出 cookie 后粘贴到 Secrets")
                else:
                    log_area.warning("⚠️ 未登录小红书，正在打开登录页...")
                    log_area.info("👆 请在浏览器窗口中扫码登录")
                    if not crawler.login_interactive():
                        log_area.error("❌ 登录超时，请重试")
                        crawler.close()
                        st.stop()
                    log_area.success("✅ 登录成功！开始抓取...")

            log_area.info(f"🕷️ 正在搜索「{category}」...")
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
                from src.graph import build_async_graph
                state["graph"] = build_async_graph(state["vectorstore"], bms, hr, reranker=state["reranker"])

                log_area.success(f"✅ 完成！已抓取 {saved} 篇「{category}」笔记，知识库已更新。")
                progress_bar.progress(100)
            else:
                log_area.error("❌ 未抓取到任何笔记。请检查网络或重新登录。")
        except Exception as e:
            log_area.error(f"❌ 抓取出错: {e}")
            import traceback
            st.code(traceback.format_exc())
