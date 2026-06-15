"""
api.py — 小红书爆款雷达 FastAPI 后端
=====================================
Phase 1: 完整 API + 前端页面托管
Phase 2: 接入真实爬虫替换假数据

启动: uv run uvicorn api:app --reload --port 8000
"""
import os
import sys
import json
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# 请求/响应模型
# ============================================================

class InsightRequest(BaseModel):
    category: str

class QARequest(BaseModel):
    question: str
    strategy: str = "hybrid"  # auto / vector / keyword / hybrid

class EvaluateRequest(BaseModel):
    categories: list[str] = []  # 为空则评估全部品类

class CrawlRequest(BaseModel):
    category: str
    count: int = 20

class InsightResponse(BaseModel):
    success: bool
    category: str
    report: str
    notes_count: int
    generated_count: int = 0
    elapsed: float

class QAResponse(BaseModel):
    success: bool
    question: str
    answer: str
    elapsed: float

class StatsResponse(BaseModel):
    success: bool
    categories: list[str]
    total_notes: int
    total_chunks: int
    message: str


# ============================================================
# 应用生命周期
# ============================================================

_runtime = None  # 全局运行时状态


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化，关闭时清理"""
    global _runtime
    print("[API] Initializing runtime...")
    _runtime = _init_runtime()
    if _runtime["error"]:
        print(f"[API] WARNING: {_runtime['error']}")
    else:
        print(f"[API] READY - {_runtime['stats']['total_chunks']} chunks")
    yield
    print("[API] Shutting down")


app = FastAPI(
    title="小红书爆款雷达 API",
    description="翻评论、找痛点、定方向 — AI 选品洞察引擎",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# 初始化逻辑（复用原有代码）
# ============================================================

def _init_runtime() -> dict:
    """初始化向量库、检索器、LangGraph"""
    from src.retrievers import HybridRetriever, APIReranker
    from src.graph import build_graph
    from rank_bm25 import BM25Okapi
    import jieba
    from src.ingestion import load_raw_documents, chunk_documents, load_vectorstore, build_vectorstore

    project_root = os.path.dirname(os.path.abspath(__file__))
    raw_dir = os.path.join(project_root, "data", "raw")
    chroma_dir = os.path.join(project_root, "data", "chroma_db")
    chroma_db_file = os.path.join(chroma_dir, "chroma.sqlite3")

    # 检查数据
    raw_files = [f for f in os.listdir(raw_dir) if f.endswith((".txt", ".md"))] if os.path.exists(raw_dir) else []
    if not raw_files:
        return {"error": "暂无数据，请用 generate_data.py 生成数据后刷新"}

    # 加载或构建向量库
    if os.path.exists(chroma_db_file):
        vectorstore = load_vectorstore()
    else:
        docs = load_raw_documents()
        chunks = chunk_documents(docs)
        vectorstore = build_vectorstore(chunks)

    reranker = APIReranker()

    # 加载全部 chunk
    from src.ingestion import rebuild_all_chunks
    chunks = rebuild_all_chunks(raw_dir)

    # BM25 索引
    tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
    bm25 = BM25Okapi(tokenized)

    hybrid_retriever = HybridRetriever(vectorstore, chunks)

    def bm25_search(query: str, k: int = 3):
        tokenized_query = list(jieba.cut(query))
        scores = bm25.get_scores(tokenized_query)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [chunks[i] for i in top_idx]

    graph = build_graph(vectorstore, bm25_search, hybrid_retriever, reranker=reranker)

    # 统计
    categories = list(set(
        d.metadata.get("category", "未分类")
        for d in chunks
    ))

    return {
        "error": None,
        "vectorstore": vectorstore,
        "chunks": chunks,
        "bm25": bm25,
        "hybrid_retriever": hybrid_retriever,
        "bm25_search": bm25_search,
        "graph": graph,
        "reranker": reranker,
        "raw_dir": raw_dir,
        "chroma_dir": chroma_dir,
        "stats": {
            "categories": categories,
            "total_notes": len(raw_files),
            "total_chunks": len(chunks),
        },
    }


def _run_insight(query: str) -> dict:
    """执行洞察管道，返回报告"""
    from src.agents.comment_agent import CommentAnalyzer
    from src.agents.demand_agent import DemandAggregator
    from src.agents.insight_agent import InsightGenerator
    from src.config import RERANKER_THRESHOLD
    from src.fetcher import OnDemandFetcher

    MIN_NOTES = 20
    runtime = _runtime
    hybrid_retriever = runtime["hybrid_retriever"]
    reranker = runtime["reranker"]
    raw_dir = runtime["raw_dir"]

    def _do_insight(docs, category):
        analyzer = CommentAnalyzer(raw_dir=raw_dir)
        analyses = analyzer.analyze(docs)
        if not analyses:
            return "没有找到评论分析数据。"
        aggregator = DemandAggregator()
        aggregated = aggregator.aggregate(analyses)
        generator = InsightGenerator()
        try:
            report = generator.generate(aggregated, category=category)
        except Exception as e:
            report = generator.generate_fallback(aggregated, category=category)
            report += f"\n\n（注：LLM 生成失败，使用模板兜底。错误：{e}）"
        return report

    # 检索
    docs = hybrid_retriever.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
    if not docs:
        return {"report": "检索失败，请刷新页面重试。", "notes_count": 0, "generated_count": 0}

    scores = reranker.rerank(query, docs)
    relevant = [doc for doc, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]

    generated_count = 0
    if len(relevant) >= MIN_NOTES:
        report = _do_insight(relevant, query)
    else:
        # 数据不足 → 自动抓取
        fetch_target = MIN_NOTES - len(relevant) + 5
        fetcher = OnDemandFetcher(raw_dir=raw_dir)
        generated_count = fetcher.fetch(query, count=fetch_target)

        if generated_count == 0:
            return {"report": f"抱歉，无法获取「{query}」的相关数据。", "notes_count": 0, "generated_count": 0}

        # 增量入库
        from src.ingestion import incremental_ingest, rebuild_all_chunks
        from rank_bm25 import BM25Okapi
        import jieba
        incremental_ingest(raw_dir, runtime["vectorstore"])
        chunks = rebuild_all_chunks(raw_dir)
        tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
        bm25_new = BM25Okapi(tokenized)
        hr_new = HybridRetriever(runtime["vectorstore"], chunks)

        def bm25_search_new(query, k=3):
            scores = bm25_new.get_scores(list(jieba.cut(query)))
            return [chunks[i] for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]]

        runtime["chunks"] = chunks
        runtime["bm25"] = bm25_new
        runtime["hybrid_retriever"] = hr_new
        runtime["bm25_search"] = bm25_search_new

        from src.graph import build_graph
        runtime["graph"] = build_graph(runtime["vectorstore"], bm25_search_new, hr_new, reranker=reranker)

        time.sleep(0.5)
        fresh_docs = hr_new.hybrid_search(query, k=MIN_NOTES, bm25_k=40, final_k=MIN_NOTES)
        fresh_scores = reranker.rerank(query, fresh_docs)
        fresh_relevant = [doc for doc, s in zip(fresh_docs, fresh_scores) if s >= RERANKER_THRESHOLD]
        if not fresh_relevant:
            return {"report": f"已生成 {generated_count} 篇笔记，但检索仍未匹配。请更换关键词。", "notes_count": 0, "generated_count": generated_count}

        report = _do_insight(fresh_relevant, query)
        report = f"（📥 已为「{query}」实时生成 {generated_count} 篇新笔记）\n\n{report}"

    return {"report": report, "notes_count": len(relevant) if generated_count == 0 else len(fresh_relevant), "generated_count": generated_count}


def _run_qa(question: str, strategy: str = "hybrid") -> str:
    """执行 QA 管道"""
    runtime = _runtime
    graph = runtime["graph"]

    result = graph.invoke({
        "question": question,
        "rewritten_question": "",
        "strategy": strategy if strategy != "auto" else "",
        "documents": [],
        "relevant_docs": [],
        "generation": "",
        "retry_count": 0,
    })
    response = result["generation"]

    # 没有答案 → 自动抓取
    if "无法回答" in response or "根据现有资料" in response:
        from src.fetcher import OnDemandFetcher
        fetcher = OnDemandFetcher(raw_dir=runtime["raw_dir"])
        count = fetcher.fetch(question, count=15)
        if count > 0:
            # 增量入库 + 重建索引
            from src.ingestion import incremental_ingest, rebuild_all_chunks
            from rank_bm25 import BM25Okapi
            import jieba
            incremental_ingest(runtime["raw_dir"], runtime["vectorstore"])
            chunks = rebuild_all_chunks(runtime["raw_dir"])
            tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
            bm25_new = BM25Okapi(tokenized)
            hr = HybridRetriever(runtime["vectorstore"], chunks)
            def bms(q, k=3):
                scores = bm25_new.get_scores(list(jieba.cut(q)))
                return [chunks[i] for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]]
            runtime["chunks"] = chunks
            runtime["bm25"] = bm25_new
            runtime["hybrid_retriever"] = hr
            runtime["bm25_search"] = bms
            from src.graph import build_graph
            runtime["graph"] = build_graph(runtime["vectorstore"], bms, hr, reranker=runtime["reranker"])
            time.sleep(0.5)
            fresh_graph = runtime["graph"]
            result = fresh_graph.invoke({
                "question": question,
                "rewritten_question": "",
                "strategy": strategy if strategy != "auto" else "",
                "documents": [],
                "relevant_docs": [],
                "generation": "",
                "retry_count": 0,
            })
            response = result["generation"]
            if "无法回答" in response or "根据现有资料" in response:
                response = f"（📥 已生成 {count} 篇笔记，但检索仍未匹配）\n\n{response}"
            else:
                response = f"（📥 已为「{question}」实时生成 {count} 篇笔记）\n\n{response}"

    return response


# ============================================================
# API 路由
# ============================================================

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    if _runtime is None or _runtime.get("error"):
        return StatsResponse(
            success=False,
            categories=[],
            total_notes=0,
            total_chunks=0,
            message=_runtime.get("error", "未初始化") if _runtime else "未初始化",
        )
    stats = _runtime["stats"]
    return StatsResponse(
        success=True,
        categories=stats["categories"],
        total_notes=stats["total_notes"],
        total_chunks=stats["total_chunks"],
        message=f"知识库就绪，共 {len(stats['categories'])} 个品类",
    )


@app.post("/api/insight", response_model=InsightResponse)
async def run_insight(req: InsightRequest):
    if _runtime is None or _runtime.get("error"):
        raise HTTPException(status_code=503, detail=_runtime.get("error", "服务未就绪") if _runtime else "服务未就绪")

    t0 = time.time()
    result = _run_insight(req.category)
    elapsed = round(time.time() - t0, 2)

    return InsightResponse(
        success=True,
        category=req.category,
        report=result["report"],
        notes_count=result["notes_count"],
        generated_count=result["generated_count"],
        elapsed=elapsed,
    )


@app.post("/api/qa", response_model=QAResponse)
async def run_qa(req: QARequest):
    if _runtime is None or _runtime.get("error"):
        raise HTTPException(status_code=503, detail=_runtime.get("error", "服务未就绪") if _runtime else "服务未就绪")

    t0 = time.time()
    answer = _run_qa(req.question, req.strategy)
    elapsed = round(time.time() - t0, 2)

    return QAResponse(
        success=True,
        question=req.question,
        answer=answer,
        elapsed=elapsed,
    )


@app.post("/api/evaluate")
async def run_evaluation(req: EvaluateRequest):
    """运行 RAGAS 评估并返回指标"""
    if _runtime is None or _runtime.get("error"):
        raise HTTPException(status_code=503, detail=_runtime.get("error", "服务未就绪") if _runtime else "服务未就绪")

    from src.evaluation import RAGEvaluator
    evaluator = RAGEvaluator(
        qa_func=_run_qa,
        hybrid_retriever=_runtime["hybrid_retriever"],
        reranker=_runtime["reranker"],
    )

    categories = req.categories or None
    results = evaluator.evaluate(categories=categories)

    return JSONResponse(content={
        "success": True,
        "evaluated_categories": results["categories"],
        "total_questions": results["total_questions"],
        "ragas_scores": results["ragas_scores"],
        "timing_scores": results["timing_scores"],
        "overall_score": results["overall_score"],
        "grade": results["grade"],
    })


@app.post("/api/crawl")
async def trigger_crawl(req: CrawlRequest):
    """触发数据抓取 — 优先使用真实爬虫，不可用时降级为 LLM 生成"""
    from src.crawler import CrawlerInterface
    crawler = CrawlerInterface(raw_dir=_runtime["raw_dir"])

    result = crawler.crawl(req.category, req.count)

    if result["count"] > 0:
        # 增量入库 + 重建索引
        from src.ingestion import incremental_ingest, rebuild_all_chunks
        incremental_ingest(_runtime["raw_dir"], _runtime["vectorstore"])
        chunks = rebuild_all_chunks(_runtime["raw_dir"])
        from rank_bm25 import BM25Okapi
        import jieba
        tokenized = [list(jieba.cut(d.page_content)) for d in chunks]
        _runtime["bm25"] = BM25Okapi(tokenized)
        _runtime["chunks"] = chunks
        _runtime["stats"]["total_chunks"] = len(chunks)
        _runtime["stats"]["total_notes"] = len(os.listdir(_runtime["raw_dir"]))

    return JSONResponse(content={
        "success": result["count"] > 0,
        "method": result["method"],
        "count": result["count"],
        "message": f"抓取完成: {result['count']} 篇" if result["count"] > 0 else "抓取失败",
    })


# ============================================================
# 静态文件托管（前端 SPA）
# ============================================================

static_dir = Path(__file__).parent / "static"


@app.get("/")
async def serve_frontend():
    """托管前端页面"""
    return FileResponse(static_dir / "index.html")


# 挂载静态资源
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    print("RedNote Insight API starting...")
    print("   API:   http://localhost:8000")
    print("   Front: http://localhost:8000")
    print("   Docs:  http://localhost:8000/docs")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
