"""
query_utils.py — 查询清洗与特征检测
=====================================
项目内 graph.py / qa.py / qa_stream.py 共用。
统一去除噪音 token、检测品牌对比意图。
"""
import re

# 噪声：4位以内纯数字 token
_NOISE_RE = re.compile(r'(?<!\d)\b\d{1,4}\b(?!\d)')

# 品牌/对比关键词
_BRAND_KW = re.compile(r'(品牌|对比|哪个好|推荐|测评|排行|哪个|哪款|哪家)')


def clean_query(query: str) -> str:
    """清洗查询：去纯数字噪音 + 压缩空白"""
    cleaned = _NOISE_RE.sub('', query)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    return cleaned if cleaned else query


def is_brand_comparison(query: str) -> bool:
    """判断是否为品牌对比/推荐类查询"""
    return bool(_BRAND_KW.search(query))


def resolve_k(query: str, base: int = 5, brand: int = 8) -> int:
    """品牌对比类查询自动扩大检索范围"""
    return brand if is_brand_comparison(query) else base


def resolve_bm25_k(query: str, base_k: int, multiplier: int = 5) -> int:
    """BM25 检索数量：品牌对比类也扩大"""
    return max(40, resolve_k(query, base_k, base_k) * multiplier)
