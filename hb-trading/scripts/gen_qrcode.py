"""运行 cc-connect weixin setup，提取 URL 并生成二维码图片"""
import subprocess, re, sys
import qrcode

print("Generating WeChat setup QR code...")
result = subprocess.run(
    ["C:/Users/WINDOWS/AppData/Roaming/npm/cc-connect.cmd", "weixin", "setup", "--project", "hb-assistant", "--timeout", "60"],
    capture_output=True, text=True, timeout=90
)

# 找 URL
match = re.search(r"URL: (https://liteapp\.weixin\.qq\.com[^\s]+)", result.stdout + result.stderr)
if not match:
    print("FAILED to find URL")
    print("STDOUT:", result.stdout[-500:])
    print("STDERR:", result.stderr[-500:])
    sys.exit(1)

url = match.group(1).rstrip(".")
print(f"URL: {url}")

# 生成二维码
img = qrcode.make(url)
out = "D:/hb/hb-trading/data/wechat_qr.png"
img.save(out)
print(f"QR saved to: {out}")
print("Open this file and scan it with WeChat")
