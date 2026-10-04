"""Cover the query preprocessing and retrieval sizing used by the QA routes."""

import pytest

from src.core.query_utils import (
    clean_query,
    is_brand_comparison,
    resolve_bm25_k,
    resolve_k,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("灯 123 推荐", "灯 推荐"),
        ("灯 12345", "灯 12345"),
        ("123", "123"),
        ("  磁吸  感应灯  ", "磁吸 感应灯"),
    ],
)
def test_clean_query_preserves_content_and_long_identifiers(query, expected):
    assert clean_query(query) == expected


@pytest.mark.parametrize(
    ("query", "comparison", "k"),
    [("品牌A对比品牌B", True, 8), ("收纳盒推荐", True, 8), ("收纳盒材质", False, 5)],
)
def test_comparisons_expand_retrieval(query, comparison, k):
    assert is_brand_comparison(query) is comparison
    assert resolve_k(query) == k


def test_retrieval_sizes_can_be_configured():
    assert resolve_k("收纳盒材质", base=3, brand=7) == 3
    assert resolve_k("收纳盒推荐", base=3, brand=7) == 7


@pytest.mark.parametrize(("k", "expected"), [(5, 40), (9, 45)])
def test_keyword_retrieval_keeps_a_minimum_candidate_pool(k, expected):
    assert resolve_bm25_k("收纳盒材质", base_k=k) == expected
