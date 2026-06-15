"""平台自动识别"""


def detect_platform(url: str) -> str:
    """根据 URL 识别平台类型"""
    url_lower = url.lower()

    if "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
        return "xhs"
    if "mp.weixin.qq.com" in url_lower:
        return "wechat"

    raise ValueError(
        f"不支持的平台: {url}\n"
        f"目前支持: 小红书 (xiaohongshu.com/xhslink.com)、微信公众号 (mp.weixin.qq.com)"
    )


def get_platform_name(platform: str) -> str:
    return {"xhs": "小红书", "wechat": "微信公众号"}.get(platform, platform)


def extract_note_id(url: str, platform: str) -> str:
    """从 URL 提取内容 ID"""
    if platform == "xhs":
        # https://www.xiaohongshu.com/explore/{note_id}
        # https://www.xiaohongshu.com/discovery/item/{note_id}
        import re
        m = re.search(r'/explore/([a-f0-9]+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/discovery/item/([a-f0-9]+)', url)
        if m:
            return m.group(1)
        raise ValueError(f"无法从小红书URL提取 note_id: {url}")

    elif platform == "wechat":
        # https://mp.weixin.qq.com/s/{biz}/{idx}?sn={sn}...
        # 直接用完整 URL 作为标识比较可靠
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:12]

    return "unknown"


def detect_profile_url(url: str) -> str | None:
    """如果是作者主页URL，返回 user_id；否则返回 None"""
    import re
    m = re.search(r'/user/profile/([a-f0-9]{24})', url)
    return m.group(1) if m else None
