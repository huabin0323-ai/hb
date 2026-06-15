"""飞书同步模块 — 创建文档、同步交易分析、推送消息"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger("feishu")

APP_ID = "cli_aaa33b7217b81bea"
APP_SECRET = "uIu9ieYFwsH77tuv8OS4OwpAHPoic6dw"
BASE = "https://open.feishu.cn/open-apis"

_token: Optional[str] = None
_token_expires: float = 0


def _get_token() -> str:
    global _token, _token_expires
    if _token and time.time() < _token_expires - 60:
        return _token
    resp = requests.post(f"{BASE}/auth/v3/tenant_access_token/internal", json={
        "app_id": APP_ID, "app_secret": APP_SECRET
    }, timeout=10)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书认证失败: {data}")
    _token = data["tenant_access_token"]
    _token_expires = time.time() + data.get("expire", 7200)
    return _token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


# ======================================================================
# 文档操作
# ======================================================================

def create_doc(title: str, content: str = "") -> dict:
    """创建飞书文档，返回 document_id 和 url"""
    resp = requests.post(f"{BASE}/docx/v1/documents", headers=_headers(),
                         json={"title": title})
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"创建文档失败: {data}")

    doc_id = data["data"]["document"]["document_id"]
    url = f"https://bw0ut17d5uh.feishu.cn/docx/{doc_id}"

    if content:
        _append_blocks(doc_id, content)

    logger.info(f"飞书文档已创建: {title} -> {url}")
    return {"document_id": doc_id, "url": url}


def _append_blocks(doc_id: str, content: str) -> None:
    """向文档追加文本块"""
    # 获取 page block
    resp = requests.get(
        f"{BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}",
        headers=_headers()
    )
    data = resp.json()
    blocks = data.get("data", {}).get("items", [])

    # 找 page 级别的 block_id（通常是 document_id）
    page_id = doc_id
    for b in blocks:
        if b.get("block_type") == 2:  # page type
            page_id = b.get("block_id", doc_id)
            break

    # 分段添加文本块
    paragraphs = content.strip().split("\n\n")
    children = []
    for p in paragraphs:
        if not p.strip():
            continue
        is_header = p.startswith("# ")
        is_header2 = p.startswith("## ")
        is_header3 = p.startswith("### ")

        # 构建文本元素
        elements = _build_text_elements(p)

        block = {
            "block_type": 2,  # page
            "text": {
                "elements": elements,
                "style": {}
            }
        }

    # Simplified: use batch create for children
    elements_list = []
    for p in paragraphs:
        if not p.strip():
            continue
        elems = _build_text_elements(p)
        elements_list.append({
            "block_type": 2,
            "text": {"elements": elems, "style": {}}
        })

    # Actually, Feishu's block API is complex. Let's use a simpler approach:
    # Create blocks one by one under the page
    for i, block_data in enumerate(elements_list):
        try:
            requests.post(
                f"{BASE}/docx/v1/documents/{doc_id}/blocks/{page_id}/children",
                headers=_headers(),
                json={"children": [block_data], "index": i}
            )
        except Exception:
            pass


def _build_text_elements(text: str) -> list:
    """将 markdown 风格的文本转为飞书文本元素"""
    # 简单处理：纯文本，粗体处理标题
    elements = []
    # 去掉 markdown 标记
    clean = text
    for prefix in ["### ", "## ", "# "]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break

    elements.append({
        "text_run": {
            "content": clean,
            "text_element_style": {}
        }
    })
    return elements


def sync_case_to_feishu(case_id: str, title: str, content: str) -> dict:
    """同步案例到飞书文档"""
    full_title = f"交易案例 #{case_id}: {title}"
    doc = create_doc(full_title, content)
    return doc


def send_message(chat_id: str, text: str) -> bool:
    """发送飞书消息"""
    resp = requests.post(
        f"{BASE}/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        headers=_headers(),
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
        timeout=10,
    )
    result = resp.json()
    if result.get("code") != 0:
        logger.warning(f"消息发送失败: {result}")
    return result.get("code") == 0


# ======================================================================
# 批量历史同步
# ======================================================================

def sync_case_file(case_path: str) -> Optional[dict]:
    """读取本地 case_xxx.md 文件，同步到飞书"""
    import re
    from pathlib import Path

    path = Path(case_path)
    if not path.exists():
        logger.error(f"文件不存在: {case_path}")
        return None

    content = path.read_text(encoding="utf-8")
    # 提取标题
    title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
    title = title_match.group(1) if title_match else path.stem

    # 提取 case id
    case_id = path.stem  # case_001

    return sync_case_to_feishu(case_id, title, content)


if __name__ == "__main__":
    # 测试：同步案例001
    result = sync_case_file("D:/hb/hb-trading/data/cases/case_001.md")
    if result:
        print(f"文档URL: {result['url']}")
