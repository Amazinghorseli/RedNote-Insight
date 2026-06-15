"""
crawler.py — 真实数据抓取接口
=============================
Phase 1: 占位实现（使用 LLM 生成数据）
Phase 2: 接入 Playwright/DrissionPage 抓取小红书真实数据

接口设计为统一的抽象基类，Phase 2 只需实现子类即可切换。
"""
import os
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class NoteData:
    """小红书笔记数据结构"""
    title: str
    content: str
    brand: str = ""
    likes: int = 0
    comments_raw: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    author: str = ""
    url: str = ""


class BaseCrawler(ABC):
    """爬虫抽象基类"""

    @abstractmethod
    def search_notes(self, keyword: str, count: int = 10) -> list[NoteData]:
        """搜索笔记"""
        ...

    @abstractmethod
    def fetch_comments(self, note_url: str, count: int = 50) -> list[str]:
        """获取单篇笔记的评论"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查爬虫是否可用"""
        ...


class LLMGeneratorCrawler(BaseCrawler):
    """
    Phase 1 实现：用 LLM 生成模拟数据（现有逻辑的封装）
    保持接口一致，Phase 2 替换为 RealCrawler 即可
    """

    def __init__(self, raw_dir: str):
        self.raw_dir = raw_dir
        from src.fetcher import OnDemandFetcher
        self._fetcher = OnDemandFetcher(raw_dir=raw_dir)

    def search_notes(self, keyword: str, count: int = 10) -> list[NoteData]:
        print(f"[Crawler:LLM] 为「{keyword}」生成 {count} 篇笔记...")
        written = self._fetcher.fetch(keyword, count=count)
        print(f"[Crawler:LLM] 实际写入 {written} 篇")

        # 从 data/raw/ 读取刚生成的文件
        notes = []
        if written > 0:
            import glob
            import re
            pattern = os.path.join(self.raw_dir, f"*{keyword[:2]}*.md") if len(keyword) >= 2 else os.path.join(self.raw_dir, "*.md")
            files = sorted(glob.glob(os.path.join(self.raw_dir, "*.md")), key=os.path.getmtime, reverse=True)[:written]
            for f in files:
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        content = fp.read()
                    # 简单提取
                    title = ""
                    body = ""
                    in_frontmatter = False
                    in_body = False
                    for line in content.split("\n"):
                        if line.strip() == "---":
                            if not in_frontmatter:
                                in_frontmatter = True
                            else:
                                in_body = True
                            continue
                        if in_frontmatter:
                            if line.startswith("title:"):
                                title = line.replace("title:", "").strip().strip('"')
                        elif in_body:
                            body += line + "\n"
                    notes.append(NoteData(
                        title=title or os.path.basename(f).replace(".md", ""),
                        content=body[:1000],
                        url=f"file://{f}",
                    ))
                except Exception:
                    pass
        return notes

    def fetch_comments(self, note_url: str, count: int = 50) -> list[str]:
        # Phase 1 没有真实评论接口，返回 LLM 生成的占位数据
        return [f"（占位评论 {i+1}）Phase 2 将实现真实评论抓取" for i in range(min(count, 5))]

    def is_available(self) -> bool:
        return True  # LLM 生成总是可用


class RealCrawler(BaseCrawler):
    """
    Phase 2 实现：真实小红书爬虫
    ============================
    基于 DrissionPage / Playwright 模拟浏览器访问。

    待实现：
    1. 登录态管理（cookie 持久化）
    2. 搜索接口逆向（x-s, x-t 签名）
    3. 笔记详情 + 评论解析
    4. 反爬对抗（随机延迟、IP 轮换、User-Agent 池）

    用法：
        crawler = RealCrawler(
            headless=True,
            cookie_file="cookies.json",
            proxy_pool=["http://127.0.0.1:7890"],
        )
        notes = crawler.search_notes("磁吸感应灯", count=20)
        for note in notes:
            comments = crawler.fetch_comments(note.url)
    """

    def __init__(self, headless: bool = True, cookie_file: str = "", proxy_pool: list[str] = None):
        self.headless = headless
        self.cookie_file = cookie_file
        self.proxy_pool = proxy_pool or []
        self._available = False

        # TODO Phase 2: 初始化浏览器实例
        # from DrissionPage import ChromiumPage, ChromiumOptions
        # co = ChromiumOptions()
        # if headless:
        #     co.headless(True)
        # self._page = ChromiumPage(co)

    def search_notes(self, keyword: str, count: int = 10) -> list[NoteData]:
        """
        TODO Phase 2: 搜索小红书笔记
        目标 URL: https://www.xiaohongshu.com/search_result?keyword={keyword}
        需要处理：
        1. 搜索页滚动加载
        2. 笔记卡片解析（标题、作者、点赞数、封面图）
        3. 点击进入详情页获取正文
        """
        raise NotImplementedError(
            "Phase 2 待实现。当前可用 Phase 1 的 LLMGeneratorCrawler。"
        )

    def fetch_comments(self, note_url: str, count: int = 50) -> list[str]:
        """
        TODO Phase 2: 获取笔记评论
        目标 URL: https://www.xiaohongshu.com/explore/{note_id}
        需要处理：
        1. API 签名：/api/sns/web/v2/comment/page
        2. 评论分页加载
        3. 子评论展开
        """
        raise NotImplementedError(
            "Phase 2 待实现。评论接口需要 API 签名逆向。"
        )

    def is_available(self) -> bool:
        return self._available


# ============================================================
# 统一入口
# ============================================================

class CrawlerInterface:
    """
    爬虫统一接口。
    Phase 1 自动使用 LLM 生成，Phase 2 检测到真实爬虫可用时自动切换。
    """

    def __init__(self, raw_dir: str):
        self.raw_dir = raw_dir
        self._real = RealCrawler()
        self._generator = LLMGeneratorCrawler(raw_dir)

        # Phase 1: 仅 LLM 生成
        self._active = "generated"

        # Phase 2: 自动检测
        # if self._real.is_available():
        #     self._active = "real"
        #     print("[Crawler] ✅ 真实爬虫已就绪")
        # else:
        #     print("[Crawler] ⚠ 真实爬虫未就绪，使用 LLM 生成")

    def is_real(self) -> bool:
        return self._active == "real"

    def crawl(self, category: str, count: int = 20) -> dict:
        """
        抓取品类数据。Phase 1 用 LLM 生成，Phase 2 用真实爬虫。

        Returns:
            {"method": "generated"|"real", "count": int, "details": [...]}
        """
        if self._active == "real":
            notes = self._real.search_notes(category, count)
            # 保存为 markdown 文件
            written = 0
            for note in notes:
                self._save_note(note)
                written += 1
            return {"method": "real", "count": written, "details": [n.title for n in notes]}
        else:
            written = self._generator._fetcher.fetch(category, count)
            return {"method": "generated", "count": written, "details": []}

    def _save_note(self, note: NoteData) -> str:
        """将 NoteData 保存为 data/raw/*.md 文件"""
        import yaml
        frontmatter = {
            "title": note.title,
            "author": note.author or "unknown",
            "date": "2025-01-01",
            "likes": note.likes,
            "tags": note.tags or [],
            "brand": note.brand or "",
            "url": note.url or "",
        }
        body = [
            "---",
            yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip(),
            "---",
            "",
            note.content,
            "",
            "## 评论分析",
            "```yaml",
            "complaints: []",
            "purchase_intents: []",
            "```",
        ]
        import random
        filename = f"{note.title[:20] or 'note'}_{random.randint(1000,9999)}.md"
        filepath = os.path.join(self.raw_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(body))
        return filepath
