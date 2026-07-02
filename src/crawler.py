"""
crawler.py — 真实数据抓取接口
=============================
基于 DrissionPage 的真实小红书爬虫封装。
当知识库中没有用户查询的品类数据时，自动打开浏览器抓取真实笔记和评论。
"""
import os
import json
import random

# ============================================================
# 统一入口
# ============================================================

class CrawlerInterface:
    """
    爬虫统一接口，支持本地和云端（Streamlit Cloud）两种模式。
    - 本地：DrissionPage 打开可见浏览器，扫码登录，cookie 存文件
    - 云端：DrissionPage 无头 Chromium，cookie 从 Streamlit Secrets 读取
    """

    def __init__(self, raw_dir: str, cookies_json: str = ""):
        self.raw_dir = raw_dir
        self._crawler = None
        self._init_error = None
        self._is_cloud = False

        try:
            from src.real_crawler import XHSCrawler
            self._crawler = XHSCrawler(cookies_json=cookies_json)
            self._is_cloud = self._crawler.is_cloud_mode
            if self._crawler.is_logged_in:
                mode = "[Cloud] 云端" if self._is_cloud else "[Local] 本地"
                print(f"[Crawler] [OK] {mode}爬虫已就绪")
            else:
                if self._is_cloud:
                    print("[Crawler] [Cloud] 云端未登录。请在 Streamlit Secrets 中配置 XHS_COOKIES")
                else:
                    print("[Crawler] [WARN] 本地未登录。运行: uv run python src/real_crawler.py \"品类名\" 登录")
        except Exception as e:
            self._init_error = str(e)
            print(f"[Crawler] [FAIL] 爬虫初始化失败: {e}")

    @property
    def is_available(self) -> bool:
        """爬虫是否可用（已初始化且已登录）"""
        return self._crawler is not None and self._crawler.is_logged_in

    @property
    def needs_login(self) -> bool:
        """是否需要登录"""
        return self._crawler is not None and not self._crawler.is_logged_in

    @property
    def is_cloud(self) -> bool:
        """是否云端模式"""
        return self._is_cloud

    def login(self, timeout_minutes: int = 5) -> bool:
        """
        交互式登录：打开浏览器等待用户扫码。

        Returns:
            True 表示登录成功，False 表示失败/超时
        """
        if not self._crawler:
            print(f"[Crawler] 爬虫不可用: {self._init_error}")
            return False
        return self._crawler.login_interactive(timeout_minutes=timeout_minutes)

    def crawl(self, category: str, count: int = 30) -> dict:
        """
        抓取品类数据。

        Returns:
            {"method": "real", "count": int, "details": [...]}
        """
        if not self._crawler:
            return {"method": "error", "count": 0, "error": f"爬虫不可用: {self._init_error}"}

        if not self._crawler.is_logged_in:
            if self._is_cloud:
                return {
                    "method": "error",
                    "count": 0,
                    "error": "未登录。请在本地运行 `uv run python scripts/export_cookies.py` 导出 cookie，然后粘贴到 Streamlit Secrets → XHS_COOKIES"
                }
            return {
                "method": "error",
                "count": 0,
                "error": "未登录小红书。请先在命令行运行: uv run python src/real_crawler.py \"品类名\" 完成登录"
            }

        saved = self._crawler.crawl(category, count=count, with_comments=True)
        return {
            "method": "real",
            "count": saved,
            "details": [],
        }

    def fetch_hot_list(self, max_items: int = 30) -> list[dict]:
        """
        抓取小红书实时热榜（轻量，不需要登录）

        Returns:
            [{"keyword": "辣条", "tag": "热", "rank": 1, "category": "食品", ...}, ...]
        """
        if not self._crawler:
            print(f"[Crawler] 爬虫不可用，使用兜底热榜: {self._init_error}")
            from src.real_crawler import XHSCrawler
            return XHSCrawler._fallback_hot_list()
        try:
            return self._crawler.fetch_hot_search(max_items=max_items)
        except Exception as e:
            print(f"[Crawler] 热榜抓取失败: {e}")
            from src.real_crawler import XHSCrawler
            return XHSCrawler._fallback_hot_list()
