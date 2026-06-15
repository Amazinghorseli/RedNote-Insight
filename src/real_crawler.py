"""
real_crawler.py — 小红书真实数据爬虫 (Phase 2)
==============================================
基于 DrissionPage 控制真实 Chrome 浏览器，抓取小红书笔记和评论。

用法:
    python src/real_crawler.py "健身服" --count 30

首次运行会打开浏览器窗口，请手动扫码登录。登录后 cookie 会保存，
后续运行自动复用，无需重复登录。
"""
import os
import sys
import json
import time
import random
import re
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from DrissionPage import ChromiumPage, ChromiumOptions
from src.config import RAW_DIR


# ============================================================
# 配置
# ============================================================
COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cookies.json")
SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={}&source=web_search_result_notes"


class XHSCrawler:
    """小红书爬虫 — 搜索笔记 + 抓取评论"""

    def __init__(self):
        self.page = None
        self._init_browser()

    def _init_browser(self):
        """初始化浏览器，尝试复用已保存的登录态"""
        co = ChromiumOptions()
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-gpu")
        # 不设 headless — 首次需要用户手动扫码登录
        # co.headless(True)  # 登录后可开启

        self.page = ChromiumPage(co)
        self._load_cookies()

    def _load_cookies(self):
        """从文件加载 cookie，恢复登录态"""
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                self.page.get("https://www.xiaohongshu.com")
                time.sleep(1)
                for c in cookies:
                    try:
                        self.page.set.cookies(c)
                    except Exception:
                        pass
                self.page.get("https://www.xiaohongshu.com")
                time.sleep(2)
                if "login" not in self.page.url:
                    print("[Crawler] ✅ Cookie 有效，已恢复登录态")
                    return
            except Exception as e:
                print(f"[Crawler] Cookie 加载失败: {e}")

        print("[Crawler] ⚠️  未登录，请在浏览器窗口中扫码登录...")
        self.page.get("https://www.xiaohongshu.com")
        input("登录完成后按 Enter 继续...")
        self._save_cookies()

    def _save_cookies(self):
        """保存当前 cookie 到文件"""
        try:
            cookies = self.page.get_cookies()
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False)
            print("[Crawler] Cookie 已保存")
        except Exception as e:
            print(f"[Crawler] Cookie 保存失败: {e}")

    def search(self, keyword: str, count: int = 30) -> list[dict]:
        """
        搜索关键词，返回笔记列表。
        每篇笔记包含: title, content, url, likes, author
        """
        print(f"\n[Crawler] 🔍 搜索: {keyword}（目标 {count} 篇）")
        notes = []

        url = SEARCH_URL.format(keyword)
        self.page.get(url)
        time.sleep(3)

        # 滚动加载更多
        last_count = 0
        no_new = 0
        while len(notes) < count and no_new < 10:
            self.page.scroll.to_bottom()
            time.sleep(random.uniform(1.5, 3.0))

            # 获取当前页面的笔记卡片
            cards = self.page.eles("css:section.note-item, css:div.note-item, css:a[href*='/explore/']")
            # 尝试多种选择器
            if not cards:
                cards = self.page.eles("css:a[href*='/explore/']")

            for card in cards:
                try:
                    href = card.attr("href") or ""
                    if "/explore/" not in href:
                        continue
                    note_id = href.split("/explore/")[-1].split("?")[0]
                    if any(n["id"] == note_id for n in notes):
                        continue

                    # 尝试获取标题
                    title = ""
                    try:
                        title_el = card.ele("css:.title, css:.note-title, css:span.title")
                        if title_el:
                            title = title_el.text
                    except Exception:
                        pass

                    notes.append({
                        "id": note_id,
                        "title": title or f"{keyword}_{note_id[:8]}",
                        "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                    })
                except Exception:
                    continue

            if len(notes) == last_count:
                no_new += 1
            else:
                no_new = 0
            last_count = len(notes)
            print(f"\r[Crawler]   已发现 {len(notes)} 篇...", end="")

        print(f"\n[Crawler] ✅ 搜索完成，共 {len(notes[:count])} 篇笔记")
        return notes[:count]

    def get_note_detail(self, note: dict) -> dict:
        """获取单篇笔记的正文内容"""
        print(f"[Crawler]   📄 {note['title'][:30]}...")
        try:
            self.page.get(note["url"])
            time.sleep(random.uniform(2.0, 4.0))

            # 获取正文
            content = ""
            try:
                desc_el = self.page.ele("css:#detail-desc, css:.note-text, css:.desc")
                if desc_el:
                    content = desc_el.text
            except Exception:
                pass

            # 获取点赞数
            likes = 0
            try:
                like_el = self.page.ele("css:.like-wrapper .count, css:.like .count")
                if like_el:
                    likes = int(re.sub(r"\D", "", like_el.text) or "0")
            except Exception:
                pass

            # 获取作者
            author = ""
            try:
                author_el = self.page.ele("css:.username, css:.author-name")
                if author_el:
                    author = author_el.text
            except Exception:
                pass

            note["content"] = content
            note["likes"] = likes
            note["author"] = author
        except Exception as e:
            print(f"        ⚠️  失败: {e}")
            note["content"] = ""
            note["likes"] = 0
            note["author"] = ""

        return note

    def get_comments(self, note: dict, max_comments: int = 30) -> list[str]:
        """获取笔记的评论"""
        comments = []
        try:
            self.page.get(note["url"])
            time.sleep(3)

            # 滚动评论区
            for _ in range(min(max_comments // 10 + 1, 10)):
                try:
                    comment_area = self.page.ele("css:.comment-container, css:.comments")
                    if comment_area:
                        comment_area.scroll.to_bottom()
                except Exception:
                    pass
                time.sleep(random.uniform(1.0, 2.0))

            # 提取评论
            comment_els = self.page.eles("css:.comment-item .content, css:.comment-content")
            for el in comment_els:
                try:
                    text = el.text.strip()
                    if text and len(text) > 2:
                        comments.append(text)
                except Exception:
                    continue

            print(f"[Crawler]   💬 获取到 {len(comments[:max_comments])} 条评论")
        except Exception as e:
            print(f"        ⚠️  评论获取失败: {e}")

        return comments[:max_comments]

    def save_note(self, note: dict, category: str, comments: list[str] = None):
        """将笔记保存为 data/raw/*.md 文件"""
        import yaml

        frontmatter = {
            "title": note.get("title", ""),
            "author": note.get("author", "unknown"),
            "date": time.strftime("%Y-%m-%d"),
            "likes": note.get("likes", 0),
            "tags": [category],
            "brand": category,
            "url": note.get("url", ""),
        }

        # 简单分析评论
        complaints = []
        purchase_intents = []
        complaint_kw = ["太贵", "不好", "差", "烂", "后悔", "千万别", "踩雷", "坑", "不行",
                        "小", "短", "丑", "慢", "掉", "坏", "退", "缺点"]
        intent_kw = ["想买", "求链接", "在哪买", "多少钱", "推荐", "种草", "求"]
        if comments:
            for c in comments:
                if any(kw in c for kw in complaint_kw):
                    complaints.append(c[:80])
                if any(kw in c for kw in intent_kw):
                    purchase_intents.append(c[:80])

        body_lines = [
            "---",
            yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip(),
            "---",
            "",
            note.get("content", ""),
            "",
            "## 评论分析",
            "```yaml",
            yaml.dump({
                "complaints": complaints[:10],
                "purchase_intents": purchase_intents[:10],
            }, allow_unicode=True, default_flow_style=False).strip(),
            "```",
        ]

        safe_title = re.sub(r"[^\w一-鿿]", "_", note.get("title", "note"))[:20]
        filename = f"{safe_title}_{note['id'][:8]}.md"
        filepath = os.path.join(RAW_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(body_lines))

        return filepath

    def crawl(self, category: str, count: int = 30, with_comments: bool = True):
        """完整抓取流程"""
        os.makedirs(RAW_DIR, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"[Crawler] 🕷️  开始抓取: {category}")
        print(f"{'='*60}")

        # 1. 搜索笔记
        notes = self.search(category, count)
        if not notes:
            print("[Crawler] ❌ 无搜索结果")
            return 0

        # 2. 逐篇抓取详情 + 评论
        saved = 0
        for i, note in enumerate(notes):
            print(f"\n[Crawler] [{i+1}/{len(notes)}] {note['title'][:40]}")

            note = self.get_note_detail(note)
            comments = None
            if with_comments:
                comments = self.get_comments(note)

            self.save_note(note, category, comments)
            saved += 1

            # 随机间隔，避免被封
            if i < len(notes) - 1:
                delay = random.uniform(3.0, 6.0)
                print(f"        ⏳ 等待 {delay:.0f}s...")
                time.sleep(delay)

        print(f"\n[Crawler] ✅ 完成！共保存 {saved} 篇笔记 → {RAW_DIR}")
        return saved

    def close(self):
        if self.page:
            self.page.quit()


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小红书真实数据抓取")
    parser.add_argument("category", help="品类名称，如：健身服、蓝牙耳机")
    parser.add_argument("--count", type=int, default=30, help="抓取篇数（默认 30）")
    parser.add_argument("--no-comments", action="store_true", help="不抓评论（更快）")
    args = parser.parse_args()

    crawler = XHSCrawler()
    try:
        saved = crawler.crawl(args.category, args.count, with_comments=not args.no_comments)
        print(f"\n✅ 已抓取 {saved} 篇，存储于 {RAW_DIR}")
        print(f"   运行 'uv run uvicorn api:app --reload' 后即可查询「{args.category}」")
    finally:
        crawler.close()
