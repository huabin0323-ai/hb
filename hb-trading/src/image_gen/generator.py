"""小红书配图生成器 — 模板化文字卡片"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageColor

from config import SIZE_FEED, SIZE_COVER, SIZE_STORY, THEMES, FONT_DIR

logger = logging.getLogger("xhs-gen")


# ======================================================================
# 字体加载
# ======================================================================

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """智能加载字体：fonts/ 目录下的自定义字体 > 系统默认"""
    font_dir = Path(FONT_DIR)
    if font_dir.exists():
        for f in font_dir.glob("*.ttf"):
            return ImageFont.truetype(str(f), size)
        for f in font_dir.glob("*.otf"):
            return ImageFont.truetype(str(f), size)

    # 回退：Windows 系统字体
    sys_fonts = [
        "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
        "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑粗体
        "C:/Windows/Fonts/simhei.ttf",   # 黑体
    ]
    for sf in sys_fonts:
        if os.path.exists(sf):
            return ImageFont.truetype(sf, size)

    return ImageFont.load_default()


def list_fonts() -> list[str]:
    """列出可用字体"""
    fonts = []
    font_dir = Path(FONT_DIR)
    if font_dir.exists():
        fonts.extend(str(f) for f in font_dir.glob("*.ttf"))
        fonts.extend(str(f) for f in font_dir.glob("*.otf"))
    if not fonts:
        fonts.append("微软雅黑 (系统)")
    return fonts


# ======================================================================
# 绘图工具
# ======================================================================

def _draw_gradient_bg(draw: ImageDraw.Draw, size: tuple, top_color: str, bottom_color: str):
    """垂直渐变背景"""
    w, h = size
    top = ImageColor.getrgb(top_color)
    bottom = ImageColor.getrgb(bottom_color)
    for y in range(h):
        r = top[0] + (bottom[0] - top[0]) * y // h
        g = top[1] + (bottom[1] - top[1]) * y // h
        b = top[2] + (bottom[2] - top[2]) * y // h
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int,
               draw: ImageDraw.Draw) -> list[str]:
    """中文自动换行"""
    lines = []
    current = ""
    for char in text:
        test = current + char
        if draw.textbbox((0, 0), test, font=font)[2] > max_width:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _draw_centered_text(draw: ImageDraw.Draw, text: str, y: int, font: ImageFont.FreeTypeFont,
                        color: str, canvas_w: int) -> int:
    """居中绘制单行文字，返回底部 Y"""
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (canvas_w - bbox[2]) // 2
    draw.text((x, y), text, fill=color, font=font)
    return y + bbox[3] - bbox[1]


# ======================================================================
# 模板
# ======================================================================

def generate_knowledge_card(
    title: str,
    body: str,
    tag: str = "",
    theme: str = "trading",
    size: tuple = SIZE_FEED,
    output_path: str = "",
) -> str:
    """知识卡片模板：大标题 + 正文 + 标签

    Args:
        title: 主标题（如 "什么是80%规则？"）
        body: 正文（支持 \n 换行）
        tag: 底部标签（如 "#价格行为学"）
        theme: 主题配色
        size: 画布尺寸
        output_path: 输出路径，为空则自动命名
    """
    colors = THEMES.get(theme, THEMES["dark_pro"])
    img = Image.new("RGB", size, colors["bg"])
    draw = ImageDraw.Draw(img)
    w, h = size

    # --- 顶部装饰线 ---
    margin = 80
    draw.rectangle([margin, 60, margin + 4, 60 + 40], fill=colors["highlight"])

    # --- 主标题 ---
    title_font = _load_font(52, bold=True)
    title_lines = _wrap_text(title, title_font, w - margin * 2, draw)
    y = 160
    for line in title_lines:
        y = _draw_centered_text(draw, line, y, title_font, colors["title"], w) + 12

    # --- 分隔线 ---
    y += 20
    line_w = 120
    draw.line([(w // 2 - line_w, y), (w // 2 + line_w, y)], fill=colors["highlight"], width=3)
    y += 40

    # --- 正文 ---
    body_font = _load_font(32)
    for para in body.split("\n"):
        if not para.strip():
            y += 20
            continue
        para_lines = _wrap_text(para, body_font, w - margin * 2, draw)
        for line in para_lines:
            draw.text((margin, y), line, fill=colors["text"], font=body_font)
            y += 48
        y += 12

    # --- 底部标签 ---
    if tag:
        tag_font = _load_font(28)
        bbox = draw.textbbox((0, 0), tag, font=tag_font)
        tag_w = bbox[2] + 40
        tag_h = bbox[3] - bbox[1] + 24
        tag_x = (w - tag_w) // 2
        tag_y = h - 120
        draw.rounded_rectangle(
            [tag_x, tag_y, tag_x + tag_w, tag_y + tag_h],
            radius=20, fill=colors["accent"]
        )
        draw.text((tag_x + 20, tag_y + 12), tag, fill=colors["text"], font=tag_font)

    # --- 底部装饰 ---
    footer_y = h - 40
    draw.line([(margin, footer_y), (w - margin, footer_y)], fill=colors["accent"], width=1)

    if not output_path:
        output_path = f"output/knowledge_{datetime.now():%Y%m%d_%H%M%S}.png"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=95)
    logger.info(f"已生成: {output_path}")
    return output_path


def generate_quote_card(
    quote: str,
    author: str = "",
    context: str = "",
    theme: str = "warm",
    size: tuple = SIZE_FEED,
    output_path: str = "",
) -> str:
    """名言/金句卡片：大字号引用 + 出处 + 背景点缀

    Args:
        quote: 引用文字（一句话）
        author: 作者
        context: 补充说明
    """
    colors = THEMES.get(theme, THEMES["warm"])
    img = Image.new("RGB", size, colors["bg"])
    draw = ImageDraw.Draw(img)
    w, h = size

    # --- 引号装饰 ---
    quote_font = _load_font(120, bold=True)
    draw.text((60, 40), "“", fill=colors["accent"], font=quote_font)

    # --- 引用文字 ---
    text_font = _load_font(44, bold=True)
    margin = 100
    lines = _wrap_text(quote, text_font, w - margin * 2, draw)
    y = 280
    for line in lines:
        y = _draw_centered_text(draw, line, y, text_font, colors["title"], w) + 20

    # --- 引号闭合 ---
    y += 30
    draw.text((w - 120, y), "”", fill=colors["accent"], font=quote_font)

    # --- 作者 ---
    if author:
        y += 120
        author_font = _load_font(28)
        _draw_centered_text(draw, f"—— {author}", y, author_font, colors["text"], w)

    # --- 补充说明 ---
    if context:
        y += 80
        ctx_font = _load_font(24)
        ctx_lines = _wrap_text(context, ctx_font, w - 200, draw)
        for line in ctx_lines:
            y = _draw_centered_text(draw, line, y, ctx_font,
                                    ImageColor.getrgb(colors["text"])[:3] + (150,)
                                    if len(ImageColor.getrgb(colors["text"])) == 3
                                    else colors["text"], w) + 10

    # --- 底部 ---
    draw.line([(margin, h - 60), (w - margin, h - 60)], fill=colors["accent"], width=2)

    if not output_path:
        output_path = f"output/quote_{datetime.now():%Y%m%d_%H%M%S}.png"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=95)
    logger.info(f"已生成: {output_path}")
    return output_path


def generate_list_card(
    title: str,
    items: list[str],
    theme: str = "dark_pro",
    size: tuple = SIZE_FEED,
    output_path: str = "",
) -> str:
    """清单/步骤卡片：数字序号 + 说明

    Args:
        title: 清单标题
        items: 条目列表
    """
    colors = THEMES.get(theme, THEMES["dark_pro"])
    img = Image.new("RGB", size, colors["bg"])
    draw = ImageDraw.Draw(img)
    w, h = size

    # --- 标题 ---
    title_font = _load_font(48, bold=True)
    margin = 80
    y = _draw_centered_text(draw, title, 120, title_font, colors["title"], w) + 40

    # 分隔
    draw.line([(margin, y), (w - margin, y)], fill=colors["accent"], width=2)
    y += 50

    # --- 列表 ---
    num_font = _load_font(40, bold=True)
    item_font = _load_font(30)
    for i, item in enumerate(items, 1):
        # 序号圆圈
        cx, cy = margin + 30, y + 15
        r = 24
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colors["highlight"])
        draw.text((cx - 12, cy - 16), str(i), fill=colors["text"], font=num_font)

        # 文字
        item_lines = _wrap_text(item, item_font, w - margin * 2 - 80, draw)
        for j, line in enumerate(item_lines):
            draw.text((margin + 80, y + j * 44), line, fill=colors["text"], font=item_font)

        y += max(44 * len(item_lines), 60) + 20

        if y > h - 120:
            break

    if not output_path:
        output_path = f"output/list_{datetime.now():%Y%m%d_%H%M%S}.png"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=95)
    return output_path


def generate_comparison_card(
    title: str,
    left_label: str, left_points: list[str],
    right_label: str, right_points: list[str],
    theme: str = "trading",
    size: tuple = SIZE_FEED,
    output_path: str = "",
) -> str:
    """对比卡片：左右两栏对比

    Args:
        title: 标题
        left_label: 左栏标题（如"散户"）
        left_points: 左栏要点
        right_label: 右栏标题（如"机构"）
        right_points: 右栏要点
    """
    colors = THEMES.get(theme, THEMES["trading"])
    img = Image.new("RGB", size, colors["bg"])
    draw = ImageDraw.Draw(img)
    w, h = size

    # 标题
    title_font = _load_font(42, bold=True)
    _draw_centered_text(draw, title, 80, title_font, colors["title"], w)

    # 中间分隔线
    mid_x = w // 2
    draw.line([(mid_x, 160), (mid_x, h - 160)], fill=colors["accent"], width=2)
    # VS 圆圈
    vs_r = 30
    draw.ellipse([mid_x - vs_r, 180 - vs_r, mid_x + vs_r, 180 + vs_r],
                 fill=colors["highlight"])
    vs_font = _load_font(28, bold=True)
    _draw_centered_text(draw, "VS", 180 - 16, vs_font, colors["text"], w)

    # 左栏
    label_font = _load_font(32, bold=True)
    point_font = _load_font(26)
    _draw_centered_text(draw, left_label, 240, label_font, colors["red"], mid_x)

    y = 300
    for p in left_points:
        lines = _wrap_text(p, point_font, mid_x - 100, draw)
        for line in lines:
            draw.text((60, y), line, fill=colors["text"], font=point_font)
            y += 36
        y += 16

    # 右栏
    _draw_centered_text(draw, right_label, 240, label_font, colors["green"], mid_x)

    y = 300
    for p in right_points:
        lines = _wrap_text(p, point_font, mid_x - 100, draw)
        for line in lines:
            draw.text((mid_x + 60, y), line, fill=colors["text"], font=point_font)
            y += 36
        y += 16

    if not output_path:
        output_path = f"output/compare_{datetime.now():%Y%m%d_%H%M%S}.png"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=95)
    return output_path
