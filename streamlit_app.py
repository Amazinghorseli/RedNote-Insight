"""
streamlit_app.py — 小红书爆款雷达 v3.0
========================================
对标原版 FastAPI 前端：灵感库 + 发现机会(双报告) + 问答 + 导入
"""
import streamlit as st
import sys
import os
import time
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="小红书爆款雷达", page_icon="🎯", layout="wide")

# ============================================================
# 初始化 AppState
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


# ============================================================
# 工具函数
# ============================================================
def rebuild_indexes():
    _state.rebuild_sync()
    st.session_state.data_version += 1


# ============================================================
# 热榜/灵感库数据
# ============================================================
@st.cache_data(ttl=300)
def get_trending_keywords() -> list:
    """从内置词库获取热榜关键词"""
    hot_kw = [
        # 🏠 家居日用 (20)
        {"keyword": "磁吸感应灯", "category": "家居", "trend": "up"},
        {"keyword": "桌面收纳", "category": "家居", "trend": "up"},
        {"keyword": "收纳盒", "category": "家居", "trend": "stable"},
        {"keyword": "装饰画", "category": "家居", "trend": "up"},
        {"keyword": "香薰", "category": "家居", "trend": "up"},
        {"keyword": "地毯", "category": "家居", "trend": "stable"},
        {"keyword": "窗帘", "category": "家居", "trend": "stable"},
        {"keyword": "抱枕", "category": "家居", "trend": "stable"},
        {"keyword": "花瓶", "category": "家居", "trend": "up"},
        {"keyword": "挂钟", "category": "家居", "trend": "stable"},
        {"keyword": "台灯", "category": "家居", "trend": "up"},
        {"keyword": "落地灯", "category": "家居", "trend": "up"},
        {"keyword": "沙发垫", "category": "家居", "trend": "stable"},
        {"keyword": "门帘", "category": "家居", "trend": "up"},
        {"keyword": "墙面置物架", "category": "家居", "trend": "up"},
        {"keyword": "冰箱贴", "category": "家居", "trend": "up"},
        {"keyword": "杯垫", "category": "家居", "trend": "stable"},
        {"keyword": "家居拖鞋", "category": "家居", "trend": "stable"},
        {"keyword": "衣架", "category": "家居", "trend": "up"},
        {"keyword": "收纳柜", "category": "家居", "trend": "up"},
        # 👗 服饰 (15)
        {"keyword": "健身服", "category": "服饰", "trend": "up"},
        {"keyword": "风衣", "category": "服饰", "trend": "seasonal"},
        {"keyword": "瑜伽裤", "category": "服饰", "trend": "up"},
        {"keyword": "冲锋衣", "category": "服饰", "trend": "up"},
        {"keyword": "防晒衣", "category": "服饰", "trend": "up"},
        {"keyword": "阔腿裤", "category": "服饰", "trend": "up"},
        {"keyword": "针织衫", "category": "服饰", "trend": "seasonal"},
        {"keyword": "卫衣", "category": "服饰", "trend": "stable"},
        {"keyword": "羽绒服", "category": "服饰", "trend": "seasonal"},
        {"keyword": "连衣裙", "category": "服饰", "trend": "stable"},
        {"keyword": "真丝睡衣", "category": "服饰", "trend": "up"},
        {"keyword": "袜子", "category": "服饰", "trend": "stable"},
        {"keyword": "打底衫", "category": "服饰", "trend": "stable"},
        {"keyword": "运动鞋", "category": "服饰", "trend": "up"},
        {"keyword": "棒球帽", "category": "服饰", "trend": "up"},
        # 🍜 食品 (10)
        {"keyword": "辣条", "category": "食品", "trend": "stable"},
        {"keyword": "养生茶", "category": "食品", "trend": "up"},
        {"keyword": "即食早餐", "category": "食品", "trend": "up"},
        {"keyword": "代餐奶昔", "category": "食品", "trend": "up"},
        {"keyword": "低卡零食", "category": "食品", "trend": "up"},
        {"keyword": "坚果礼盒", "category": "食品", "trend": "stable"},
        {"keyword": "速溶咖啡", "category": "食品", "trend": "stable"},
        {"keyword": "冻干水果", "category": "食品", "trend": "up"},
        {"keyword": "牛肉干", "category": "食品", "trend": "stable"},
        {"keyword": "奶酪棒", "category": "食品", "trend": "up"},
        # 💄 美妆个护 (15)
        {"keyword": "素颜霜", "category": "美妆", "trend": "up"},
        {"keyword": "护发精油", "category": "个护", "trend": "up"},
        {"keyword": "补水面膜", "category": "美妆", "trend": "stable"},
        {"keyword": "磨砂膏", "category": "个护", "trend": "up"},
        {"keyword": "防晒霜", "category": "美妆", "trend": "up"},
        {"keyword": "眼线笔", "category": "美妆", "trend": "stable"},
        {"keyword": "气垫粉底", "category": "美妆", "trend": "up"},
        {"keyword": "卸妆油", "category": "美妆", "trend": "stable"},
        {"keyword": "身体乳", "category": "个护", "trend": "stable"},
        {"keyword": "洗发水", "category": "个护", "trend": "stable"},
        {"keyword": "脱毛仪", "category": "个护", "trend": "up"},
        {"keyword": "美容仪", "category": "个护", "trend": "up"},
        {"keyword": "美瞳", "category": "美妆", "trend": "stable"},
        {"keyword": "睫毛膏", "category": "美妆", "trend": "stable"},
        {"keyword": "口红", "category": "美妆", "trend": "stable"},
        # 📱 数码 (10)
        {"keyword": "蓝牙耳机", "category": "数码", "trend": "stable"},
        {"keyword": "手机壳", "category": "数码", "trend": "stable"},
        {"keyword": "充电宝", "category": "数码", "trend": "stable"},
        {"keyword": "数据线", "category": "数码", "trend": "up"},
        {"keyword": "平板支架", "category": "数码", "trend": "up"},
        {"keyword": "无线鼠标", "category": "数码", "trend": "stable"},
        {"keyword": "键盘", "category": "数码", "trend": "up"},
        {"keyword": "屏幕挂灯", "category": "数码", "trend": "up"},
        {"keyword": "手机支架", "category": "数码", "trend": "stable"},
        {"keyword": "充电头", "category": "数码", "trend": "up"},
        # 🐱 宠物 (8)
        {"keyword": "宠物零食", "category": "宠物", "trend": "up"},
        {"keyword": "猫抓板", "category": "宠物", "trend": "stable"},
        {"keyword": "猫砂", "category": "宠物", "trend": "stable"},
        {"keyword": "狗狗玩具", "category": "宠物", "trend": "up"},
        {"keyword": "宠物背包", "category": "宠物", "trend": "up"},
        {"keyword": "宠物衣服", "category": "宠物", "trend": "up"},
        {"keyword": "自动喂食器", "category": "宠物", "trend": "up"},
        {"keyword": "宠物饮水机", "category": "宠物", "trend": "up"},
        # 🏃 运动健身 (8)
        {"keyword": "运动水壶", "category": "运动", "trend": "up"},
        {"keyword": "瑜伽垫", "category": "运动", "trend": "stable"},
        {"keyword": "跳绳", "category": "运动", "trend": "up"},
        {"keyword": "弹力带", "category": "运动", "trend": "up"},
        {"keyword": "运动手套", "category": "运动", "trend": "up"},
        {"keyword": "速干毛巾", "category": "运动", "trend": "up"},
        {"keyword": "筋膜枪", "category": "运动", "trend": "up"},
        {"keyword": "护膝", "category": "运动", "trend": "stable"},
        # 🧸 潮玩/文创 (8)
        {"keyword": "盲盒", "category": "潮玩", "trend": "up"},
        {"keyword": "手账本", "category": "文创", "trend": "up"},
        {"keyword": "贴纸", "category": "文创", "trend": "stable"},
        {"keyword": "印章", "category": "文创", "trend": "up"},
        {"keyword": "水彩笔", "category": "文创", "trend": "stable"},
        {"keyword": "解压玩具", "category": "潮玩", "trend": "up"},
        {"keyword": "拼图", "category": "潮玩", "trend": "up"},
        {"keyword": "手工材料包", "category": "文创", "trend": "up"},
        # 🚗 汽车/出行 (6)
        {"keyword": "车载香薰", "category": "汽车", "trend": "up"},
        {"keyword": "车载手机架", "category": "汽车", "trend": "stable"},
        {"keyword": "临时停车牌", "category": "汽车", "trend": "stable"},
        {"keyword": "遮阳挡", "category": "汽车", "trend": "seasonal"},
        {"keyword": "安全锤", "category": "汽车", "trend": "stable"},
        {"keyword": "汽车脚垫", "category": "汽车", "trend": "stable"},
    ]
    return hot_kw


