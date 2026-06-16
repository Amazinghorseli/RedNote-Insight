"""
export_cookies.py — 小红书 Cookie 导出工具
===========================================
从小红书浏览器登录态中导出 cookie，用于 Streamlit Cloud 部署。

用法:
    uv run python scripts/export_cookies.py

输出:
    一段 JSON 字符串，复制后粘贴到 Streamlit Cloud Secrets:
    Key: XHS_COOKIES
    Value: <输出的 JSON>
"""
import os
import sys
import json

# Fix Windows GBK encoding for emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COOKIE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "cookies.json")


def export():
    """从文件或浏览器导出 cookie"""
    # 1. 尝试从已有文件加载
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        print(f"✅ 从 {COOKIE_FILE} 加载了 {len(cookies)} 个 cookie")
        print_cookies_for_secrets(cookies)
        return

    # 2. 否则打开浏览器让用户登录
    print("📁 未找到 cookie 文件，正在打开浏览器...")
    print("👆 请在浏览器窗口中扫码登录小红书")
    print("⏳ 登录完成后按 Enter 继续...")

    from src.real_crawler import XHSCrawler
    crawler = XHSCrawler()
    try:
        if not crawler.is_logged_in:
            crawler.login_interactive()
        if crawler.is_logged_in:
            print(f"✅ 登录成功！")
            # 重新读取刚保存的 cookie
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                print_cookies_for_secrets(cookies)
        else:
            print("❌ 登录失败，请重试")
    finally:
        crawler.close()


def print_cookies_for_secrets(cookies: list):
    """输出 cookie JSON 和使用说明"""
    cookie_json = json.dumps(cookies, ensure_ascii=False)

    print()
    print("=" * 60)
    print("📋 请复制以下内容到 Streamlit Cloud Secrets:")
    print("=" * 60)
    print()
    print("Key:   XHS_COOKIES")
    print(f"Value: {cookie_json}")
    print()
    print("=" * 60)
    print("📝 操作步骤:")
    print("  1. 打开 https://share.streamlit.io/")
    print("  2. 进入你的 App → Settings → Secrets")
    print("  3. 添加:")
    print("     XHS_COOKIES = '''<上面的 JSON>'''")
    print("  4. 保存 → Reboot App")
    print()
    print("⚠️  Cookie 有效期约 1-4 周，过期后需重新导出。")
    print("=" * 60)


if __name__ == "__main__":
    export()
