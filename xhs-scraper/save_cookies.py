"""一次性保存小红书 cookie —— 跑一次，永久有效"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from scraper.browser import create_browser, save_cookies, cleanup_browser
from scraper.extractor_xhs import check_logged_in

print("=" * 50)
print("  小红书 Cookie 保存工具（只需跑一次）")
print("=" * 50)

pw, browser, context, page = create_browser()

if check_logged_in(page):
    print("\n>> 已有有效 cookie，无需重新登录！")
    save_cookies(context)
else:
    print("\n>> 正在打开小红书登录页...")
    page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded")
    print(">> 请在弹出的 Edge 窗口中扫码登录小红书")
    print(">> 等待登录（最多 120 秒）...")

    for i in range(60):
        time.sleep(2)
        if check_logged_in(page):
            print(f"\n>> 登录成功！Cookie 已永久保存")
            save_cookies(context)
            break
    else:
        print("\n>> 超时，请重新运行本脚本")

cleanup_browser(pw, browser, context)
print(">> 完成。之后 /xhs-scrape 无需再登录\n")
