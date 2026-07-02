"""
opportunities.py — 选品机会评分 API
=====================================
直接从 data/raw/ 的 frontmatter 聚合计算品类评分，
不调 LLM，轻量快速。

Endpoints:
  GET  /api/opportunities       → 全部品类排行列表
  GET  /api/opportunities/{cat} → 单个品类详细信息（未知品类返回启发式估算）
"""
import os
import re
import yaml as pyyaml
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.config import RAW_DIR

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


# ===== 品类名映射（文件名前缀 → 中文名） =====
CATEGORY_NAMES = {
    "cixi": "磁吸感应灯",
    "健身": "健身服",
    "风衣": "风衣",
    "辣条": "辣条",
    "茶杯": "茶杯",
    "dorm": "桌面收纳",
    "box": "盲盒",
    "deco": "装饰画",
    "scent": "香薰",
    "store": "收纳盒",
    "选健": "健身器材",
}


# ===== 品类启发式关键词分类 =====
CLOTHING_KEYS = ["服", "衣", "裤", "裙", "鞋", "袜", "帽", "包"]
FOOD_KEYS = ["食", "零食", "辣", "糖", "饮", "茶", "酒", "果"]
HOME_KEYS = ["家", "收纳", "饰", "灯", "桌", "椅", "柜", "床"]
BEAUTY_KEYS = ["妆", "护肤", "洗", "护", "美", "香", "霜", "乳"]
DIGITAL_KEYS = ["机", "电", "器", "充", "耳机", "线", "壳"]


def _get_frontmatter(text: str) -> dict:
    """提取 YAML frontmatter"""
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return {}
    try:
        return pyyaml.safe_load(fm_match.group(1)) or {}
    except Exception:
        return {}


def _get_comment_block(text: str) -> dict:
    """提取 HTML 注释中的 YAML 数据"""
    comm_match = re.search(r"<!--(.*?)-->", text, re.DOTALL)
    if not comm_match:
        return {}
    try:
        return pyyaml.safe_load(comm_match.group(1)) or {}
    except Exception:
        return {}


def _safe(val, default=0):
    return val if val else default


def _classify_category(name: str) -> dict:
    """根据品类名关键词推断品类属性"""
    if any(k in name for k in DIGITAL_KEYS):
        return dict(base_price=60, base_cost=18, base_weight=0.2, base_margin=0.65, base_sales=4500, comp_level="高", cat_type="常青款", tags=["需求旺", "更新快"])
    if any(k in name for k in CLOTHING_KEYS):
        return dict(base_price=188, base_cost=45, base_weight=0.5, base_margin=0.65, base_sales=3500, comp_level="高", cat_type="季节款" if "衣" in name else "常青款", tags=["需求旺", "竞争大"])
    if any(k in name for k in FOOD_KEYS):
        return dict(base_price=45, base_cost=15, base_weight=0.4, base_margin=0.60, base_sales=6000, comp_level="高", cat_type="常青款", tags=["复购高", "利润中等"])
    if any(k in name for k in HOME_KEYS):
        return dict(base_price=80, base_cost=25, base_weight=0.6, base_margin=0.65, base_sales=4000, comp_level="中", cat_type="常青款", tags=["刚需品", "利润一般"])
    if any(k in name for k in BEAUTY_KEYS):
        return dict(base_price=120, base_cost=35, base_weight=0.3, base_margin=0.70, base_sales=5000, comp_level="高", cat_type="常青款", tags=["利润高", "品牌多"])
    return dict(base_price=80, base_cost=25, base_weight=0.5, base_margin=0.60, base_sales=3000, comp_level="中", cat_type="常青款", tags=["需验证", "数据采集中"])


def _compute_scores(avg_price, avg_cost, avg_weight, avg_margin, avg_sales,
                    avg_likes=0, avg_comments=0, brand_count=0,
                    competitions=None, difficulties=None,
                    differentiations=None, cat_types=None, n=0):
    """通用评分计算，可传入估算值或实际聚合值"""
    if competitions is None:
        competitions = []
    if difficulties is None:
        difficulties = []
    if differentiations is None:
        differentiations = []
    if cat_types is None:
        cat_types = []

    price_cost_ratio = avg_price / avg_cost if avg_cost > 0 else 3.0

    profit_score = min(100, int(
        min(price_cost_ratio / 5, 1.0) * 40 +
        min(avg_margin / 0.7, 1.0) * 40 +
        20
    ))

    logistics_score = min(100, int(35 +
        (30 if avg_weight > 0 and avg_weight < 0.3 else 0) +
        (15 if avg_weight > 0 and avg_weight < 1.0 else 0) +
        (10 if competitions.count("高") < max(n, 1) * 0.5 else 0)
    ))

    demand_score = min(100, int(
        min(avg_likes / 200, 1.0) * 25 +
        min(avg_comments / 50, 1.0) * 20 +
        min(avg_sales / 5000, 1.0) * 30 +
        min(brand_count * 3, 15) +
        10
    ))

    low_comp_ratio = competitions.count("低") / max(n, 1)
    easy_entry_ratio = difficulties.count("低") / max(n, 1)
    competition_score = min(100, max(0, int(
        low_comp_ratio * 40 +
        easy_entry_ratio * 30 +
        max(0, 5 - brand_count) * 5 +
        10
    )))

    overall = max(0, min(100, int(
        profit_score * 0.30 +
        logistics_score * 0.20 +
        competition_score * 0.20 +
        demand_score * 0.30
    )))

    rec = "强烈推荐" if overall >= 80 else "可尝试" if overall >= 65 else "谨慎进入" if overall >= 50 else "不建议"
    unique_diffs = list(dict.fromkeys([d for d in differentiations if d]))[:5]
    evergreen = cat_types.count("常青款") / max(n, 1) > 0.6 if n > 0 else True

    return dict(
        scores=dict(profit=profit_score, logistics=logistics_score,
                     demand=demand_score, competition=competition_score,
                     overall=overall),
        metrics=dict(avg_price=round(avg_price, 1), avg_cost=round(avg_cost, 1),
                     avg_profit_margin=round(avg_margin, 2),
                     price_cost_ratio=round(price_cost_ratio, 1),
                     avg_weight=round(avg_weight, 2),
                     avg_likes=round(avg_likes, 1), avg_comments=round(avg_comments, 1),
                     avg_return_rate=0.05, avg_monthly_sales=avg_sales,
                     brand_count=brand_count),
        recommendation=rec,
        differentiation_directions=unique_diffs,
        evergreen=evergreen,
    )