# ============================================================
# 选品分析管道
# ============================================================
def run_insight_analysis(query: str) -> str:
    """运行选品分析 + 达人推荐，返回两段报告"""
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.agents.creator_agent import CreatorGenerator
    from src.config import RERANKER_THRESHOLD

    MIN_NOTES = 10
    hr = _state.hybrid_retriever
    reranker = _state.reranker
    raw_dir = _state.raw_dir

    # 检索
    docs = hr.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES) or []
    if not docs:
        return "选品报告：暂无相关数据。", "达人推荐：暂无相关数据。"

    scores = reranker.rerank(query, docs)
    relevant = [d for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]
    if len(relevant) < 3:
        return "选品报告：相关数据不足（少于3篇）。", "达人推荐：相关数据不足。"

    # 分析
    analyzer = CommentAnalyzer(raw_dir=raw_dir)
    analyses = analyzer.analyze(relevant)
    if not analyses:
        return "选品报告：无法分析评论数据。", "达人推荐：无法分析。"

    aggregator = DemandAggregator()
    aggregated = aggregator.aggregate(analyses)

    # 生成两套报告
    try:
        selection = InsightGenerator()
        sel_report = selection.generate_fallback(aggregated, category=query)
    except Exception as e:
        sel_report = f"选品报告生成失败：{e}"

    try:
        creator = CreatorGenerator()
        creator_report = creator.generate_fallback(aggregated, category=query)
    except Exception as e:
        creator_report = f"达人推荐生成失败：{e}"

    return sel_report, creator_report


