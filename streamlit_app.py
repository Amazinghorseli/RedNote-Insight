"""
streamlit_app.py — Streamlit Cloud 部署入口 (v2.0)
====================================================
保留修复：st.session_state 初始化（避开了 @st.cache_resource 的 DOM bug）
恢复经典 UI：st.chat_message + st.chat_input 对话气泡风格
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="小红书爆款雷达", page_icon="🎯", layout="wide")

# ============================================================
# 初始化 AppState（无任何 Streamlit UI 元素）
# ============================================================
if "app_state" not in st.session_state:
    from src.core.state import AppState
    _s = AppState()
    _s.init_sync()
    st.session_state.app_state = _s
    st.session_state.data_version = 0

_state = st.session_state.app_state

if not _state.is_ready:
    st.title("🎯 小红书爆款雷达")
    st.error(f"应用启动失败：{_state.error}")
    st.info("请检查 API Key 是否有效，或联系开发者。")
    st.stop()

st.title("🎯 小红书爆款雷达")
st.caption("翻评论 · 找痛点 · 定方向 — AI 选品洞察引擎")

# ============================================================
# 重建索引
# ============================================================
def rebuild_indexes():
    _state.rebuild_sync()
    st.session_state.data_version += 1


# ============================================================
# 自动抓取工具
# ============================================================
def _auto_fetch(keyword: str, count: int = 30) -> int:
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
# 洞察管道（流式，适配 st.write_stream）
# ============================================================
def run_insight_stream(query: str):
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
            yield gen.generate_fallback(aggregated, category=category) + f"\n\n（LLM 降级为模板。错误：{e}）"

    docs = hr.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES) or []
    scores = reranker.rerank(query, docs) if docs else []
    relevant = [d for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]

    if len(relevant) >= 3:
        yield from _do_insight(relevant, query)
        return

    yield f"📊 知识库中「{query}」相关数据较少（{len(relevant)} 篇），正在自动抓取...\n\n"
    c = _auto_fetch(query, count=30)
    if c == 0:
        yield (f"无法获取「{query}」的数据。\n\n"
               f"💡 请先在命令行运行:\n`uv run python src/real_crawler.py \"{query}\"`\n"
               f"或配置 Streamlit Secrets → XHS_COOKIES")
        return

    yield f"（📥 已从小红书抓取 {c} 篇真实笔记）\n\n"
    import time; time.sleep(0.5)
    fresh = _state.hybrid_retriever.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
    fresh_scores = reranker.rerank(query, fresh) if fresh else []
    fresh_rel = [d for d, s in zip(fresh, fresh_scores) if s >= RERANKER_THRESHOLD]
    if not fresh_rel:
        yield f"已抓取 {c} 篇但未匹配到相关内容，请稍后重试。"
        return
    yield from _do_insight(fresh_rel, query)


# ============================================================
# QA 管道
# ============================================================
def run_qa(query: str) -> str:
    from src.config import RERANKER_THRESHOLD
    from src.core.query_utils import clean_query, is_brand_comparison
    from src.core.prompt_loader import get_prompt_loader
    from langchain_openai import ChatOpenAI
    from src.config import LLM_CONFIG

    cleaned = clean_query(query)
    k = 8 if is_brand_comparison(cleaned) else 5
    docs = _state.hybrid_retriever.hybrid_search(cleaned, k=k, bm25_k=max(40, k*5), final_k=k)
    if not docs:
        return ""
    scores = _state.reranker.rerank(cleaned, docs)
    scored = sorted([(d, s) for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD], key=lambda x: x[1], reverse=True)
    docs = [d for d, _ in scored] if scored else docs[:5]
    context = "\n---\n".join(f"[文档{i+1}] {d.page_content}" for i, d in enumerate(docs)) or "暂无相关文档"
    prompt = get_prompt_loader().load("gen_answer", "v2")
    msg = prompt.format_messages(context=context, question=query)
    llm = ChatOpenAI(**LLM_CONFIG)
    return llm.invoke(msg).content.strip()


# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    mode = st.radio("运行模式", ["问答模式", "洞察模式", "🕷️ 抓取数据"], index=0)
    st.markdown("---")
    st.caption(f"📊 {_state.stats['total_chunks']} 个 chunk · {_state.stats['total_notes']} 篇笔记"
               + (f" · 🆕 有新数据" if st.session_state.data_version > 0 else ""))

# ============================================================
# 问答模式（经典 chat_message + chat_input 风格）
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
            ans = run_qa(q)

            if not ans or _should_fetch(ans):
                st.markdown("📊 知识库暂无此数据，正在从小红书实时抓取...")
                c = _auto_fetch(q, count=30)
                if c > 0:
                    st.markdown(f"✅ 已抓取 {c} 篇真实笔记，重新检索...")
                    import time; time.sleep(0.5)
                    ans = run_qa(q)
                    if ans and not _should_fetch(ans):
                        ans = f"（📥 已从小红书抓取 {c} 篇真实笔记）\n\n{ans}"
                    else:
                        ans = (f"（📥 已抓取 {c} 篇笔记，但仍未匹配）\n\n{ans or '未找到相关信息'}")
                else:
                    ans = f"{ans}\n\n💡 自动抓取未成功。\n  • 本地: `uv run python src/real_crawler.py \"{q}\"`\n  • 云端: 配置 Streamlit Secrets → XHS_COOKIES"

            st.markdown(ans)
        st.session_state.qa_msgs.append({"role": "assistant", "content": ans})

# ============================================================
# 洞察模式（chat_message + st.write_stream 流式）
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
            report = st.write_stream(run_insight_stream(q))
        st.session_state.is_msgs.append({"role": "assistant", "content": report})

# ============================================================
# 抓取模式
# ============================================================
else:
    st.subheader("🕷️ 真实数据抓取")
    st.caption("打开浏览器抓取小红书真实笔记和评论。首次使用需扫码登录。")

    category = st.text_input("品类名称", placeholder="例如：健身服、蓝牙耳机")
    col1, col2 = st.columns(2)
    with col1:
        count = st.number_input("抓取篇数", min_value=5, max_value=100, value=30)
    with col2:
        with_comments = st.checkbox("同时抓评论", value=True)

    if st.button("🚀 开始抓取", type="primary", disabled=not category):
        log_box = st.container()
        progress_bar = st.progress(0)

        try:
            from src.real_crawler import XHSCrawler
            log_box.info(f"🕷️ 正在打开浏览器...")

            cookies_json = ""
            try:
                cookies_json = st.secrets.get("XHS_COOKIES", "")
            except Exception:
                pass

            crawler = XHSCrawler(cookies_json=cookies_json)

            if not crawler.is_logged_in:
                if crawler.is_cloud_mode:
                    log_box.warning("☁️ 云端模式未登录。请在 Streamlit Secrets 中配置 XHS_COOKIES")
                    log_box.info("💡 本地运行 scripts/export_cookies.py 导出 cookie")
                else:
                    log_box.warning("⚠️ 未登录小红书，正在打开登录页...")
                    log_box.info("👆 请在浏览器窗口中扫码登录")
                    if not crawler.login_interactive():
                        log_box.error("❌ 登录超时，请重试")
                        crawler.close()
                        st.stop()
                    log_box.success("✅ 登录成功！开始抓取...")

            log_box.info(f"🕷️ 正在搜索「{category}」...")
            saved = crawler.crawl(category, count=count, with_comments=with_comments)
            crawler.close()

            if saved > 0:
                rebuild_indexes()
                log_box.success(f"✅ 完成！已抓取 {saved} 篇「{category}」笔记，知识库已更新。")
                progress_bar.progress(100)
            else:
                log_box.error("❌ 未抓取到任何笔记。请检查网络或重新登录。")
        except Exception as e:
            log_box.error(f"❌ 抓取出错: {e}")
            import traceback
            st.code(traceback.format_exc())

# ============================================================
# 底部
# ============================================================
st.markdown("---")
st.caption(f"🎯 小红书爆款雷达 v2.0 · 问答 + 洞察 + 自动抓取 · 数据版本 {st.session_state.data_version}")
