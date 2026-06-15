"""
fetcher.py - 查询时按需内容获取器
====================================
当知识库中没有用户查询的品类数据时，自动：
1. 用 LLM 推荐该品类在小红书上的热门品牌
2. 复用 NoteGenerator 生成模拟笔记（含评论分析数据）
3. 写入 data/raw/，供增量入库使用

这是 "没有就现场生成" 的核心模块。
"""
import os
import sys
import random

# 确保能导入项目根目录的 generate_data.py
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:# 安装

    sys.path.insert(0, _project_root)

from generate_data import NoteGenerator, write_notes
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.config import LLM_CONFIG


class OnDemandFetcher:
    """
    查询时自动获取品类内容。

    用法：
        fetcher = OnDemandFetcher(raw_dir="data/raw")
        count = fetcher.fetch("健身服", count=8)
        # → 在 data/raw/ 下生成了 8 篇健身服相关笔记
    """

    def __init__(self, raw_dir: str, llm=None):
        self.raw_dir = raw_dir
        self.llm = llm or ChatOpenAI(**LLM_CONFIG)

    def fetch(self, category: str, count: int = 8) -> int:
        """
        为一个品类生成笔记数据并写入磁盘。

        Args:
            category: 品类名，如 "健身服"、"蓝牙耳机"
            count: 生成篇数（默认 8 篇）

        Returns:
            实际写入的文件数
        """
        print(f"\n{'='*60}")
        print(f"[Fetcher] 触发按需抓取: {category}")
        print(f"[Fetcher] 目标: {count} 篇笔记")

        # Step 1: LLM 推荐品牌
        brands = self._suggest_brands(category)
        print(f"[Fetcher] LLM 推荐品牌: {brands}")

        # Step 2: 用 NoteGenerator 批量生成
        seed = random.randint(1, 9999)
        generator = NoteGenerator(category, brands, seed=seed)
        products = generator.generate(count)
        print(f"[Fetcher] 生成 {len(products)} 条笔记元组")

        # Step 3: 写入文件
        written = write_notes(products, self.raw_dir)
        print(f"[Fetcher] 写入 {written} 篇笔记 -> {self.raw_dir}")
        print(f"{'='*60}\n")

        return written

    def _suggest_brands(self, category: str) -> list:
        """
        让 LLM 推荐该品类在小红书上讨论最多的品牌。
        返回品牌名列表，无效时用 fallback。
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "你是一个中国电商市场专家。用户在问一个品类在小红书上"
             "讨论最多的品牌。\n\n"
             "要求：\n"
             "1. 推荐 3-5 个品牌（包括平价、中端、高端）\n"
             "2. 每个品牌后面用 | 分隔\n"
             "3. 只输出品牌名，不要解释\n\n"
             "示例输入：蓝牙耳机\n"
             "示例输出：小米|华为|漫步者|索尼|倍思"),
            ("human", "{category}"),
        ])

        try:
            msg = prompt.format_messages(category=category)
            response = self.llm.invoke(msg)
            brands = [b.strip() for b in response.content.strip().split("|") if b.strip()]
            if len(brands) >= 2:
                return brands[:5]
        except Exception as e:
            print(f"[Fetcher] 品牌推荐失败: {e}")

        # Fallback：品类名本身 + 常见泛化品牌
        return [category, f"{category}推荐", f"{category}平价", f"{category}高端"]