# ============================================================
# 导入笔记（粘贴链接）
# ============================================================
def import_note_by_url(note_url: str, category: str) -> dict:
    """通过粘贴的小红书笔记链接导入单篇"""
    note_id = ""
    if "/explore/" in note_url:
        note_id = note_url.split("/explore/")[-1].split("?")[0].split("/")[0]
    elif "/a/" in note_url:
        note_id = note_url.split("/a/")[-1].split("?")[0].split("/")[0]

    if not note_id or len(note_id) < 20:
        return {"success": False, "error": f"无法从链接中提取笔记ID: {note_url}"}

    try:
        from src.real_crawler import XHSCrawler
        crawler = XHSCrawler()
        if not crawler.is_logged_in:
            crawler.close()
            return {"success": False, "error": "未登录，请先扫码登录后再导入"}
    except Exception as e:
        return {"success": False, "error": f"爬虫初始化失败: {e}"}

    note = {"id": note_id, "title": f"{category}_{note_id[:8]}", "url": f"https://www.xiaohongshu.com/explore/{note_id}"}
    try:
        note = crawler.get_note_detail(note)
        comments = crawler.get_comments(note, max_comments=30)
        path = crawler.save_note(note, category, comments)
        crawler.close()
        rebuild_indexes()
        return {"success": True, "path": path, "content_len": len(note.get("content", "")), "comments": len(comments or [])}
    except Exception as e:
        try:
            crawler.close()
        except Exception:
            pass
        return {"success": False, "error": str(e)}


# ============================================================
# 智能问答
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
# UI
# ============================================================
st.title("🎯 小红书爆款雷达")
st.caption("选品洞察 · 达人选题 · AI 问答")

# ===== 侧边栏导航 =====
with st.sidebar:
    st.markdown("## 🎯 选品雷达")
    st.caption("小红书选品 · 机会评分 · 执行清单")

    tabs = ["💡 灵感库", "🎯 发现机会", "💬 智能问答", "📥 导入数据"]
    selected_tab = st.radio("导航", tabs, index=1, label_visibility="collapsed")

    st.markdown("---")
    st.caption(f"📊 {_state.stats['total_chunks']} chunk · {_state.stats['total_notes']} 笔记")

# ============================================================
# 💡 灵感库
# ============================================================
if selected_tab == "💡 灵感库":
    st.subheader("💡 灵感库")
    st.caption("不知道搜什么？按品类浏览精选方向，点一下就出双报告。")

    keywords = get_trending_keywords()
    categories = sorted(set(k["category"] for k in keywords))
    cat_filter = st.selectbox("品类筛选", ["全部"] + categories)

    filtered = keywords if cat_filter == "全部" else [k for k in keywords if k["category"] == cat_filter]

    cols = st.columns(4)
    for i, kw in enumerate(filtered):
        trend_icon = "🔥" if kw["trend"] == "up" else ""
        with cols[i % 4]:
            if st.button(f"{trend_icon} {kw['keyword']}\n_{kw['category']}_", key=f"hot_{i}", use_container_width=True):
                st.session_state.inspire_keyword = kw["keyword"]
                st.session_state.analyze_now = True
                st.rerun()

