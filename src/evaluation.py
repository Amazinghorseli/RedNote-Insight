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

