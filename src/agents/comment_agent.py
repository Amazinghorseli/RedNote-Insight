"""
comment_agent.py - 评论分析智能体
从笔记的 HTML 注释中提取结构化评论数据，
为后续需求聚合和洞察生成提供原材料。

核心能力：
1. 重新读取原始文件（保留 HTML 注释和 frontmatter）
2. 解析 YAML 格式的评论分析数据
3. 输出结构化的分析结果
"""
import re
import yaml
from typing import List, Optional
from pathlib import Path
from langchain_core.documents import Document


class CommentAnalyzer:
    """分析笔记评论区，提取用户真实需求信号"""

    def __init__(self, raw_dir: Optional[str] = None):
        self.raw_dir = raw_dir

    def analyze(self, documents: List[Document]) -> List[dict]:
        """
        从检索到的文档中提取评论分析数据。

        输入：RAG 检索到的 Document 列表（依赖 metadata.source 定位文件）
        输出：每个文档一条结构化分析
        """
        results = []
        for doc in documents:
            source_path = self._resolve_source(doc)
            if not source_path or not Path(source_path).exists():
                continue

            raw = self._read_raw(source_path)
            frontmatter = self._parse_frontmatter(raw)
            comments = self._parse_comments(raw)

            # 合并为一条记录
            record = {
                "file": str(source_path),
                "title": frontmatter.get("title", ""),
                "brand": frontmatter.get("brand", ""),
                "likes": frontmatter.get("likes", 0),
                "comments_count": frontmatter.get("comments", 0),
                "tags": frontmatter.get("tags", []),
            }
            # 电商选品字段（从 frontmatter 提取）
            record["price"] = frontmatter.get("price", 0)
            record["cost"] = frontmatter.get("cost", 0)
            record["weight"] = frontmatter.get("weight", 0)
            record["size"] = frontmatter.get("size", "")
            record["category_type"] = frontmatter.get("category_type", "常青款")
            record["return_rate"] = frontmatter.get("return_rate", 0.05)

            # 评论分析数据
            ca = comments.get("comment_analysis", {})
            if ca:
                record["high_freq_words"] = ca.get("high_freq_words", [])
                record["complaints"] = ca.get("complaints", [])
                record["purchase_intent"] = ca.get("purchase_intent", [])
                record["comparison_mentions"] = ca.get("comparison_mentions", [])
                record["related_brands"] = ca.get("related_brands", [])
                record["ask_link_count"] = ca.get("ask_link_count", 0)
            else:
                record["high_freq_words"] = []
                record["complaints"] = []
                record["purchase_intent"] = []
                record["comparison_mentions"] = []
                record["related_brands"] = []
                record["ask_link_count"] = 0

            # 电商评分数据（从 comment 的 ecommerce 段提取）
            ec = comments.get("ecommerce", {})
            if ec:
                record["profit_margin"] = ec.get("profit_margin", 0)
                record["logistics_level"] = ec.get("logistics_level", "中")
                record["competition_level"] = ec.get("competition_level", "中")
                record["entry_difficulty"] = ec.get("entry_difficulty", "中")
                record["recommended_for_newbie"] = ec.get("recommended_for_newbie", True)
                record["differentiation_opportunity"] = ec.get("differentiation_opportunity", "")
                record["estimated_monthly_sales"] = ec.get("estimated_monthly_sales", 0)
            else:
                # 旧数据兜底：从现有数据估算
                record["profit_margin"] = 0.65
                record["logistics_level"] = "中"
                record["competition_level"] = "中"
                record["entry_difficulty"] = "中"
                record["recommended_for_newbie"] = True
                record["differentiation_opportunity"] = ""
                record["estimated_monthly_sales"] = 0

            results.append(record)

        return results

    # ---- 内部方法 ----

    def _resolve_source(self, doc: Document) -> Optional[Path]:
        """从 Document metadata 中解析原始文件路径"""
        source = doc.metadata.get("source", "")
        if not source:
            return None
        path = Path(source)
        if path.exists():
            return path
        # 相对路径处理
        if self.raw_dir:
            path = Path(self.raw_dir) / path.name
            if path.exists():
                return path
        return None

    def _read_raw(self, path: Path) -> str:
        """读取原始文件内容（包含 frontmatter 和 HTML 注释）"""
        return path.read_text(encoding="utf-8")

    def _parse_frontmatter(self, content: str) -> dict:
        """解析 YAML frontmatter（--- ... ---）"""
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                return {}
        return {}

    def _parse_comments(self, content: str) -> dict:
        """解析 HTML 注释中的 YAML（<!-- ... -->）"""
        match = re.search(r"<!--\s*(.*?)\s*-->", content, re.DOTALL)
        if match:
            try:
                return yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                return {}
        return {}