# ============================================================
# 🎯 发现机会（双报告：选品 + 达人）
# ============================================================
elif selected_tab == "🎯 发现机会":
    st.subheader("🎯 发现机会")
    st.caption("输入品类名，一键生成选品洞察 + 达人选题方案。")

    # 快捷标签
    quick_kws = ["健身服", "磁吸感应灯", "辣条", "瑜伽裤", "蓝牙耳机", "养生茶"]
    st.markdown("**热门：** " + " · ".join(
        f"`{kw}`" for kw in quick_kws
    ))

    # Input
    default_kw = st.session_state.get("inspire_keyword", "")
    query = st.text_input("品类名称", value=default_kw, placeholder="例如：辣条、磁吸感应灯", key="discover_input")

    analyze = st.button("🔍 一键分析", type="primary", disabled=not query, key="discover_btn")

    if (analyze or st.session_state.get("analyze_now")) and query:
        st.session_state.analyze_now = False
        st.session_state.inspire_keyword = ""

        with st.spinner(f"正在分析「{query}」..."):
            sel_report, creator_report = run_insight_analysis(query)

        tab1, tab2 = st.tabs(["📊 选品洞察", "🎬 达人选题"])

        with tab1:
            st.markdown("### 📊 选品洞察报告")
            st.markdown(sel_report)

        with tab2:
            st.markdown("### 🎬 达人选题方案")
            st.markdown("> 基于评论区真实反馈，为你量身定制的内容创作方案。博主直接复制就能拍。")
            st.markdown(creator_report)

# ============================================================
# 💬 智能问答
# ============================================================
elif selected_tab == "💬 智能问答":
    st.subheader("💬 智能问答")
    st.caption("基于小红书真实评论数据回答选品问题。")

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
            if not ans:
                ans = f"知识库暂无「{q}」相关数据。\n\n请先在「📥 导入数据」中粘贴小红书笔记链接，或在「🎯 发现机会」中尝试已有品类。"
            st.markdown(ans)
        st.session_state.qa_msgs.append({"role": "assistant", "content": ans})

# ============================================================
# 📥 导入数据（替代自动抓取）
# ============================================================
elif selected_tab == "📥 导入数据":
    st.subheader("📥 导入笔记")
    st.caption("自动抓取容易被小红书拦截。改用粘贴链接导入，更稳定更安全。")

    st.info(
        "自动抓取功能因小红书强反爬已移除。\n\n"
        "**推荐方式：** 在小红书 App 中复制笔记链接，粘贴到下方导入。每次可以粘贴多条链接。"
    )

    imported = False
    links_text = st.text_area(
        "粘贴小红书笔记链接（每行一条，建议3-5条）",
        placeholder="https://www.xiaohongshu.com/explore/xxxxxxxxxxxxxx\nhttps://www.xiaohongshu.com/explore/yyyyyyyyyyyyyy\nhttps://www.xiaohongshu.com/explore/zzzzzzzzzzzzzz",
        height=140,
    )

    category = st.text_input("笔记所属品类", placeholder="例如：健身服、蓝牙耳机")

    if st.button("📥 导入", type="primary", disabled=not links_text or not category):
        links = [l.strip() for l in links_text.strip().split("\n") if l.strip()]
        log_placeholder = st.empty()

        success_count = 0
        fail_count = 0

        for i, link in enumerate(links):
            log_placeholder.info(f"正在导入 ({i+1}/{len(links)})： {link[:60]}...")
            result = import_note_by_url(link, category)
            if result["success"]:
                success_count += 1
                st.success(f"✅ 导入成功：{link[:50]}... ({result.get('comments', 0)} 条评论)")
            else:
                fail_count += 1
                st.warning(f"❌ 导入失败：{link[:50]}... — {result.get('error', '未知错误')}")

        if success_count > 0:
            log_placeholder.success(f"完成！成功 {success_count} 篇，失败 {fail_count} 篇")
        else:
            log_placeholder.error(f"全部失败（{fail_count} 篇）。请确保已登录后重试。")

# ============================================================
# 底部
# ============================================================
st.markdown("---")
st.caption(f"🎯 小红书爆款雷达 v3.0 · 选品+选题双引擎 · {_state.stats['total_notes']} 篇笔记")
