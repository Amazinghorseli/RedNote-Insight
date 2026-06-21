"""
app.py - 小红书爆款雷达（Streamlit 入口）
===========================================
Day 4 重构：删除了与 AppState 重复的 build_runtime / reload_after_fetch 逻辑，
改用 AppState 统一管理运行时状态。
"""
import streamlit as st
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="小红书爆款雷达", page_icon="🎯", layout="wide")
st.title("🎯 小红书爆款雷达")
st.markdown("---")


# ======================================================================
# 第一部分：初始化（委托给 AppState）
# ======================================================================

@st.cache_resource
def init_app_state_sync():
    """Streamlit cache_resource 装饰器确保只执行一次。

    AppState.init_sync() 内部新建事件循环运行 async 初始化。
    """
    from src.core.state import AppState
    state = AppState()
    state.init_sync()
    if state.error:
        return state, state.error
    return state, None


state, error = init_app_state_sync()
if error:
    st.warning(error)
    st.info("提示: 运行 `python generate_data.py` 生成演示数据。")
    st.stop()


if "data_version" not in st.session_state:
    st.session_state.data_version = 0

graph = state.graph
hybrid_retriever = state.hybrid_retriever
chunks = state.chunks
raw_dir = state.raw_dir
reranker = state.reranker


# ======================================================================
# 第二部分：洞察管道
# ======================================================================

def run_insight_pipeline(query: str, status_placeholder=None, stream: bool = False):
    """完整洞察流程（同步，Streamlit 环境）"""
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.config import RERANKER_THRESHOLD

    MIN_NOTES = 20
    generator = InsightGenerator()

    def _do_insight(docs, category):
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

    docs = hybrid_retriever.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
    if not docs:
        return "检索失败，请刷新页面重试。"

    scores = reranker.rerank(query, docs)
    relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]

    if len(relevant) >= MIN_NOTES:
        return _do_insight(relevant, query)

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

    # ✅ Day 4: 委托给 AppState 统一重建
    state.rebuild_sync()
    st.session_state.data_version += 1

    time.sleep(0.5)
    fresh_docs = state.hybrid_retriever.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
    fresh_scores = reranker.rerank(query, fresh_docs)
    fresh_relevant = [doc for doc, s in zip(fresh_docs, fresh_scores) if s >= RERANKER_THRESHOLD]

    if not fresh_relevant:
        return f"已从小红书抓取 {count} 篇「{query}」笔记，但检索仍未匹配。请稍后重试或更换关键词。"

    report = _do_insight(fresh_relevant, query)
    report = (f"（📥 已从小红书实时抓取「{query}」{count} 篇真实笔记，"
              f"当前共 {len(fresh_relevant)} 篇相关笔记）\n\n{report}")
    return report


# ======================================================================
# 第三部分：Streamlit UI
# ======================================================================

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

                if "无法回答" in response or "根据现有资料" in response:
                    from src.crawler import CrawlerInterface

                    category = prompt
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
                            # ✅ Day 4: 委托给 AppState 统一重建
                            state.rebuild_sync()
                            st.session_state.data_version += 1

                            time.sleep(0.5)

                            graph = state.graph
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

                            if "无法回答" in response or "根据现有资料" in response:
                                response = (f"（📥 已从小红书抓取 {count} 篇真实笔记，"
                                            f"但检索仍未匹配到相关信息）\n\n{response}")
                            else:
                                response = (f"（📥 已从小红书实时抓取 {count} 篇真实笔记作为知识补充）\n\n{response}")
                        else:
                            response = f"抱歉，无法从小红书获取「{category}」的数据。请检查网络连接后重试。"

                st.markdown(response)

        st.session_state.qa_messages.append({"role": "assistant", "content": response})

else:
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
                full_report = ""
                for chunk in stream_gen:
                    full_report += chunk
                    report_container.markdown(full_report + "▌")
                report_container.markdown(full_report)

        st.session_state.insight_messages.append({"role": "assistant", "content": full_report})


st.markdown("---")
st.caption(f"🎯 小红书爆款雷达 v0.4 · 问答 + 洞察 + 自动抓取 · 数据版本 {st.session_state.data_version}")
