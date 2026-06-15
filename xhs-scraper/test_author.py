import sys, time, json, re
sys.path.insert(0, ".")
from scraper.browser import create_browser, cleanup_browser

pw, browser, context, page = create_browser()

page.goto("http://xhslink.com/o/5szJEssdkiQ", wait_until="networkidle", timeout=30000)
time.sleep(3)

# 从 HTML 提取 user_id
html = page.content()
uids = set()
for m in re.finditer(r'"userId":"([^"]+)"', html): uids.add(m.group(1))
for m in re.finditer(r'"user_id":"([^"]+)"', html): uids.add(m.group(1))
for m in re.finditer(r'/user/profile/([a-f0-9]+)', html): uids.add(m.group(1))
print(f"Found user IDs: {uids}")

# 从页面 JS 提取
try:
    note_data = page.evaluate("""
        () => {
            const s = document.body.innerHTML;
            const m = s.match(/"noteId":"([^"]+)"/);
            const m2 = s.match(/"authorId":"([^"]+)"/);
            return {noteId: m?.[1], authorId: m2?.[1]};
        }
    """)
    print(f"Note data: {note_data}")
except Exception as e:
    print(f"JS eval error: {e}")

# 直接看页面 URL 中的 xsec
print(f"Page URL: {page.url[:120]}")

cleanup_browser(pw, browser, context)
