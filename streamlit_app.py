"""
streamlit_app.py — Streamlit Cloud 部署入口 (v2.0)
====================================================
适配 v2.0 重构架构，使用 AppState 统一状态管理。
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="小红书爆款雷达", page_icon="🎯", layout="wide")
st.title("🎯 小红书爆款雷达")
st.caption("翻评论 · 找痛点 · 定方向 — AI 选品洞察引擎")

# ============================================================
# 初始化 AppState（v2.0 统一状态管理，同步初始化）
# ============================================================
@st.cache_resource(show_spinner=False)
def init_app_state():
    """初始化 AppState，缓存避免重复冷启动"""
    from src.core.state import AppState
    state = AppState()
    state.init_sync()
    return state


_state = init_app_state()

if not _state.is_ready:
    st.error(f"应用启动失败：{_state.error}")
    st.info("请检查 API Key 是否有效，或联系开发者。")
    st.stop()

st.success(f"✅ 知识库就绪 · {_state.stats['total_chunks']} 个文本块 · {_state.stats['total_notes']} 篇笔记")

# ============================================================
# 数据版本跟踪（用于检测新数据）
# ============================================================
if "data_version" not in st.session_state:
    st.session_state.data_version = 0


def rebuild_indexes():
    """重建所有索引（同步版本）"""
    _state.rebuild_sync()
    st.session_state.data_version += 1


# ============================================================
# 自动抓取工具
# ============================================================
def _auto_fetch(keyword: str, count: int = 30) -> int:
    """自动抓取：使用真实爬虫从小红书抓取笔记和评论。返回抓取篇数。"""
    from src.crawler import CrawlerInterface
    cookies_json = ""
    try:
        cookies_json = st.secrets.get("XHS_COOKIES", "")
    except Exception:
        pass
    crawler = CrawlerInterface(raw_dir=_state.raw_dir, cookies_json=cookies_json)
    if not crawler.is_available:
        return 0
    result = crawler.crawl(keyword, count=count)
    c = result["count"]
    if c > 0:
        rebuild_indexes()
    return c


def _should_fetch(answer: str) -> bool:
    triggers = ["无法回答", "根据现有资料", "无法找到", "抱歉", "没有找到",
                 "暂无相关文档", "知识库中暂无"]
    return any(t in answer for t in triggers)


# ============================================================
# 洞察管道（流式）
# ============================================================
def run_insight_stream(query: str, status_placeholder=None):
    """
    洞察管道（流式版本，同步）。
    检索完成后，生成报告时逐 token yield，适配 st.write_stream / 手动流式。
    """
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.config import RERANKER_THRESHOLD

    MIN_NOTES = 10
    hr = _state.hybrid_retriever
    reranker = _state.reranker
    raw_dir = _state.raw_dir

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

    docs = hr.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
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
        yield (f"无法获取「{query}」的数据。\n\n"
               f"💡 请先在「🕷️ 抓取数据」模式中登录小红书，"
               f"或在命令行运行:\n`uv run python src/real_crawler.py \"{query}\"`")
        return

    import time
    time.sleep(0.5)
    fresh = _state.hybrid_retriever.hybrid_search(
        query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES
    )
    fresh_scores = reranker.rerank(query, fresh) if fresh else []
    fresh_rel = [doc for doc, s in zip(fresh, fresh_scores) if s >= RERANKER_THRESHOLD]
    if not fresh_rel:
        yield f"已抓取 {c} 篇但未匹配到相关内容，请稍后重试。"
        return
    yield f"（📥 已从小红书抓取 {c} 篇真实笔记）\n\n"
    yield from _do_insight(fresh_rel, query)


# ============================================================
# QA 管道（适配 v2.0 prompt_loader）
# ============================================================
def run_qa(query: str) -> str:
    """执行单次 QA 问答（同步版本）"""
    from src.config import RERANKER_THRESHOLD
    from src.core.query_utils import clean_query, is_brand_comparison
    from src.core.prompt_loader import get_prompt_loader
    from langchain_openai import ChatOpenAI
    from src.config import LLM_CONFIG

    cleaned = clean_query(query)
    k = 8 if is_brand_comparison(cleaned) else 5

    docs = _state.hybrid_retriever.hybrid_search(
        cleaned, k=k, bm25_k=max(40, k * 5), final_k=k
    )
    if not docs:
        return ""

    scores = _state.reranker.rerank(cleaned, docs)
    scored = sorted(
        [(d, s) for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD],
        key=lambda x: x[1], reverse=True,
    )
    docs = [d for d, _ in scored] if scored else docs[:5]

    context = "\n---\n".join(
        f"[文档{i+1}] {d.page_content}" for i, d in enumerate(docs)
    ) if docs else "暂无相关文档"

    prompt = get_prompt_loader().load("gen_answer", "v2")
    msg = prompt.format_messages(context=context, question=query)
    llm = ChatOpenAI(**LLM_CONFIG)
    resp = llm.invoke(msg)
    return resp.content.strip()


# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    mode = st.radio(
        "运行模式",
        ["问答模式", "洞察模式", "🕷️ 抓取数据"],
        index=0,
    )
    st.markdown("---")
    st.caption(
        f"📊 {_state.stats['total_chunks']} 个 chunk"
        + f" · {_state.stats['total_notes']} 篇笔记"
        + (f" · 🆕 有新数据" if st.session_state.data_version > 0 else "")
    )
    st.markdown("---")
    if mode == "问答模式":
        st.caption(
            "💡 试试问：\n"
            "- 磁吸感应灯哪个品牌好\n"
            "- 学生寝室平价好物推荐\n"
            "- 收纳盒怎么选"
        )
    elif mode == "洞察模式":
        st.caption(
            "💡 输入品类名称，如：\n"
            "- 磁吸感应灯\n"
            "- 寝室改造\n"
            "- 桌面收纳"
        )
    else:
        st.caption(
            "💡 首次使用需扫码登录小红书，\n"
            "之后 cookie 会自动保存复用。"
        )

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
            with st.spinner("检索中..."):
                ans = run_qa(q)

            if not ans or _should_fetch(ans):
                status.info(f"📊 知识库无「{q}」数据，正在从小红书实时抓取...")
                c = _auto_fetch(q, count=30)
                if c > 0:
                    status.info(f"✅ 已抓取 {c} 篇真实笔记，重新检索...")
                    import time
                    time.sleep(0.5)
                    ans = run_qa(q)
                    if ans and not _should_fetch(ans):
                        ans = f"（📥 已从小红书抓取 {c} 篇真实笔记）\n\n{ans}"
                    else:
                        ans = (f"（📥 已抓取 {c} 篇笔记，但仍未匹配）\n\n"
                               f"{ans if ans else '未找到相关信息'}")
                else:
                    ans = (f"{ans}\n\n"
                           f"💡 自动抓取未成功。\n"
                           f"   • 本地：`uv run python src/real_crawler.py \"{q}\"`\n"
                           f"   • 云端：配置 Streamlit Secrets → XHS_COOKIES")

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

            # 云端模式：从 Streamlit Secrets 读取 cookie
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
                # 增量入库 + 重建索引
                rebuild_indexes()
                log_area.success(f"✅ 完成！已抓取 {saved} 篇「{category}」笔记，知识库已更新。")
                progress_bar.progress(100)
            else:
                log_area.error("❌ 未抓取到任何笔记。请检查网络或重新登录。")
        except Exception as e:
            log_area.error(f"❌ 抓取出错: {e}")
            import traceback
            st.code(traceback.format_exc())

# ============================================================
# 底部
# ============================================================
st.markdown("---")
st.caption(
    f"🎯 小红书爆款雷达 v2.0 · 问答 + 洞察 + 自动抓取 · "
    f"数据版本 {st.session_state.data_version}"
)
