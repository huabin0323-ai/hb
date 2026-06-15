"""图一+图二：课设变项目 对比配图"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# 画布
W, H = 1080, 1440

# 字体
def font(size, bold=False):
    """加载系统字体"""
    fonts = [
        "C:/Windows/Fonts/simhei.ttf",     # 黑体（有力量感）
        "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑粗体
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
    ]
    idx = 0 if bold else 2
    try:
        return ImageFont.truetype(fonts[idx], size)
    except:
        return ImageFont.load_default()

def draw_rounded_rect(draw, xy, r, fill):
    """圆角矩形"""
    draw.rounded_rectangle(xy, radius=r, fill=fill)

def draw_pin(draw, x, y, color="#d4a574"):
    """手绘图钉"""
    r = 14
    draw.ellipse([x-r, y-r, x+r, y+r], fill=color, outline="#b8956e", width=2)
    draw.ellipse([x-r//2, y-r//2, x+r//2, y+r//2], fill="#e8c9a0")

def draw_tape(draw, x, y, w=60, h=24, color="#e8c9a0", angle=-15):
    """手绘胶带"""
    tape = Image.new("RGBA", (w, h), (0,0,0,0))
    td = ImageDraw.Draw(tape)
    td.rounded_rectangle([0, 0, w, h], radius=3, fill=color)
    tape = tape.rotate(angle, expand=True)
    # paste with alpha
    # Actually for simplicity, just draw rotated rect slightly
    draw.rectangle([x, y, x+w, y+h], fill=color)
    draw.rectangle([x+2, y+2, x+w-2, y+h-4], fill=color, outline=(*ImageDraw.ImageColor.getrgb(color)[:3], 100))

def generate_image1():
    """图一：哪些课设，写了等于白写？"""
    bg_color = "#faf0e6"  # 浅杏色/米色
    img = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    # --- 背景质感：信纸横线 ---
    line_color = (220, 210, 195)
    for ly in range(200, H, 48):
        draw.line([(80, ly), (W - 80, ly)], fill=line_color, width=1)

    # --- 手绘装饰：左上角图钉 ---
    draw_pin(draw, 70, 70)
    draw_pin(draw, 130, 65, color="#c9a87c")
    # 胶带
    draw.rectangle([45, 58, 120, 78], fill="#e8d5b7", outline="#d4c4a5")
    # 右边也有个小胶带
    draw.rectangle([W-130, 55, W-50, 75], fill="#e8d5b7", outline="#d4c4a5")

    # --- 主标题 ---
    title = "这些课设，写了等于白写"
    tf = font(62, bold=True)
    bbox = draw.textbbox((0,0), title, font=tf)
    tx = (W - bbox[2]) // 2
    ty = 190
    # 标题阴影
    draw.text((tx+2, ty+2), title, fill=(60,50,40), font=tf)
    draw.text((tx, ty), title, fill="#3d2b1f", font=tf)

    # --- 副标题 ---
    sub = "面试官内心毫无波澜，甚至想划走"
    sf = font(34)
    sbox = draw.textbbox((0,0), sub, font=sf)
    sx = (W - sbox[2]) // 2
    sy = ty + 90
    draw.text((sx, sy), sub, fill="#8b7355", font=sf)

    # --- 分隔装饰 ---
    sep_y = sy + 70
    draw.line([(W//2 - 60, sep_y), (W//2 + 60, sep_y)], fill="#c4a882", width=2)
    # 中间小叉号
    xf = font(30)
    draw.text((W//2 - 15, sep_y - 20), "✕", fill="#cc6666", font=xf)

    # --- 三个反面例子 ---
    items = [
        "完成了一个温度采集系统",
        "设计了一个数字时钟电路",
        "参与了嵌入式智能小车开发",
    ]
    item_y = sep_y + 80
    for i, item in enumerate(items):
        # 大叉号
        draw.text((120, item_y - 10), "❌", fill="#d9534f", font=font(48))

        # 项目文字
        draw.text((200, item_y + 15), item, fill="#5c4a3a", font=font(36))

        # 每条之间虚线
        item_y += 160

    # --- 红色手绘大叉（覆盖在项目文字上方） ---
    # 用粗线画一个跨列表的大叉
    x_cx = 840; x_cy = item_y // 2 + 100
    x_size = 250
    draw.line([(x_cx-x_size, x_cy-x_size), (x_cx+x_size, x_cy+x_size)],
              fill=(220, 80, 60), width=12)
    draw.line([(x_cx+x_size, x_cy-x_size), (x_cx-x_size, x_cy+x_size)],
              fill=(220, 80, 60), width=12)
    # 叉号叠加更粗的红线（手绘感）
    draw.line([(x_cx-x_size+3, x_cy-x_size), (x_cx+x_size+3, x_cy+x_size)],
              fill=(240, 100, 80), width=5)

    # --- 底部吐槽 ---
    footer = "是不是写完了还觉得心里没底？问题就出在这👇"
    ff = font(30)
    fbox = draw.textbbox((0,0), footer, font=ff)
    fx = (W - fbox[2]) // 2
    fy = H - 180
    draw.text((fx, fy), footer, fill="#8b7355", font=ff)

    # --- 底部手绘箭头 ---
    ax = W // 2
    ay = fy + 70
    draw.line([(ax, ay), (ax, ay+40)], fill="#c4a882", width=4)
    draw.polygon([(ax-15, ay+25), (ax+15, ay+25), (ax, ay+45)], fill="#c4a882")

    out = "output/图一_课设白写.png"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    print(f"图一: {out}")
    return out


def generate_image2():
    """图二：稍微改下，课设变项目"""
    bg_color = "#e8efe0"  # 浅绿色/鼠尾草绿
    img = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    # --- 背景质感 ---
    line_color = (200, 215, 190)
    for ly in range(200, H, 48):
        draw.line([(80, ly), (W - 80, ly)], fill=line_color, width=1)

    # --- 左上角图钉 ---
    draw_pin(draw, 70, 70, color="#8fbc6b")
    draw_pin(draw, 130, 65, color="#7aad50")
    draw.rectangle([45, 58, 120, 78], fill="#d4e8c0", outline="#b8d4a0")

    # --- 主标题 ---
    title = "稍微改下，课设变项目"
    tf = font(62, bold=True)
    bbox = draw.textbbox((0,0), title, font=tf)
    tx = (W - bbox[2]) // 2
    ty = 190
    draw.text((tx+2, ty+2), title, fill=(40,60,30), font=tf)
    draw.text((tx, ty), title, fill="#2d3a1f", font=tf)

    # --- 副标题 ---
    sub = "面试官心想：这孩子做过事，可以聊聊"
    sf = font(34)
    sbox = draw.textbbox((0,0), sub, font=sf)
    sx = (W - sbox[2]) // 2
    sy = ty + 90
    draw.text((sx, sy), sub, fill="#5a7a4a", font=sf)

    # --- 分隔 ---
    sep_y = sy + 60
    draw.line([(W//2 - 100, sep_y), (W//2 + 100, sep_y)], fill="#9cbb8a", width=2)
    # 对勾
    draw.text((W//2 - 15, sep_y - 22), "✓", fill="#4a8c3f", font=font(36))

    # --- 三个正面例子 ---
    items = [
        ("1️⃣", "温度采集系统",
         "用STM32+DS18B20做了个多节点温度采集系统。",
         "自己画的PCB，焊接调试一把过。",
         "遇到时序冲突，用逻辑分析仪抓波形定位解决。",
         "最终精度控制在±0.5°C。"),
        ("2️⃣", "数字时钟电路",
         "基于74系列逻辑芯片，独立设计并搭建了",
         "一个带闹钟功能的数字时钟。",
         "从原理图到面包板验证再到焊板，独立完成。",
         "最大收获是学会了排查信号竞争冒险。"),
        ("3️⃣", "嵌入式智能小车",
         "负责小车底层驱动开发，用PID算法实现",
         "了稳定循迹功能。最大挑战是解决电机对",
         "传感器的干扰，通过隔离电源和软件滤波",
         "搞定，抗干扰能力提升明显。"),
    ]

    item_y = sep_y + 60
    for emoji, name, *lines in items:
        # 序号
        draw.text((80, item_y), emoji, fill="#3d6b2e", font=font(44))

        # 项目名（加粗）
        nf = font(34, bold=True)
        draw.text((150, item_y + 5), name, fill="#2d3a1f", font=nf)

        # 箭头
        draw.text((150, item_y + 5 + 42), "→", fill="#4a8c3f", font=font(28))

        # 详细描述
        df = font(28)
        for j, line in enumerate(lines):
            # 每行开头加小对勾
            draw.text((200, item_y + 50 + j * 38), "✓", fill="#4a8c3f", font=font(22))
            draw.text((235, item_y + 50 + j * 38), line, fill="#4a5a3a", font=df)

        # 分隔线
        item_y += 50 + len(lines) * 38 + 35
        draw.line([(100, item_y), (W - 100, item_y)], fill=(185, 200, 170), width=1)
        item_y += 30

    # --- 底部总结 ---
    footer = '记住：面试官看的不是项目"高不高级"'
    footer2 = '是你"清不清楚"自己做了什么'
    ff = font(32, bold=True)
    for i, ft in enumerate([footer, footer2]):
        fbox = draw.textbbox((0,0), ft, font=ff)
        fx = (W - fbox[2]) // 2
        fy = H - 180 + i * 50
        draw.text((fx+1, fy+1), ft, fill=(255,255,255), font=ff)
        draw.text((fx, fy), ft, fill="#2d3a1f", font=ff)

    # 底部装饰：对勾
    draw.text((W//2 + fbox[2]//2 + 20, H - 170), "✅", fill="#4a8c3f", font=font(36))

    out = "output/图二_课设变项目.png"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    print(f"图二: {out}")
    return out


if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    generate_image1()
    generate_image2()
    print("Done - open output/ folder")
