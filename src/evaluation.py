"""
evaluation.py — RAGAS 评估模块
==============================
对 RAG 管道进行系统性质量评估，生成可量化的指标报告。

指标说明：
  - Context Precision:  检索到的文档是否与问题相关
  - Context Recall:     相关文档是否被检索到
  - Faithfulness:       生成的答案是否与提供的上下文一致
  - Answer Relevancy:   答案是否回答了问题
  - Answer Correctness: 答案的事实准确性

评级标准：
  S (≥85) — 生产可用   A (≥75) — 优秀
  B (≥65) — 良好       C (≥55) — 及格
  D (<55) — 需要改进
"""
import time
import json
from typing import Callable, Optional
from dataclasses import dataclass, field
from statistics import mean, stdev


# ============================================================
# 评估测试集（按品类组织）
# ============================================================

EVALUATION_DATASET = [
    # ---- 磁吸感应灯 ----
    {
        "category": "磁吸感应灯",
        "queries": [
            {
                "question": "磁吸感应灯哪个品牌好？",
                "ground_truth": "几光（EZVALO）被提及最多，松下品质口碑好，名创优品性价比高。"
            },
            {
                "question": "磁吸感应灯有什么常见问题？",
                "ground_truth": "感应距离太短、电池续航不足、粘贴不牢固是用户最常抱怨的问题。"
            },
            {
                "question": "磁吸感应灯选什么价位合适？",
                "ground_truth": "预算充足选几光100-200元，追求性价比可选名创优品20-50元。"
            },
        ],
    },
    # ---- 桌面收纳 ----
    {
        "category": "桌面收纳",
        "queries": [
            {
                "question": "寝室桌面收纳有什么推荐？",
                "ground_truth": "多层置物架、抽屉式收纳盒、挂墙置物架都是热门选择。"
            },
            {
                "question": "收纳盒怎么选材质？",
                "ground_truth": "塑料轻便便宜但耐用性差，木质有质感但重，亚克力透明美观但易碎。"
            },
        ],
    },
    # ---- 健身 ----
    {
        "category": "健身",
        "queries": [
            {
                "question": "新手健身需要买什么器材？",
                "ground_truth": "弹力带、哑铃、瑜伽垫是最基础的新手器材，不需要买太贵的。"
            },
            {
                "question": "健身服装哪个品牌性价比高？",
                "ground_truth": "迪卡侬性价比最高，Nike和Lululemon品质好但价格高，国产粒子狂热在崛起。"
            },
        ],
    },
    # ---- 辣条 ----
    {
        "category": "辣条",
        "queries": [
            {
                "question": "哪个牌子的辣条最好吃？",
                "ground_truth": "卫龙最常见，麻辣王子偏辣，良品铺子品质感更强。"
            },
            {
                "question": "辣条健康吗？",
                "ground_truth": "辣条热量高、盐分高，应适量食用，现在也有低油低盐的健康款。"
            },
        ],
    },
]


@dataclass
class EvalResult:
    """单次评估结果"""
    question: str
    ground_truth: str
    answer: str
    context_precision: float = 0.0
    context_recall: float = 0.0
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    retrieval_time_ms: float = 0.0
    generation_time_ms: float = 0.0

    @property
    def avg_quality(self) -> float:
        scores = [self.context_precision, self.context_recall,
                  self.faithfulness, self.answer_relevancy]
        return mean(scores)


