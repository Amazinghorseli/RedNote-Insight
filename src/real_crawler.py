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
    """小红书爬虫 — 搜索笔记 + 抓取评论
    支持两种模式：
    - 本地：打开可见浏览器，交互式扫码登录，cookie 持久化到文件
    - 云端：无头 Chromium，从 JSON 字符串加载 cookie（通过 Streamlit Secrets）
    """

    def __init__(self, headless: bool = False, cookies_json: str = ""):
        self.page = None
        self.headless = headless
        self.cookies_json = cookies_json  # 云端模式：从 secrets 传入的 cookie JSON
        self._logged_in = False
        self._is_cloud = self._detect_cloud()
        self._need_relogin = False   # search() 发现登录弹窗时设为 True
        self._init_browser()

    @staticmethod
    def _detect_cloud() -> bool:
        """检测是否运行在 Streamlit Cloud 环境"""
        # Streamlit Cloud 设置了 STREAMLIT_SERVER_ADDRESS 环境变量
        return bool(os.environ.get("STREAMLIT_SERVER_ADDRESS")) or \
               bool(os.environ.get("STREAMLIT_RUNTIME"))

    def _init_browser(self):
        """初始化浏览器，尝试复用已保存的登录态"""
        co = ChromiumOptions()
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-gpu")
        co.set_argument("--disable-dev-shm-usage")
        co.set_argument("--disable-blink-features=AutomationControlled")
        co.set_argument("--disable-features=VizDisplayCompositor")
        co.set_argument("--window-size=1920,1080")
        # 随机化 User-Agent，避免被识别为爬虫
        ua = random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ])
        co.set_user_agent(ua)

        if self._is_cloud or self.headless:
            co.headless(True)
            # Streamlit Cloud 上 Chromium 的安装路径
            if self._is_cloud:
                for browser_path in ["/usr/bin/chromium-browser", "/usr/bin/chromium",
                                     "/usr/bin/google-chrome", "/usr/bin/chrome"]:
                    if os.path.exists(browser_path):
                        co.set_browser_path(browser_path)
                        print(f"[Crawler] [Cloud] 云端模式，使用: {browser_path}")
                        break

        self.page = ChromiumPage(co)
        # 额外隐身：覆盖 webdriver 特征
        self._apply_stealth()
        self._load_cookies()

    def _apply_stealth(self):
        """隐藏自动化特征，避免被网站检测到"""
        try:
            self.page.run_js("""
                // 覆盖 navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                // 覆盖 chrome 对象
                window.chrome = { runtime: {} };
                // 覆盖权限查询
                const originalQuery = navigator.permissions.query;
                navigator.permissions.query = (params) => (
                    params.name === 'notifications' ?
                        Promise.resolve({ state: 'granted' }) :
                        originalQuery(params)
                );
                // 覆盖 plugins 长度
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                // 覆盖 languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en'],
                });
            """)
            print("[Crawler] [Stealth] 隐身脚本已注入")
        except Exception as e:
            print(f"[Crawler] [Stealth] 注入失败（可忽略）: {e}")

    @property
    def is_logged_in(self) -> bool:
        """检查是否已登录小红书"""
        return self._logged_in

    @property
    def is_cloud_mode(self) -> bool:
        """是否运行在云端模式"""
        return self._is_cloud

    def _load_cookies(self):
        """加载 cookie：云端从 secrets JSON，本地从文件"""
        cookies = None

        # 1. 云端模式：从 JSON 字符串加载
        if self.cookies_json:
            try:
                cookies = json.loads(self.cookies_json)
                print(f"[Crawler] [Cloud] 从 Secrets 加载了 {len(cookies)} 个 cookie")
            except json.JSONDecodeError as e:
                print(f"[Crawler] [WARN] Secrets cookie 解析失败: {e}")

        # 2. 本地模式：从文件加载
        if not cookies and os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                print(f"[Crawler] [File] 从文件加载了 {len(cookies)} 个 cookie")
            except Exception as e:
                print(f"[Crawler] Cookie 文件加载失败: {e}")

        # 3. 应用 cookie（DrissionPage 4.x: page.set.cookies() 接受列表）
        if cookies:
            try:
                self.page.get("https://www.xiaohongshu.com")
                time.sleep(1)
                # 批量设置 cookie
                self.page.set.cookies(cookies)
                self.page.get("https://www.xiaohongshu.com")
                time.sleep(3)
                # 检查是否有登录弹窗
                if self._is_login_modal_shown():
                    print("[Crawler] [WARN] 首页显示登录弹窗，尝试关闭...")
                    self._close_login_modal()
                    time.sleep(1)
                    # 再试试 explore 页
                    self.page.get("https://www.xiaohongshu.com/explore")
                    time.sleep(3)
                    if self._is_login_modal_shown():
                        self._close_login_modal()
                        time.sleep(1)
                if self._verify_logged_in():
                    self._logged_in = True
                    print("[Crawler] [OK] Cookie 有效，已恢复登录态")
                    return
                else:
                    print("[Crawler] [WARN] Cookie 已过期，需要重新登录")
            except Exception as e:
                print(f"[Crawler] Cookie 应用失败: {e}")

        self._logged_in = False
        if self._is_cloud:
            print("[Crawler] [Cloud] 云端未登录。请在本地导出 cookie 并配置 Streamlit Secrets: XHS_COOKIES")
        else:
            print("[Crawler] [WARN] 未登录。请运行: uv run python src/real_crawler.py \"品类名\" 来登录")

    def _is_login_modal_shown(self) -> bool:
        """检查当前页面是否显示了登录弹窗（CSS 检测 + HTML 文本兜底）"""
        try:
            # 方法1: CSS 选择器检测弹窗元素
            for sel in [
                "css:.login-modal",
                "css:.reds-modal-open.login-modal",
                "css:[class*='login-modal']",
                "xpath://div[contains(@class,'login-modal')]",
            ]:
                try:
                    el = self.page.ele(sel, timeout=0.5)
                    if el and el.is_displayed():
                        return True
                except Exception:
                    continue

            # 方法2: 检查页面文本（兜底：有时弹窗在 DOM 但不可被 CSS 选择器识别）
            try:
                page_text = self.page.text or ""
                login_markers = ["登录查看精彩内容", "扫码登录", "登录后查看更多"]
                for marker in login_markers:
                    if marker in page_text:
                        print(f"[Crawler] [Login] 页面文本检测到登录提示: '{marker}'")
                        return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _close_login_modal(self) -> bool:
        """尝试关闭登录弹窗"""
        try:
            for sel in [
                "css:.close-button",
                "css:.icon-btn-wrapper.close-button",
                "css:[class*='close-button']",
                "css:.reds-modal button",
                "xpath://div[contains(@class,'close-button')]",
                "xpath://*[local-name()='svg' and @xlink:href='#close']/..",
            ]:
                try:
                    el = self.page.ele(sel, timeout=0.5)
                    if el and el.is_displayed():
                        el.click()
                        time.sleep(1)
                        print("[Crawler] [Login] 已尝试关闭登录弹窗")
                        return True
                except Exception:
                    continue

            # 兜底: 按 ESC 键
            try:
                self.page.run_js("document.querySelector('.close-button')?.click()")
                time.sleep(1)
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _verify_logged_in(self) -> bool:
        """
        通过 cookie 和页面元素双重验证是否已登录小红书。
        比单纯检查 URL 更可靠，因为 Xiaohongshu 可能使用弹窗登录而非页面跳转。
        """
        try:
            # 方法0: 先检查当前页面是否有登录弹窗
            if self._is_login_modal_shown():
                # 有登录弹窗 → 尝试关闭它，如果能关掉且有关闭后的内容，说明可能还有效
                closed = self._close_login_modal()
                if closed:
                    time.sleep(1)
                    # 关闭后再检查一下弹窗是否还在
                    if not self._is_login_modal_shown():
                        # 弹窗已关闭，cookie 可能还有效
                        pass

            # 方法1: 检查是否存在小红书认证 cookie
            xhs_cookies = self.page.cookies(all_domains=True, all_info=False)
            auth_cookie_names = {"a1", "web_session", "session", "sid", "authorization", "token", "xhs"}
            for cookie in xhs_cookies:
                name = cookie.get("name", "").lower()
                if name in auth_cookie_names:
                    val = cookie.get("value", "")
                    if val and len(val) > 5:
                        # 找到有效 cookie，但还要确保没有登录弹窗
                        return not self._is_login_modal_shown()

            # 方法2: 检查页面上登录后的特征元素
            for selector in [
                "css:.user-avatar",
                "css:.avatar",
                "css:[class*='avatar']",
                "css:[class*='user']",
                "xpath://img[contains(@class,'avatar')]",
            ]:
                try:
                    el = self.page.ele(selector, timeout=0.5)
                    if el:
                        return True
                except Exception:
                    continue

            # 方法3: 如果当前在登录页，尝试导航到首页后再次检查 cookie
            url = self.page.url or ""
            if "login" in url or "passport" in url:
                self.page.get("https://www.xiaohongshu.com")
                time.sleep(2)
                # 导航后检查登录弹窗
                if self._is_login_modal_shown():
                    self._close_login_modal()
                    time.sleep(1)
                # 导航后直接检查 cookie（避免递归）
                xhs_cookies = self.page.cookies(all_domains=True, all_info=False)
                for cookie in xhs_cookies:
                    name = cookie.get("name", "").lower()
                    if name in auth_cookie_names:
                        val = cookie.get("value", "")
                        if val and len(val) > 5:
                            return not self._is_login_modal_shown()
        except Exception:
            pass
        return False

    def login_interactive(self, timeout_minutes=10):
        """
        交互式登录：打开浏览器，等待用户扫码登录。
        使用 URL + cookie + 页面元素三重检测，避免传统 URL-only 检测的误判。
        """
        if self._logged_in:
            print("[Crawler] 已登录，无需重复操作")
            return True

        print("[Crawler] 正在打开小红书登录页...")
        self.page.get("https://www.xiaohongshu.com")
        print("[Crawler] [Action] 请在浏览器窗口中扫码登录")
        print(f"[Crawler] [Wait] 等待登录完成（最长{timeout_minutes}分钟）...")

        # 轮询检测登录状态（每1秒检测一次，响应更快）
        max_attempts = timeout_minutes * 60  # 1秒间隔
        for attempt in range(max_attempts):
            time.sleep(1)
            try:
                if self._verify_logged_in():
                    print("[Crawler] [OK] 登录成功！")
                    self._logged_in = True
                    self._save_cookies()
                    # 登录后暖启动：验证 session
                    try:
                        print("[Crawler] [Login] 验证 session 有效性...")
                        self.page.get("https://www.xiaohongshu.com/explore")
                        time.sleep(3)
                        if self._is_note_page_blocked() or self._is_login_modal_shown():
                            print("[Crawler] [WARN] 登录后仍被拦截，等待后重试...")
                            time.sleep(5)
                            self.page.get("https://www.xiaohongshu.com/explore")
                            time.sleep(3)
                        else:
                            print("[Crawler] [OK] session 验证通过")
                    except Exception:
                        pass
                    return True
            except Exception:
                pass

        current_url = self.page.url[:80] if self.page else "N/A"
        print(f"[Crawler] [FAIL] 登录超时（{timeout_minutes}分钟），当前URL: {current_url}")
        print("[Crawler] [Hint] 如果已扫码但没有反应，请刷新页面重新扫码")
        print("[Crawler] [Hint] 也可以手动在浏览器地址栏输入 xiaohongshu.com 确保已登录")
        return False

    def _save_cookies(self):
        """保存当前 cookie 到文件"""
        try:
            cookies = self.page.cookies(all_domains=True, all_info=True)
            cookie_list = list(cookies) if cookies else []
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(cookie_list, f, ensure_ascii=False)
            print(f"[Crawler] Cookie 已保存 ({len(cookie_list)} 条)")
        except Exception as e:
            print(f"[Crawler] Cookie 保存失败: {e}")

    def search(self, keyword: str, count: int = 30) -> list[dict]:
        """
        搜索关键词，返回笔记列表。
        每篇笔记包含: id, title, url
        """
        print(f"\n[Crawler] [Search] 搜索: {keyword}（目标 {count} 篇）")
        notes = []

        url = SEARCH_URL.format(keyword)

        def _navigate_and_dismiss(target_url: str) -> bool:
            """导航到目标页面并处理登录弹窗，返回 True 表示弹窗已处理完毕"""
            self.page.get(target_url)
            time.sleep(5)
            if self._is_login_modal_shown():
                print("[Crawler] [Search] 检测到登录弹窗，尝试关闭...")
                if self._close_login_modal():
                    time.sleep(2)
                    if self._is_login_modal_shown():
                        print("[Crawler] [Search] 关闭弹窗后仍在，尝试先暖启动 session...")
                        # 先去首页或 explore 页暖一下 session
                        for warmup_url in [
                            "https://www.xiaohongshu.com/explore",
                            "https://www.xiaohongshu.com",
                        ]:
                            self.page.get(warmup_url)
                            time.sleep(3)
                            self._close_login_modal()
                            time.sleep(1)
                            if not self._is_login_modal_shown():
                                print(f"[Crawler] [Search] {warmup_url} 暖启动成功")
                                # 重新导航到目标
                                self.page.get(target_url)
                                time.sleep(5)
                                self._close_login_modal()
                                time.sleep(1)
                                break
                else:
                    print("[Crawler] [Search] [WARN] 无法关闭登录弹窗，cookie 可能已过期")
            return self._is_login_modal_shown()

        # 第一步：导航 + 处理弹窗
        login_still_shown = _navigate_and_dismiss(url)

        if login_still_shown:
            print("[Crawler] [Search] [WARN] 登录弹窗持续存在，请重新登录")
            print("[Crawler] [Search] 已登录状态可能已过期，建议运行: uv run python src/real_crawler.py")
            # 即使弹窗还在，也尝试抓取（可能弹窗背后有内容）

        # ===== 策略 A (首选): 用浏览器 fetch() 直接调搜索 API =====
        print("[Crawler] [Search] 尝试 API 搜索...")
        try:
            api_notes_raw = self.page.run_js(f"""
                (async () => {{
                    const url = 'https://edith.xiaohongshu.com/api/sns/web/v1/search/notes?' +
                        'keyword=' + encodeURIComponent('{keyword}') +
                        '&page=1&page_size={min(count, 50)}&sort=general';
                    const resp = await fetch(url, {{
                        credentials: 'include',
                        headers: {{ 'accept': 'application/json' }},
                    }});
                    const data = await resp.json();
                    const items = data?.data?.items || [];
                    return JSON.stringify(items.map(item => {{
                        const note = item.note_card || item;
                        const id = item.id || note.note_id || '';
                        const title = (note.display_title || note.title || '').slice(0, 100);
                        const interact = note.interact_info || {{}};
                        const likes = parseInt(interact.liked_count || 0);
                        const user = (item.user || note.user || {{}});
                        const author = user.nickname || user.nick_name || '';
                        return {{ id, title, likes, author }};
                    }}));
                }})()
            """)

            if api_notes_raw and isinstance(api_notes_raw, str) and api_notes_raw.startswith("["):
                api_items = json.loads(api_notes_raw)
                seen_ids = set()
                for item in api_items:
                    nid = item.get("id", "")
                    if nid and nid not in seen_ids:
                        seen_ids.add(nid)
                        notes.append({
                            "id": nid,
                            "title": item.get("title", f"{keyword}_{nid[:8]}"),
                            "url": f"https://www.xiaohongshu.com/explore/{nid}",
                            "likes": item.get("likes", 0),
                            "author": item.get("author", ""),
                        })
                print(f"[Crawler] [Search] [OK] API 搜索到 {len(notes)} 篇笔记")
            else:
                print(f"[Crawler] [Search] [WARN] API 返回异常: {str(api_notes_raw)[:100]}")
        except Exception as e:
            print(f"[Crawler] [Search] API 搜索失败: {e}")

        # ===== 策略 B (兜底): 页面滚动 + HTML 正则 =====
        if not notes:
            print("[Crawler] [Search] API 无结果，退回到页面解析...")
            no_new = 0
            last_count = 0
            max_scrolls = max(count // 3, 30)
            scroll_count = 0

            while len(notes) < count and no_new < 10 and scroll_count < max_scrolls:
                self.page.scroll.to_bottom()
                scroll_count += 1
                time.sleep(random.uniform(1.5, 3.0))

                page_html = self.page.html or ""
                hex_ids = re.findall(r'/explore/([a-f0-9]{24})', page_html)
                if hex_ids:
                    seen_ids = {n["id"] for n in notes}
                    for note_id in hex_ids:
                        if note_id not in seen_ids:
                            seen_ids.add(note_id)
                            notes.append({
                                "id": note_id,
                                "title": f"{keyword}_{note_id[:8]}",
                                "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                            })
                    no_new = 0
                    last_count = len(notes)
                else:
                    no_new += 1
                last_count = len(notes)
                print(f"\r[Crawler]   已发现 {len(notes)} 篇...", end="")

        print(f"\n[Crawler] [OK] 搜索完成，共 {len(notes[:count])} 篇笔记")

        # 如果一篇都没找到且有登录弹窗 → 需要重新登录
        if not notes and self._is_login_modal_shown():
            self._need_relogin = True
            print("[Crawler] [Search] [WARN] 搜索到 0 篇笔记 + 登录弹窗 -> cookie 过期，需要重新登录")
        else:
            self._need_relogin = False

        return notes[:count]

    def _is_note_page_blocked(self) -> bool:
        """检测笔记页是否被「扫码查看」拦截"""
        try:
            page_text = self.page.text or ""
            blocked_keywords = [
                "暂时无法浏览", "请打开小红书App扫码查看", "扫码查看",
                "小红书如何扫码", "问题反馈", "返回首页",
            ]
            matches = sum(1 for kw in blocked_keywords if kw in page_text)
            return matches >= 3  # 匹配到 3 个以上关键词才判定为被拦截
        except Exception:
            return False

    def _try_fetch_via_api(self, note_id: str) -> dict:
        """通过小红书内部 API 获取笔记内容（浏览器 fetch + cookies 自动携带）"""
        result = {"content": "", "likes": 0, "author": ""}
        try:
            js = f"""
            (async () => {{
                try {{
                    const resp = await fetch(
                        'https://edith.xiaohongshu.com/api/sns/web/v1/feed?source_note_id={note_id}',
                        {{ credentials: 'include', headers: {{ 'accept': 'application/json' }} }}
                    );
                    const data = await resp.json();
                    const items = data?.data?.items || [];
                    if (!items.length) return 'NO_DATA';
                    const card = items[0].note_card || {{}};
                    const interact = card.interact_info || {{}};
                    const user = (items[0].user || card.user || {{}});
                    return JSON.stringify({{
                        content: card.desc || '',
                        likes: parseInt(interact.liked_count || interact.likedCount || 0),
                        author: user.nickname || user.nickName || '',
                    }});
                }} catch(e) {{ return 'FETCH_ERR: ' + e.message; }}
            }})()
            """
            raw = self.page.run_js(js)
            import json
            if raw and raw.startswith('{'):
                data = json.loads(raw)
                result.update(data)
                print(f"        [API] [OK] 获取内容成功（{len(result['content'])} 字符，{result['likes']} 赞）")
            elif raw and 'NO_DATA' in str(raw):
                print(f"        [API] [WARN] API 返回空数据")
            else:
                print(f"        [API] [WARN] 失败: {str(raw)[:80]}")
        except Exception as e:
            print(f"        [API] [WARN] 异常: {e}")

        return result

    def get_note_detail(self, note: dict) -> dict:
        """获取单篇笔记的正文内容 — API 优先"""
        title_short = note.get('title', '')[:30]
        note_id = note.get("id", "")
        print(f"[Crawler] [Page] {title_short}...")

        # ===== 策略 A: API fetch() 直接拿（最快最稳） =====
        api_result = self._try_fetch_via_api(note_id)
        if api_result["content"]:
            note["content"] = api_result["content"]
            note["likes"] = api_result.get("likes", 0) or note.get("likes", 0)
            note["author"] = api_result.get("author", "") or note.get("author", "")
            return note

        # ===== 策略 B: 浏览器打开笔记页 + 关闭弹窗 =====
        try:
            self.page.get(note["url"])
            time.sleep(random.uniform(2.0, 4.0))
            if self._is_login_modal_shown():
                self._close_login_modal()
                time.sleep(1)
            blocked = self._is_note_page_blocked()
            if blocked:
                print(f"        [WARN] 被拦截，放弃此篇")
                note["content"] = note.get("content", "")
                note["likes"] = note.get("likes", 0)
                note["author"] = note.get("author", "")
                return note

            # 获取正文
            content = ""
            for desc_sel in ["css:#detail-desc", "css:.note-text", "css:.desc",
                             "css:.note-scroller", "css:.content"]:
                try:
                    desc_el = self.page.ele(desc_sel)
                    if desc_el:
                        content = desc_el.text.strip()
                        if len(content) > 20:
                            break
                except Exception:
                    continue

            likes = 0
            try:
                for like_sel in ["css:.like-wrapper .count", "css:.like .count",
                                 "css:.interact-item .count"]:
                    like_el = self.page.ele(like_sel)
                    if like_el:
                        likes = int(re.sub(r"\D", "", like_el.text) or "0")
                        break
            except Exception:
                pass

            author = ""
            try:
                for author_sel in ["css:.username", "css:.author-name", "css:.name"]:
                    author_el = self.page.ele(author_sel)
                    if author_el:
                        author = author_el.text.strip()
                        if author:
                            break
            except Exception:
                pass

            note["content"] = content
            note["likes"] = likes
            note["author"] = author
        except Exception as e:
            print(f"        [WARN] 获取详情失败: {e}")
            note["content"] = note.get("content", "")
            note["likes"] = note.get("likes", 0)
            note["author"] = note.get("author", "")

        return note

    def _try_fetch_comments_via_api(self, note_id: str) -> list[str]:
        """通过 API 获取评论（不依赖页面渲染）"""
        try:
            js = f"""
            (async () => {{
                const allComments = [];
                let cursor = '';
                for (let i = 0; i < 3; i++) {{
                    const url = 'https://edith.xiaohongshu.com/api/sns/web/v2/comment/page?' +
                        'note_id={note_id}&cursor=' + cursor + '&top_size=10&image_formats=jpg';
                    const resp = await fetch(url, {{
                        credentials: 'include',
                        headers: {{ 'accept': 'application/json' }},
                    }});
                    const data = await resp.json();
                    const commentList = data?.data?.comments || [];
                    for (const c of commentList) {{
                        allComments.push(c.content || '');
                        for (const sc of (c.sub_comments || [])) {{
                            allComments.push(sc.content || '');
                        }}
                    }}
                    cursor = data?.data?.cursor || '';
                    if (!cursor || !data?.data?.has_more) break;
                }}
                return JSON.stringify(allComments);
            }})()
            """
            raw = self.page.run_js(js)
            if raw and raw.startswith('['):
                comments = json.loads(raw)
                print(f"        [API] [OK] 评论 API 获取到 {len(comments)} 条")
                return comments
        except Exception as e:
            print(f"        [API] [WARN] 评论 API 失败: {e}")
        return []

    def get_comments(self, note: dict, max_comments: int = 30, level: str = "all") -> list[str]:
        """
        获取笔记的评论 — API 优先。

        Args:
            note: 笔记数据（含 url）
            max_comments: 最大评论数
            level: 评论层级
                "all"  — 抓取所有评论（一级 + 回复，混在一起）
                "top"  — 只抓一级评论（直接评论笔记的，不含回复）
                "hot"  — 只抓热评（按热度排序的前几条）

        Returns:
            评论文本列表
        """
        note_id = note.get("id", "")

        # ===== 策略 A: API 获取 =====
        api_comments = self._try_fetch_comments_via_api(note_id)
        if api_comments:
            if level == "hot":
                return api_comments[:max(5, max_comments // 3)]
            elif level == "top":
                return api_comments[:max_comments]  # API 返回的顶级在前
            return api_comments[:max_comments]

        # ===== 策略 B: 页面抓取（兜底） =====
        comments = []
        try:
            self.page.get(note["url"])
            time.sleep(3)
            # 检查登录弹窗
            if self._is_login_modal_shown():
                self._close_login_modal()
                time.sleep(1)

            # 滚动评论区
            for _ in range(min(max_comments // 5 + 1, 15)):
                try:
                    self.page.scroll.to_bottom()
                except Exception:
                    pass
                time.sleep(random.uniform(1.0, 2.0))

            # ===== 策略 1: 先用特定选择器抓取 =====
            if level == "top":
                # 只抓一级评论：尝试 direct-child 选择器 + 排除嵌套
                selectors = [
                    "css:.comment-list > .comment-item > .content",
                    "css:.comments-wrapper > .comment-item > .content",
                    "css:.note-scroller > .comment-item > .content",
                    "css:.comment-item > .content",           # 兜底：所有 comment-item 的直接子 content
                ]
            elif level == "hot":
                # 热评：通常排在前几条，只取前 1/3
                selectors = [
                    "css:.comment-list > .comment-item > .content",
                    "css:.comments-wrapper > .comment-item > .content",
                    "css:.note-scroller > .comment-item > .content",
                    "css:.comment-item > .content",
                ]
            else:
                # 全部评论（原有行为）
                selectors = [
                    "css:.comment-item .content",
                    "css:.comment-content",
                    "css:.comments .content",
                    "css:.note-comment .content",
                ]

            comment_els = []
            for sel in selectors:
                try:
                    found = self.page.eles(sel)
                    if found:
                        comment_els = found
                        print(f"[Crawler] [Comments] 使用选择器: {sel} → {len(found)} 个元素")
                        break
                except Exception:
                    continue

            # ===== 策略 2: 如果特定选择器没找到，退回到全量 + 过滤 =====
            if not comment_els:
                # 全量抓取
                for sel in [
                    "css:.comment-item .content", "css:.comment-content",
                    "css:.comments .content", "css:.note-comment .content",
                ]:
                    try:
                        found = self.page.eles(sel)
                        if found:
                            comment_els = found
                            break
                    except Exception:
                        continue

                # 如果只想要一级评论，尝试从 DOM 结构判断是否为嵌套
                if level in ("top", "hot") and comment_els:
                    filtered = []
                    for el in comment_els:
                        try:
                            # 检查父元素是否有嵌套标记
                            parent = el.parent()
                            parent_classes = parent.attr("class") or "" if parent else ""
                            grandparent = parent.parent() if parent else None
                            gp_classes = grandparent.attr("class") or "" if grandparent else ""
                            # 如果父/祖父元素包含 reply/sub/child 关键词，跳过
                            if any(k in parent_classes.lower() for k in ["reply", "sub", "child", "二级"]):
                                continue
                            if any(k in gp_classes.lower() for k in ["reply", "sub", "child", "二级"]):
                                continue
                            filtered.append(el)
                        except Exception:
                            filtered.append(el)
                    print(f"[Crawler] [Comments] DOM 过滤后: {len(filtered)}/{len(comment_els)} 条一级评论")
                    comment_els = filtered

            # 提取文本
            for el in comment_els:
                try:
                    text = el.text.strip()
                    if text and len(text) > 2:
                        comments.append(text)
                except Exception:
                    continue

            # 热评模式：只取前 1/3（按页面排序，热评在前）
            if level == "hot":
                comments = comments[:max(5, max_comments // 3)]

            print(f"[Crawler] [Comments] 获取到 {len(comments[:max_comments])} 条评论 (level={level})")
        except Exception as e:
            print(f"        [WARN] 评论获取失败: {e}")

        return comments[:max_comments]

    def save_note(self, note: dict, category: str, comments: list[str] = None):
        """
        将笔记保存为 data/raw/*.md 文件。
        格式与 generate_data.py 一致，确保 CommentAnalyzer 能正确解析。
        """
        import yaml

        # 分析评论
        complaints, purchase_intents, comparison_mentions, high_freq_words = \
            self._analyze_comments(comments or [])

        # 构建 frontmatter（与 generate_data.py 格式一致）
        frontmatter = {
            "title": note.get("title", ""),
            "author": note.get("author", "unknown"),
            "likes": note.get("likes", 0),
            "comments": len(comments or []),
            "date": time.strftime("%Y-%m-%d"),
            "tags": [category, note.get("author", "")],
            "brand": category,
            "price": 0,
            "cost": 0,
            "weight": 0.5,
            "size": "",
            "category_type": "常青款",
            "return_rate": 0.05,
        }

        # 构建评论分析数据（HTML 注释格式，与 generate_data.py 一致）
        comment_analysis = {
            "high_freq_words": high_freq_words[:10],
            "complaints": complaints[:10],
            "purchase_intent": purchase_intents[:10],
            "comparison_mentions": comparison_mentions[:5],
            "related_brands": [category],
            "ask_link_count": sum(1 for c in (comments or [])
                                  if any(kw in c for kw in ["链接", "在哪买", "求", "想要"])),
        }

        ecommerce = {
            "profit_margin": 0.65,
            "logistics_level": "中",
            "competition_level": "中",
            "entry_difficulty": "中",
            "recommended_for_newbie": True,
            "differentiation_opportunity": "",
            "estimated_monthly_sales": 0,
        }

        # 组装文件内容
        body_lines = [
            "---",
            yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip(),
            "---",
            "",
            note.get("content", ""),
            "",
            "---",
            "<!--",
            yaml.dump({
                "comment_analysis": comment_analysis,
                "ecommerce": ecommerce,
            }, allow_unicode=True, default_flow_style=False).strip(),
            "-->",
        ]

        safe_title = re.sub(r"[^\w一-鿿]", "_", note.get("title", "note"))[:20]
        filename = f"{safe_title}_{note['id'][:8]}.md"
        filepath = os.path.join(RAW_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(body_lines))

        return filepath

    def _analyze_comments(self, comments: list[str]) -> tuple:
        """关键词分析评论，提取：投诉、购买意向、对比提及、高频词"""
        complaints = []
        purchase_intents = []
        comparison_mentions = []
        all_words = []

        complaint_kw = [
            "太贵", "不好", "差", "烂", "后悔", "千万别", "踩雷", "坑", "不行",
            "小", "短", "丑", "慢", "掉", "坏", "退", "缺点", "失望", "难用",
            "不值", "垃圾", "无语", "鸡肋", "智商税", "浪费", "别买", "慎入",
            "不好用", "有问题", "坏了", "掉了", "破了", "不推荐", "避雷",
        ]
        intent_kw = [
            "想买", "求链接", "在哪买", "多少钱", "推荐", "种草", "求", "想要",
            "怎么买", "哪里买", "想入", "好想要", "被种草", "下单", "链接",
        ]
        comparison_kw = [
            "比", "不如", "还是", "更", "不如买", "对比", "选择",
        ]

        for c in comments:
            # 投诉
            if any(kw in c for kw in complaint_kw):
                complaints.append(c[:100])
            # 购买意向
            if any(kw in c for kw in intent_kw):
                purchase_intents.append(c[:100])
            # 对比
            if any(kw in c for kw in comparison_kw):
                comparison_mentions.append(c[:100])
            # 高频词（简单分词）
            all_words.extend([w for w in c if len(w) > 1])

        # 简单高频词统计
        from collections import Counter
        word_counts = Counter(all_words)
        high_freq = [w for w, _ in word_counts.most_common(15)]

        return complaints, purchase_intents, comparison_mentions, high_freq

    def crawl(self, category: str, count: int = 30, with_comments: bool = True, comment_level: str = "all"):
        """完整抓取流程

        Args:
            category: 品类名称
            count: 抓取篇数
            with_comments: 是否抓评论
            comment_level: 评论层级 ("all" / "top" / "hot")
        """
        if not self._logged_in:
            msg = ("[Crawler] [FAIL] 未登录，无法抓取\n"
                   "[Crawler] [Hint] 本地: uv run python src/real_crawler.py \"品类名\" 登录\n"
                   "[Crawler] [Hint] 云端: 在 Streamlit Secrets 中配置 XHS_COOKIES")
            print(msg)
            return 0

        os.makedirs(RAW_DIR, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"[Crawler] [Crawl]  开始抓取: {category}")
        print(f"{'='*60}")

        # 1. 搜索笔记（如发现需重新登录，自动触发一次登录后重试）
        MAX_RETRIES = 1
        for attempt in range(MAX_RETRIES + 1):
            notes = self.search(category, count)
            if notes:
                break  # 找到笔记 → 继续

            if not self._need_relogin:
                # 不是因为登录弹窗导致的空结果 → 不重试
                break

            print(f"\n[Crawler] [Crawl] [RETRY] cookie 已过期，尝试重新登录（第{attempt+1}次）...")
            self._logged_in = False  # 强制设为未登录态
            if not self._is_cloud:
                if not self.login_interactive():
                    print("[Crawler] [FAIL] 重新登录失败")
                    return 0
                print("[Crawler] [OK] 重新登录成功，重新搜索...")
            else:
                print("[Crawler] [FAIL] 云端模式下 cookie 过期，请更新 Streamlit Secrets XHS_COOKIES")
                return 0

        if not notes:
            print("[Crawler] [FAIL] 无搜索结果")
            return 0

        # 2. 逐篇抓取详情 + 评论
        saved = 0
        print(f"\n[Crawler] [Crawl] 搜索到 {len(notes)} 篇笔记，开始逐篇抓取详情...")
        for i, note in enumerate(notes):
            print(f"\n[Crawler] [{i+1}/{len(notes)}] {note.get('title', '')[:40]}")

            try:
                note = self.get_note_detail(note)
                comments = None
                if with_comments:
                    comments = self.get_comments(note, level=comment_level)

                self.save_note(note, category, comments)
                saved += 1

                # 随机间隔，避免被封
                if i < len(notes) - 1:
                    delay = random.uniform(3.0, 6.0)
                    print(f"        [Wait] {delay:.0f}s...")
                    time.sleep(delay)
            except Exception as e:
                print(f"        [ERR] 处理笔记失败: {e}")
                import traceback
                traceback.print_exc()
                # 尝试保存一个基础版本
                try:
                    self.save_note(note, category, [])
                    saved += 1
                except Exception:
                    pass

        print(f"\n[Crawler] [OK] 完成！共保存 {saved} 篇笔记 → {RAW_DIR}")
        return saved

    # ============================================================
    # 热榜抓取（偷懒模式：只抓搜索建议，不翻页面）
    # ============================================================
    def fetch_hot_search(self, max_items: int = 30) -> list[dict]:
        """
        从小红书探索页 + 搜索框抓取热门搜索关键词。

        策略 A: 首页搜索框下拉热词
        策略 B: 探索页热门笔记标题提取关键词
        策略 C: 兜底内置词库
        """
        print(f"\n[Crawler] [HotSearch] 开始抓取小红书热榜...")
        items = []

        try:
            # ═══ 策略 A: 搜索框下拉热词 ═══
            self.page.get("https://www.xiaohongshu.com")
            time.sleep(4)
            print("[Crawler] [HotSearch] 主页加载完成")

            # 尝试激活搜索框
            search_clicked = False
            for selector in [
                "css:#search-input",
                "css:input[placeholder*='搜索']",
                "css:.search-input",
                "css:[class*='search'] input",
                "css:input[type='text']",
            ]:
                try:
                    el = self.page.ele(selector, timeout=3)
                    if el:
                        el.click()
                        search_clicked = True
                        print(f"[Crawler] [HotSearch] 搜索框已激活: {selector}")
                        break
                except Exception:
                    continue

            if search_clicked:
                time.sleep(3)  # 等下拉面板渲染
                page_html = self.page.html or ""

                # 方法 1: 面板文本提取
                panel_texts = []
                for panel_sel in [
                    "css:.search-suggest-panel",
                    "css:.suggest-panel",
                    "css:[class*='suggest-panel']",
                    "css:[class*='search-panel']",
                    "css:[class*='dropdown-panel']",
                    "css:.suggest-list",
                    "css:[class*='hot-search']",
                ]:
                    try:
                        panel = self.page.ele(panel_sel, timeout=2)
                        if panel:
                            t = panel.text.strip()
                            if t:
                                panel_texts.append(t)
                                print(f"[Crawler] [HotSearch] 面板命中: {panel_sel} → {t[:100]}...")
                    except Exception:
                        continue

                # 方法 2: 所有 suggest/search 相关的 span/div
                if not panel_texts:
                    suggest_els = []
                    for sel in [
                        "css:[class*='suggest'] span",
                        "css:[class*='search'] div[class*='item'] span",
                        "css:[class*='hot'] span",
                        "css:[class*='trend'] span",
                    ]:
                        try:
                            found = self.page.eles(sel, timeout=2)
                            if found:
                                suggest_els.extend(found)
                        except Exception:
                            continue

                    if suggest_els:
                        combined = " ".join([el.text.strip() for el in suggest_els if el.text and len(el.text.strip()) >= 2])
                        if combined:
                            panel_texts = [combined]

                # 解析面板文本
                if panel_texts:
                    seen_keywords = set()
                    rank = 0
                    for pt in panel_texts:
                        for line in pt.replace('\t', '\n').split('\n'):
                            kw = line.strip()
                            # 清理：去掉数字前缀、热度标记等
                            import re as re_mod
                            kw = re_mod.sub(r'^\d+[\.\、\)\s]*', '', kw)
                            kw = re_mod.sub(r'\s*(热|新|荐|HOT|爆)$', '', kw)
                            kw = kw.strip()

                            if not kw or len(kw) < 2 or len(kw) > 25:
                                continue
                            if kw in seen_keywords:
                                continue
                            if re_mod.match(r'^[\d\.\s\-—，,]+$', kw):
                                continue
                            if '小红书' in kw or '登录' in kw or '注册' in kw:
                                continue

                            seen_keywords.add(kw)
                            rank += 1
                            items.append({
                                "keyword": kw,
                                "rank": rank,
                                "tag": "热" if rank <= 5 else ("新" if rank <= 15 else ""),
                                "category": self._guess_category(kw),
                                "trend": "up" if rank <= 10 else "stable",
                                "hots": max(100 - rank * 3, 10),
                            })
                            if len(items) >= max_items:
                                break
                        if len(items) >= max_items:
                            break

            # ═══ 策略 B: 探索页热门笔记提取 ═══
            if len(items) < 5:
                print("[Crawler] [HotSearch] 策略B: 探索页提取热门笔记标题")
                self.page.get("https://www.xiaohongshu.com/explore")
                time.sleep(5)

                # 滚动加载内容
                for _ in range(4):
                    self.page.scroll.to_bottom()
                    time.sleep(2)

                # 精确提取笔记卡片标题（排除页面 chrome）
                title_els = []
                title_selectors = [
                    "css:a[href*='/explore/'] div.title",
                    "css:a[href*='/explore/'] .title",
                    "css:section.note-item .title",
                    "css:.note-item .title",
                    "css:.feeds-page .note-item a.title",
                ]
                for sel in title_selectors:
                    try:
                        found = self.page.eles(sel, timeout=2)
                        if found and len(found) > 3:
                            title_els = found
                            print(f"[Crawler] [HotSearch] 探索页标题命中: {sel} → {len(found)} 条")
                            break
                    except Exception:
                        continue

                # 如果标准选择器失败，用更宽泛的获取方式
                if not title_els:
                    # 从页面链接提取
                    try:
                        links = self.page.eles("css:a[href*='/explore/']", timeout=3)
                        note_links = [l for l in links if l and l.text and len(l.text.strip()) > 3
                                     and 'footer' not in (getattr(l, 'parent', None) or '')]
                        title_els = note_links
                        print(f"[Crawler] [HotSearch] 探索页链接提取: {len(title_els)} 条")
                    except Exception:
                        pass

                # 过滤页面 chrome（导航、版权、菜单等）
                blacklist = {
                    "创作中心", "业务合作", "关于我们", "联系我们", "用户协议",
                    "隐私政策", "举报", "帮助", "反馈", "登录", "注册",
                    "首页", "发现", "消息", "通知", "我", "搜索",
                    "下载", "APP", "小程序", "桌面版", "手机版",
                    "关注", "推荐", "热门", "最新", "商品", "店铺",
                    "收藏", "点赞", "评论", "分享", "更多",
                    "小红书", "沪ICP", "ICP备", "备案", "版权所有",
                    "Cookie", "隐私", "条款", "广告", "推广",
                }

                # 从标题提取关键词
                title_keywords = {}
                import re as re_mod
                for el in title_els[:60]:
                    try:
                        t = el.text.strip()
                        if not t or len(t) < 3 or len(t) > 60:
                            continue
                        # 过滤黑名单
                        if t in blacklist or any(b in t for b in blacklist if len(b) >= 3):
                            continue

                        # 拆分提取有意义的词组
                        for kw in re_mod.split(r'[，。,\.、\s#＃｜|【】\[\]（）\(\)]+', t):
                            kw = kw.strip()
                            if 2 <= len(kw) <= 15 and not re_mod.match(r'^[\d\.\s\-—，,、/\?？！!]+$', kw):
                                if kw not in blacklist:
                                    title_keywords[kw] = title_keywords.get(kw, 0) + 1
                    except Exception:
                        continue

                # 按频次排序
                sorted_kws = sorted(title_keywords.items(), key=lambda x: -x[1])
                existing = {i["keyword"] for i in items}
                rank = len(items)
                for kw, freq in sorted_kws:
                    if kw in existing or len(kw) < 2 or kw in blacklist:
                        continue
                    rank += 1
                    items.append({
                        "keyword": kw,
                        "rank": rank,
                        "tag": "热" if rank <= 5 else "",
                        "category": self._guess_category(kw),
                        "trend": "up" if freq >= 3 else "stable",
                        "hots": min(freq * 25, 100),
                    })
                    existing.add(kw)
                    if len(items) >= max_items:
                        break

                if items:
                    print(f"[Crawler] [HotSearch] 探索页提取到 {len(items)} 个有效关键词")

            # ═══ 策略 C: 兜底 ═══
            if not items:
                print("[Crawler] [HotSearch] 兜底：使用内置热榜词库")
                items = self._fallback_hot_list()

            print(f"[Crawler] [HotSearch] 最终提取到 {len(items)} 条热词")

        except Exception as e:
            print(f"[Crawler] [HotSearch] 异常: {e}")
            import traceback
            traceback.print_exc()
            items = self._fallback_hot_list()

        return items

    @staticmethod
    def _guess_category(text: str) -> str:
        """根据关键词猜测品类"""
        cat_map = {
            "穿搭": "服饰", "衣服": "服饰", "裙子": "服饰", "鞋": "服饰",
            "化妆": "美妆", "护肤": "美妆", "口红": "美妆", "面膜": "美妆",
            "零食": "食品", "吃": "食品", "蛋糕": "食品", "奶茶": "食品",
            "家居": "家居", "收纳": "家居", "装修": "家居", "灯": "家居",
            "手机": "数码", "耳机": "数码", "电脑": "数码",
            "健身": "运动", "运动": "运动", "瑜伽": "运动",
            "猫": "宠物", "狗": "宠物", "宠物": "宠物",
            "旅行": "旅游", "旅游": "旅游", "酒店": "旅游",
            "养娃": "母婴", "宝宝": "母婴", "孕": "母婴",
        }
        for kw, cat in cat_map.items():
            if kw in text:
                return cat
        return "其他"

    @staticmethod
    def _fallback_hot_list() -> list[dict]:
        """兜底热榜（极简内置词库，避免空榜）"""
        fallback = [
            "穿搭", "化妆", "护肤", "减肥", "健身",
            "收纳", "装修", "零食", "奶茶", "咖啡",
            "穿搭灵感", "显瘦穿搭", "平价好物", "家居好物", "数码好物",
            "通勤穿搭", "早春穿搭", "夜间护肤", "抗老", "美白",
            "宠物用品", "旅行攻略", "本地美食", "周末去哪儿", "读书推荐",
        ]
        items = []
        for i, kw in enumerate(fallback):
            items.append({
                "keyword": kw,
                "rank": i + 1,
                "tag": "热" if i < 5 else "",
                "category": XHSCrawler._guess_category(kw),
                "trend": "up" if i < 10 else "stable",
                "hots": max(100 - i * 3, 15),
            })
        return items

    def close(self):
        if self.page:
            try:
                self.page.quit()
            except Exception:
                pass


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
        # CLI 模式：如果未登录，交互式等待登录
        if not crawler.is_logged_in:
            if not crawler.login_interactive():
                print("[FAIL] 登录失败，退出")
                sys.exit(1)

        saved = crawler.crawl(args.category, args.count, with_comments=not args.no_comments)
        print(f"\n[OK] 已抓取 {saved} 篇，存储于 {RAW_DIR}")
        print(f"   运行 'uv run uvicorn api:app --reload' 后即可查询「{args.category}」")
    finally:
        crawler.close()