def _calc_category_scores(cat_prefix: str) -> Optional[dict]:
    """对一个品类下的所有文件做聚合评分"""
    raw_dir = Path(RAW_DIR)
    files = sorted(raw_dir.glob(f"{cat_prefix}_*.md"))
    if not files:
        return None

    records = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        fm = _get_frontmatter(text)
        comment = _get_comment_block(text)
        ecom = comment.get("ecommerce", {}) if isinstance(comment, dict) else {}
        records.append({**fm, **ecom})

    n = len(records)
    if n == 0:
        return None

    prices = [_safe(r.get("price")) for r in records]
    costs = [_safe(r.get("cost")) for r in records]
    weights = [_safe(r.get("weight")) for r in records]
    margins = [_safe(r.get("profit_margin")) for r in records]
    likes = [_safe(r.get("likes")) for r in records]
    comments = [_safe(r.get("comments")) for r in records]
    competitions = [r.get("competition_level", "中") or "中" for r in records]
    difficulties = [r.get("entry_difficulty", "中") or "中" for r in records]
    differentiations = [r.get("differentiation_opportunity", "") or "" for r in records]
    sales = [_safe(r.get("estimated_monthly_sales")) for r in records]
    brands_list = [r.get("brand", "未知") or "未知" for r in records if r.get("brand")]
    cat_types = [r.get("category_type", "常青款") or "常青款" for r in records]

    has_ecom = any(p > 0 and c > 0 for p, c in zip(prices, costs))

    avg_price = sum(prices) / n
    avg_cost = sum(costs) / n
    avg_weight = sum(weights) / n
    avg_margin = sum(margins) / n if margins else 0
    avg_likes = sum(likes) / n
    avg_comments = sum(comments) / n
    avg_sales = sum(sales) // n
    brand_count = len(set(brands_list))

    # 缺电商字段的品类，用品类名估算
    if not has_ecom:
        cls = _classify_category(CATEGORY_NAMES.get(cat_prefix, cat_prefix))
        avg_price, avg_cost = cls["base_price"], cls["base_cost"]
        avg_weight, avg_margin = cls["base_weight"], cls["base_margin"]
        avg_sales = cls["base_sales"]

    scores = _compute_scores(avg_price, avg_cost, avg_weight, avg_margin, avg_sales,
                             avg_likes, avg_comments, brand_count,
                             competitions, difficulties, differentiations, cat_types, n)

    return {
        "category": CATEGORY_NAMES.get(cat_prefix, cat_prefix),
        "file_count": n,
        "crawl_needed": not has_ecom,
        **scores,
        "brands": list(dict.fromkeys([b for b in brands_list if b != "未知"]))[:8],
    }


# ===== 路由 =====

@router.get("")
async def list_opportunities():
    """返回全部品类的机会评分排行"""
    raw_dir = Path(RAW_DIR)
    if not raw_dir.exists():
        raise HTTPException(status_code=500, detail="data/raw/ 目录不存在")

    all_files = sorted(raw_dir.glob("*.md"))
    prefixes_seen = set()
    for f in all_files:
        m = re.match(r"^([^_]+)_\d+\.md$", f.name)
        if m:
            prefixes_seen.add(m.group(1))

    results = []
    for prefix in sorted(prefixes_seen):
        if prefix in CATEGORY_NAMES:
            scores = _calc_category_scores(prefix)
            if scores:
                results.append(scores)

    results.sort(key=lambda x: x["scores"]["overall"], reverse=True)
    return {"opportunities": results, "total": len(results)}


@router.get("/{category_name}")
async def get_opportunity_detail(category_name: str):
    """
    返回单个品类详细评分报告。
    如果品类不在已有数据中，返回启发式估算评分 + crawl_needed 标记。
    """
    prefix = None
    for pre, name in CATEGORY_NAMES.items():
        if name == category_name or pre == category_name:
            prefix = pre
            break

    if prefix:
        result = _calc_category_scores(prefix)
        if result:
            result["estimated"] = result.get("crawl_needed", False)
            return result

    # ===== 未知品类：启发式估算 =====
    cls = _classify_category(category_name)
    scores = _compute_scores(cls["base_price"], cls["base_cost"],
                             cls["base_weight"], cls["base_margin"],
                             cls["base_sales"])

    return {
        "category": category_name,
        "file_count": 0,
        "crawl_needed": True,
        "estimated": True,
        **scores,
        "brands": [],
        "tags": cls["tags"],
    }