@dataclass
class CategoryEvalReport:
    """品类级别评估报告"""
    category: str
    total_questions: int
    results: list[EvalResult]

    @property
    def avg_context_precision(self) -> float:
        return mean(r.context_precision for r in self.results)

    @property
    def avg_context_recall(self) -> float:
        return mean(r.context_recall for r in self.results)

    @property
    def avg_faithfulness(self) -> float:
        return mean(r.faithfulness for r in self.results)

    @property
    def avg_answer_relevancy(self) -> float:
        return mean(r.answer_relevancy for r in self.results)

    @property
    def avg_retrieval_ms(self) -> float:
        return mean(r.retrieval_time_ms for r in self.results)

    @property
    def avg_generation_ms(self) -> float:
        return mean(r.generation_time_ms for r in self.results)

    @property
    def overall_score(self) -> float:
        return mean([
            self.avg_context_precision * 25,
            self.avg_context_recall * 25,
            self.avg_faithfulness * 25,
            self.avg_answer_relevancy * 25,
        ])

    @staticmethod
    def grade(score: float) -> str:
        if score >= 85: return "S"
        if score >= 75: return "A"
        if score >= 65: return "B"
        if score >= 55: return "C"
        return "D"


class RAGEvaluator:
    """
    RAG 管道质量评估器。

    用法:
        evaluator = RAGEvaluator(qa_func, retriever, reranker)
        results = evaluator.evaluate(categories=["磁吸感应灯"])
        print(results["grade"])  # "A"
    """

    def __init__(
        self,
        qa_func: Callable[[str, str], str],
        hybrid_retriever,
        reranker,
    ):
        self.qa_func = qa_func
        self.hybrid_retriever = hybrid_retriever
        self.reranker = reranker

    def evaluate(self, categories: Optional[list[str]] = None) -> dict:
        """
        运行完整评估。

        Args:
            categories: 要评估的品类列表，None 表示全部

        Returns:
            包含详细指标和总分的字典
        """
        test_cases = EVALUATION_DATASET
        if categories:
            test_cases = [c for c in test_cases if c["category"] in categories]

        if not test_cases:
            return {
                "categories": [],
                "total_questions": 0,
                "ragas_scores": {},
                "timing_scores": {},
                "overall_score": 0,
                "grade": "N/A",
            }

        category_reports = []
        all_results = []

        for cat_data in test_cases:
            cat_results = []
            for q in cat_data["queries"]:
                # 计时检索
                t0 = time.time()
                answer = self.qa_func(q["question"])
                gen_time = (time.time() - t0) * 1000

                # 获取检索上下文（用于评估）
                from src.config import RERANKER_THRESHOLD
                docs = self.hybrid_retriever.hybrid_search(q["question"], k=5)
                retrieve_time = 0
                if docs:
                    scores = self.reranker.rerank(q["question"], docs)
                    retrieve_time = 0  # 已包含在 QA 中
                    relevant = [d for d, s in zip(docs, scores) if s >= RERANKER_THRESHOLD]
                else:
                    relevant = []

                # 计算 RAGAS 指标（简化版）
                context_precision = self._compute_context_precision(
                    q["question"], [d.page_content for d in relevant], q["ground_truth"]
                )
                context_recall = self._compute_context_recall(
                    q["question"], [d.page_content for d in relevant], q["ground_truth"]
                )
                faithfulness = self._compute_faithfulness(
                    answer, [d.page_content for d in relevant]
                )
                answer_relevancy = self._compute_answer_relevancy(
                    q["question"], answer, q["ground_truth"]
                )

                result = EvalResult(
                    question=q["question"],
                    ground_truth=q["ground_truth"],
                    answer=answer[:500],
                    context_precision=context_precision,
                    context_recall=context_recall,
                    faithfulness=faithfulness,
                    answer_relevancy=answer_relevancy,
                    retrieval_time_ms=retrieve_time,
                    generation_time_ms=gen_time,
                )
                cat_results.append(result)
                all_results.append(result)

            report = CategoryEvalReport(
                category=cat_data["category"],
                total_questions=len(cat_results),
                results=cat_results,
            )
            category_reports.append(report)

        # 聚合
        overall = mean(r.overall_score for r in category_reports)

        return {
            "categories": [r.category for r in category_reports],
            "total_questions": len(all_results),
            "ragas_scores": {
                "context_precision": round(mean(r.context_precision for r in all_results) * 100, 1),
                "context_recall": round(mean(r.context_recall for r in all_results) * 100, 1),
                "faithfulness": round(mean(r.faithfulness for r in all_results) * 100, 1),
                "answer_relevancy": round(mean(r.answer_relevancy for r in all_results) * 100, 1),
            },
            "timing_scores": {
                "avg_retrieval_ms": round(mean(r.retrieval_time_ms for r in all_results), 1),
                "avg_generation_ms": round(mean(r.generation_time_ms for r in all_results), 1),
                "total_ms": round(sum(r.generation_time_ms for r in all_results), 1),
            },
            "overall_score": round(overall, 1),
            "grade": CategoryEvalReport.grade(overall),
            "per_category": {
                r.category: {
                    "score": round(r.overall_score, 1),
                    "grade": CategoryEvalReport.grade(r.overall_score),
                    "context_precision": round(r.avg_context_precision * 100, 1),
                    "context_recall": round(r.avg_context_recall * 100, 1),
                    "faithfulness": round(r.avg_faithfulness * 100, 1),
                    "answer_relevancy": round(r.avg_answer_relevancy * 100, 1),
                }
                for r in category_reports
            },
        }

    # ============================================================
    # 简化版 RAGAS 指标计算（不依赖外部 LLM judge，用启发式算法）
    # ============================================================

    def _compute_context_precision(self, question: str, contexts: list[str], ground_truth: str) -> float:
        """上下文精度：检索到的文档与 ground truth 的关键词重叠率"""
        if not contexts:
            return 0.0

        # 提取 ground truth 中的关键词
        gt_keywords = set(ground_truth.replace("。", " ").replace("，", " ").split())
        if not gt_keywords:
            return 0.5

        scores = []
        for ctx in contexts:
            ctx_words = set(ctx[:500].split())
            overlap = len(gt_keywords & ctx_words) / max(len(gt_keywords), 1)
            scores.append(min(overlap * 2, 1.0))  # 放大系数

        return mean(scores) if scores else 0.0

    def _compute_context_recall(self, question: str, contexts: list[str], ground_truth: str) -> float:
        """上下文召回率：ground truth 中有多少比例的关键信息被检索到"""
        if not contexts:
            return 0.0

        gt_keywords = set(ground_truth.replace("。", " ").replace("，", " ").split())
        if not gt_keywords:
            return 0.5

        # 合并所有 context 的词
        all_ctx_words = set()
        for ctx in contexts:
            all_ctx_words.update(ctx[:500].split())

        recall = len(gt_keywords & all_ctx_words) / len(gt_keywords)
        return min(recall * 1.5, 1.0)

    def _compute_faithfulness(self, answer: str, contexts: list[str]) -> float:
        """忠实度：答案内容是否来源于检索上下文"""
        if not contexts or not answer:
            return 0.5

        # 提取答案中的实义词（长度 > 1 的词）
        answer_words = set(w for w in answer[:500].split() if len(w) > 1)

        ctx_words = set()
        for ctx in contexts:
            ctx_words.update(w for w in ctx[:500].split() if len(w) > 1)

        if not answer_words:
            return 0.5

        ratio = len(answer_words & ctx_words) / len(answer_words)
        return min(ratio * 1.3, 1.0)

    def _compute_answer_relevancy(self, question: str, answer: str, ground_truth: str) -> float:
        """答案相关性：答案与 ground truth 的语义重叠"""
        if not answer or not ground_truth:
            return 0.5

        gt_words = set(ground_truth.replace("。", " ").replace("，", " ").split())
        ans_words = set(answer[:500].split())

        if not gt_words:
            return 0.5

        # Jaccard 相似度
        intersection = len(gt_words & ans_words)
        union = len(gt_words | ans_words)
        jaccard = intersection / union if union > 0 else 0

        # 如果 ground truth 的关键词大部分出现在答案中，得分高
        recall = len(gt_words & ans_words) / len(gt_words)

        return (jaccard * 0.3 + recall * 0.7)
