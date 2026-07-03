"""
run_eval.py — RAG 检索质量评估脚本
=====================================
评估混合检索管道的 Recall@K / MRR / NDCG@K。

用法:
    uv run python eval/run_eval.py          # 跑全部 20 条查询
    uv run python eval/run_eval.py --k 5    # 自定义 K 值
    uv run python eval/run_eval.py --json   # 输出 JSON 格式（供 CI 使用）

输出:
    - 控制台: 彩色表格 + 失败案例
    - 文件: eval/results.json (详细结果)
    - 文件: eval/report.md (可读报告)
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# 将项目根目录加入 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.state import AppState


# ============================================================
#  加载评估集
# ============================================================

def load_queries(path: str = None) -> dict:
    if path is None:
        path = Path(__file__).parent / "queries.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ============================================================
#  相关性判定
# ============================================================

def is_relevant(doc_content: str, keywords: list[str]) -> bool:
    """判断一篇文档是否与查询相关（基于关键词命中）。"""
    content_lower = doc_content.lower()
    return any(kw.lower() in content_lower for kw in keywords)


# ============================================================
#  评估指标
# ============================================================

def recall_at_k(retrieved: list[str], relevant_keywords: list[str], k: int) -> float:
    """Recall@K：Top-K 中命中相关文档的比例。

    由于我们不知道知识库中总共多少相关文档，用 min_relevant_docs 作为分母估计。
    实际计算时：hit_count / len(retrieved[:k])。
    真正的 Recall 需要知道全部相关文档数，这里用命中关键词数近似。
    """
    hits = sum(1 for doc in retrieved[:k] if is_relevant(doc, relevant_keywords))
    return hits / max(len(retrieved[:k]), 1)


def precision_at_k(retrieved: list[str], relevant_keywords: list[str], k: int) -> float:
    """Precision@K：Top-K 中相关文档的占比。"""
    if k <= 0 or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for doc in top_k if is_relevant(doc, relevant_keywords))
    return hits / len(top_k)


def mrr(retrieved: list[str], relevant_keywords: list[str]) -> float:
    """MRR (Mean Reciprocal Rank)：第一个相关文档的排名的倒数。"""
    for rank, doc in enumerate(retrieved, start=1):
        if is_relevant(doc, relevant_keywords):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant_keywords: list[str], k: int) -> float:
    """NDCG@K：归一化折损累计增益。

    用关键词命中数作为相关性分数（0/1 或连续值）。
    """
    if k <= 0 or not retrieved:
        return 0.0
    top_k = retrieved[:k]

    # DCG
    dcg = 0.0
    for i, doc in enumerate(top_k, start=1):
        # 相关性分数：命中多少关键词
        hits = sum(1 for kw in relevant_keywords if kw.lower() in doc.lower())
        rel = min(hits / max(len(relevant_keywords), 1), 1.0)
        dcg += rel / math.log2(i + 1)

    # IDCG（理想排序：假设最相关的文档排最前面）
    # 简化：假设 k 个文档全部部分相关（rel=1）
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, k + 1))

    return dcg / idcg if idcg > 0 else 0.0


def hit_rate_at_k(retrieved: list[str], relevant_keywords: list[str], k: int) -> bool:
    """Hit Rate@K：Top-K 中是否至少有一篇相关文档。"""
    return any(is_relevant(doc, relevant_keywords) for doc in retrieved[:k])


# ============================================================
#  评估主流程
# ============================================================

async def run_evaluation(
    state: AppState,
    queries: list[dict],
    k_values: list[int] = None,
) -> dict[str, Any]:
    """运行完整评估，返回所有指标。"""
    if k_values is None:
        k_values = [1, 3, 5, 10]

    results = []
    per_category = defaultdict(lambda: defaultdict(list))
    per_difficulty = defaultdict(lambda: defaultdict(list))

    total_start = time.time()

    for i, q in enumerate(queries):
        t0 = time.time()
        query_text = q["query"]
        relevant_kw = q["relevant_keywords"]

        print(f"  [{i+1:2d}/{len(queries)}] {query_text} ... ", end="", flush=True)

        try:
            # 使用混合检索
            docs = await state.hybrid_retriever.ahybrid_search(
                query_text, k=10, bm25_k=25, final_k=10
            )
            doc_contents = [d.page_content for d in docs]
            elapsed = round(time.time() - t0, 3)
        except Exception as e:
            print(f"❌ 错误: {e}")
            results.append({
                "id": q["id"],
                "query": query_text,
                "error": str(e),
                "retrieved_count": 0,
                "elapsed_seconds": round(time.time() - t0, 3),
            })
            continue

        # 计算各项指标
        query_result = {
            "id": q["id"],
            "query": query_text,
            "category": q["category"],
            "type": q["type"],
            "difficulty": q["difficulty"],
            "retrieved_count": len(docs),
            "elapsed_seconds": elapsed,
        }

        for k in k_values:
            query_result[f"recall@{k}"] = round(recall_at_k(doc_contents, relevant_kw, k), 4)
            query_result[f"precision@{k}"] = round(precision_at_k(doc_contents, relevant_kw, k), 4)
            query_result[f"ndcg@{k}"] = round(ndcg_at_k(doc_contents, relevant_kw, k), 4)
            query_result[f"hit@{k}"] = hit_rate_at_k(doc_contents, relevant_kw, k)

        query_result["mrr"] = round(mrr(doc_contents, relevant_kw), 4)
        results.append(query_result)

        # 按维度的统计
        cat = q["category"]
        diff = q["difficulty"]
        for k in k_values:
            per_category[cat][f"recall@{k}"].append(query_result[f"recall@{k}"])
            per_category[cat][f"hit@{k}"].append(1 if query_result[f"hit@{k}"] else 0)
            per_difficulty[diff][f"recall@{k}"].append(query_result[f"recall@{k}"])
            per_difficulty[diff][f"hit@{k}"].append(1 if query_result[f"hit@{k}"] else 0)

        # 快速反馈
        hit5 = query_result.get("hit@5", False)
        recall5 = query_result.get("recall@5", 0)
        icon = "PASS" if hit5 and recall5 >= 0.5 else ("WARN" if hit5 else "FAIL")
        print(f"{icon} Recall@5={recall5:.2f}  Hit@5={'Yes' if hit5 else 'No '}  ({elapsed}s)")

    total_elapsed = round(time.time() - total_start, 2)

    # ===== 汇总 =====
    summary = {
        "total_queries": len(queries),
        "successful": len([r for r in results if "error" not in r]),
        "failed": len([r for r in results if "error" in r]),
        "total_elapsed_seconds": total_elapsed,
        "avg_elapsed_seconds": round(
            sum(r.get("elapsed_seconds", 0) for r in results) / max(len(results), 1), 3
        ),
    }

    for k in k_values:
        valid = [r for r in results if f"recall@{k}" in r]
        summary[f"avg_recall@{k}"] = (
            round(sum(r[f"recall@{k}"] for r in valid) / len(valid), 4) if valid else 0
        )
        summary[f"avg_precision@{k}"] = (
            round(sum(r[f"precision@{k}"] for r in valid) / len(valid), 4) if valid else 0
        )
        summary[f"avg_ndcg@{k}"] = (
            round(sum(r[f"ndcg@{k}"] for r in valid) / len(valid), 4) if valid else 0
        )
        summary[f"hit_rate@{k}"] = (
            round(sum(1 for r in valid if r.get(f"hit@{k}", False)) / len(valid), 4) if valid else 0
        )

    valid_mrr = [r for r in results if "mrr" in r]
    summary["avg_mrr"] = round(sum(r["mrr"] for r in valid_mrr) / len(valid_mrr), 4) if valid_mrr else 0

    # 按品类汇总
    cat_summary = {}
    for cat, metrics in per_category.items():
        cat_summary[cat] = {
            "count": len(metrics.get("recall@5", [])),
            "avg_recall@5": round(sum(metrics.get("recall@5", [])) / max(len(metrics.get("recall@5", [])), 1), 4),
            "hit_rate@5": round(sum(metrics.get("hit@5", [])) / max(len(metrics.get("hit@5", [])), 1), 4),
        }

    # 按难度汇总
    diff_summary = {}
    for diff, metrics in per_difficulty.items():
        diff_summary[diff] = {
            "count": len(metrics.get("recall@5", [])),
            "avg_recall@5": round(sum(metrics.get("recall@5", [])) / max(len(metrics.get("recall@5", [])), 1), 4),
            "hit_rate@5": round(sum(metrics.get("hit@5", [])) / max(len(metrics.get("hit@5", [])), 1), 4),
        }

    # 失败案例
    failures = [
        r for r in results
        if "error" in r or (r.get("hit@5") is False)
    ]

    return {
        "summary": summary,
        "by_category": cat_summary,
        "by_difficulty": diff_summary,
        "failures": failures,
        "results": results,
    }


# ============================================================
#  报告生成
# ============================================================

def print_report(eval_result: dict, k_values: list[int]):
    """打印彩色控制台报告。"""
    s = eval_result["summary"]

    print("\n" + "=" * 64)
    print("  [RAG 检索质量评估报告]")
    print("=" * 64)

    print(f"\n  查询数: {s['total_queries']}  |  成功: {s['successful']}  |  失败: {s['failed']}")
    print(f"  总耗时: {s['total_elapsed_seconds']}s  |  平均: {s['avg_elapsed_seconds']}s/条")
    print(f"  MRR: {s['avg_mrr']:.4f}")

    print(f"\n  {'K':>4}  {'Recall':>8}  {'Precision':>11}  {'NDCG':>8}  {'Hit Rate':>10}")
    print(f"  {'-'*4}  {'-'*8}  {'-'*11}  {'-'*8}  {'-'*10}")
    for k in k_values:
        print(f"  {k:>4}  {s[f'avg_recall@{k}']:>8.4f}  {s[f'avg_precision@{k}']:>11.4f}  {s[f'avg_ndcg@{k}']:>8.4f}  {s[f'hit_rate@{k}']:>10.2%}")

    # 按难度
    if eval_result.get("by_difficulty"):
        print(f"\n  ── 按难度 ──")
        print(f"  {'难度':>10}  {'数量':>4}  {'Recall@5':>10}  {'Hit@5':>8}")
        for diff, m in eval_result["by_difficulty"].items():
            print(f"  {diff:>10}  {m['count']:>4}  {m['avg_recall@5']:>10.4f}  {m['hit_rate@5']:>8.2%}")

    # 按品类
    if eval_result.get("by_category"):
        print(f"\n  ── 按品类 ──")
        for cat, m in sorted(eval_result["by_category"].items()):
            print(f"  {cat:>6}  {m['count']:>2}条  Recall@5={m['avg_recall@5']:.4f}  Hit@5={m['hit_rate@5']:.2%}")

    # 失败案例
    failures = eval_result.get("failures", [])
    if failures:
        print(f"\n  [!]  失败 / 低质量案例 ({len(failures)} 条):")
        for f in failures:
            err = f.get("error", "")
            hit5 = f.get("hit@5", "N/A")
            print(f"    [{f['id']}] {f['query'][:30]:30s}  Hit@5={hit5}  {err}")

    print("\n" + "=" * 64)


def save_results(eval_result: dict, output_dir: Path, k_values: list[int]):
    """保存详细结果 JSON + Markdown 报告。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON 详细结果
    json_path = output_dir / "results.json"
    json_path.write_text(
        json.dumps(eval_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Markdown 可读报告
    s = eval_result["summary"]
    md_lines = [
        "# RAG 检索质量评估报告",
        "",
        f"**日期**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**查询数**: {s['total_queries']} | **成功**: {s['successful']} | **失败**: {s['failed']}",
        f"**总耗时**: {s['total_elapsed_seconds']}s | **平均**: {s['avg_elapsed_seconds']}s/条",
        f"**MRR**: {s['avg_mrr']:.4f}",
        "",
        "## 核心指标",
        "",
        "| K | Recall | Precision | NDCG | Hit Rate |",
        "|---|--------|-----------|------|----------|",
    ]
    for k in k_values:
        md_lines.append(
            f"| @{k} | {s[f'avg_recall@{k}']:.4f} | {s[f'avg_precision@{k}']:.4f} | "
            f"{s[f'avg_ndcg@{k}']:.4f} | {s[f'hit_rate@{k}']:.2%} |"
        )

    # 按难度
    if eval_result.get("by_difficulty"):
        md_lines += ["", "## 按难度", "", "| 难度 | 数量 | Recall@5 | Hit@5 |", "|------|------|----------|-------|"]
        for diff, m in eval_result["by_difficulty"].items():
            md_lines.append(f"| {diff} | {m['count']} | {m['avg_recall@5']:.4f} | {m['hit_rate@5']:.2%} |")

    # 按品类
    if eval_result.get("by_category"):
        md_lines += ["", "## 按品类", "", "| 品类 | 数量 | Recall@5 | Hit@5 |", "|------|------|----------|-------|"]
        for cat, m in sorted(eval_result["by_category"].items()):
            md_lines.append(f"| {cat} | {m['count']} | {m['avg_recall@5']:.4f} | {m['hit_rate@5']:.2%} |")

    # 失败案例
    failures = eval_result.get("failures", [])
    if failures:
        md_lines += ["", "## 失败 / 低质量案例", ""]
        for f in failures:
            md_lines.append(f"- [{f['id']}] **{f['query']}** — Hit@5={f.get('hit@5', 'N/A')} {f.get('error', '')}")

    md_lines += ["", "---", f"*报告由 `eval/run_eval.py` 自动生成*"]

    md_path = output_dir / "report.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"\n  [OK] 结果已保存:")
    print(f"       JSON: {json_path}")
    print(f"       MD:   {md_path}")


# ============================================================
#  CLI 入口
# ============================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG 检索质量评估")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 10], help="评估的 K 值")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON 结果")
    parser.add_argument("--no-save", action="store_true", help="不保存结果文件")
    args = parser.parse_args()

    k_values = sorted(set(args.k))

    print(">>> 初始化 AppState...")
    state = AppState()
    await state.initialize()

    if not state.is_ready:
        print(f"❌ AppState 初始化失败: {state.error}")
        sys.exit(1)

    print(f"[OK] AppState 就绪 — {state.stats['total_chunks']} chunks, {len(state.stats['categories'])} 品类")

    eval_data = load_queries()
    queries = eval_data["queries"]
    print(f"\n=== 加载评估集: {eval_data['name']} v{eval_data['version']}")
    print(f"    查询数: {len(queries)} 条")
    print(f"    K 值: {k_values}\n")

    result = await run_evaluation(state, queries, k_values)

    if args.json:
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    else:
        print_report(result, k_values)

    if not args.no_save:
        save_results(result, Path(__file__).parent, k_values)

    # 退出码：有失败返回 1（供 CI 使用）
    if result["summary"]["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
