"""RSSHub JSON Feed 获取与解析模块。

JSON Feed 结构示例（来自 RSSHub ?format=json 输出）：
{
    "version": "https://jsonfeed.org/version/1.1",
    "title": "Twitter @用户名",
    "home_page_url": "https://x.com/用户名",
    "items": [
        {
            "id": "https://twitter.com/用户名/status/推文ID",
            "url": "https://x.com/用户名/status/推文ID",
            "title": "推文标题（可能被截断）",
            "content_html": "完整 HTML 内容，包含 <br> 换行、引用区块、图片、视频",
            "summary": "摘要（与 content_html 类似）",
            "date_published": "2026-01-09T01:36:56.000Z",
            "authors": [{"name": "显示名", "url": "...", "avatar": "..."}],
            "_extra": {
                "links": [
                    {"url": "引用推文URL", "type": "quote|repost", "content_html": "..."}
                ]
            }
        }
    ]
}
"""

from __future__ import annotations

import html
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .models import Tweet


# ============================================================
# 网络请求
# ============================================================

def _ensure_json_url(url: str) -> str:
    """确保 URL 返回 JSON 格式。"""
    if not url:
        return url
    if "format=json" in url:
        return url
    return f"{url}&format=json" if "?" in url else f"{url}?format=json"


def fetch_feed(
    url: str,
    retries: int = 3,
    backoff: float = 2.0,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    获取 RSSHub JSON Feed。

    Args:
        url: RSSHub URL
        retries: 重试次数
        backoff: 重试间隔（秒）
        timeout: 请求超时（秒）

    Returns:
        解析后的 JSON 字典

    Raises:
        RuntimeError: 获取失败
    """
    if not url:
        raise RuntimeError("RSS URL 未配置")

    final_url = _ensure_json_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0"}
    last_err: Optional[Exception] = None

    try:
        print(f"获取 Feed : {final_url[:80]}...")
        resp = requests.get(final_url, headers=headers, timeout=timeout)

        if resp.status_code == 200 and resp.text.strip():
            data = resp.json()
            items = data.get("items") or []
            print(f"获取成功，共 {len(items)} 条推文")
            if len(items) == 0:
                print(f"注意: Feed 中未包含任何推文，大概率是触发了推特风控，详情请见RSSHub文档和ISSUE。")
            return data
        else:
            last_err = RuntimeError(f"HTTP {resp.status_code}")
            print(f"请求失败: HTTP {resp.status_code}")

    except requests.exceptions.JSONDecodeError as e:
        last_err = e
        print(f"JSON 解析失败: {e}")
    except requests.exceptions.RequestException as e:
        last_err = e
        print(f"请求异常: {e}")

    raise RuntimeError(f"Feed 获取失败: {last_err}")


# ============================================================
# JSON 解析
# ============================================================

def parse_feed(data: Dict[str, Any], goal_username: str = "") -> List[Tweet]:
    """
    解析 RSSHub JSON Feed 为 Tweet 列表。

    Args:
        data: JSON Feed 数据
        goal_username: 目标用户名（用于构建 URL）

    Returns:
        Tweet 列表
    """
    tweets: List[Tweet] = []
    items = data.get("items") or []

    for item in items:
        tweet = _parse_item(item, goal_username)
        if tweet:
            tweets.append(tweet)

    return tweets


def _parse_item(item: Dict[str, Any], goal_username: str) -> Optional[Tweet]:
    """解析单个 JSON item 为 Tweet。"""

    # 提取推文 ID
    url = item.get("url") or item.get("id") or ""
    tweet_id = _extract_tweet_id(
        url) or _extract_tweet_id(str(item.get("id", "")))
    if not tweet_id:
        return None

    # 提取内容 HTML
    content_html = item.get("content_html") or ""
    summary = item.get("summary") or ""
    title = item.get("title") or ""

    # 使用更长的内容
    base_html = content_html if len(content_html) >= len(summary) else summary

    # 提取媒体
    images, videos = _extract_media(base_html)

    # 解析文本和引用
    text, quote_author, quote_text = _parse_content(base_html, item)

    # 如果解析出的文本太短，使用 title
    title_clean = _clean_html(title)
    if title_clean and len(title_clean) > len(text):
        text = title_clean

    # 判断是否为转推
    is_retweet = _is_retweet(text, title_clean, item)

    # 提取作者信息
    author_name, author_avatar = _extract_author(item)

    # 发布时间
    timestamp = item.get("date_published")

    return Tweet(
        id=tweet_id,
        text=text,
        url=url or f"https://x.com/{goal_username}/status/{tweet_id}",
        images=images,
        videos=videos,
        timestamp=timestamp,
        is_retweet=is_retweet,
        quote_text=quote_text,
        quote_author=quote_author,
        author_name=author_name,
        author_avatar=author_avatar,
    )


def _extract_tweet_id(url: str) -> Optional[str]:
    """从 URL 中提取推文 ID。"""
    if not url:
        return None
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None


def _extract_author(item: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """提取作者信息。"""
    authors = item.get("authors") or []
    if authors and isinstance(authors, list) and len(authors) > 0:
        author = authors[0]
        return author.get("name"), author.get("avatar")
    return None, None


def _is_retweet(text: str, title: str, item: Dict[str, Any]) -> bool:
    """判断是否为转推。"""
    # 检查文本开头
    if text.startswith("RT ") or title.startswith("RT "):
        return True

    # 检查 _extra.links 中是否有 repost 类型
    extra = item.get("_extra") or {}
    links = extra.get("links") or []
    for link in links:
        if link.get("type") == "repost":
            return True

    return False


# ============================================================
# 内容解析
# ============================================================

def _extract_media(html_content: str) -> Tuple[List[str], List[str]]:
    """
    从 HTML 内容中提取图片和视频 URL。

    Returns:
        (图片列表, 视频列表)
    """
    images: List[str] = []
    videos: List[str] = []

    # 提取 <img src="...">
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html_content, re.IGNORECASE):
        img_url = html.unescape(m.group(1))
        if img_url not in images:
            images.append(img_url)

    # 提取 <video src="...">
    for m in re.finditer(r'<video[^>]+src=["\']([^"\']+)["\']', html_content, re.IGNORECASE):
        video_url = html.unescape(m.group(1))
        if video_url not in videos:
            videos.append(video_url)

    # 提取直接的 .mp4 链接
    for m in re.finditer(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', html_content):
        video_url = m.group(0)
        if video_url not in videos:
            videos.append(video_url)

    return images, videos


def _parse_content(
    html_content: str,
    item: Dict[str, Any]
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    解析 HTML 内容，分离主文本和引用。

    Args:
        html_content: HTML 内容
        item: 原始 JSON item（用于从 _extra 获取引用信息）

    Returns:
        (主文本, 引用作者, 引用内容)
    """
    # 先解码 HTML 实体
    content = html.unescape(html_content)

    quote_author = None
    quote_text = None
    main_text = content

    # 方法1：从 <div class="rsshub-quote"> 提取引用
    quote_match = re.search(
        r'<div\s+class=["\']rsshub-quote["\']>(.*?)</div>',
        content,
        re.DOTALL | re.IGNORECASE
    )

    if quote_match:
        quote_html = quote_match.group(1)

        # 提取引用作者（第一个 <strong> 标签）
        author_match = re.search(r'<strong>([^<]+)</strong>', quote_html)
        if author_match:
            quote_author = author_match.group(1).strip()

        # 清理引用内容
        quote_text = _clean_html(quote_html)

        # 主文本去掉引用部分
        main_text = content[:quote_match.start()] + content[quote_match.end():]

    # 方法2：从 _extra.links 获取引用信息（作为补充）
    if not quote_author:
        extra = item.get("_extra") or {}
        links = extra.get("links") or []
        for link in links:
            if link.get("type") == "quote":
                link_html = link.get("content_html", "")
                if link_html:
                    author_match = re.search(
                        r'<strong>([^<]+)</strong>', link_html)
                    if author_match:
                        quote_author = author_match.group(1).strip()
                break

    # 清理主文本
    main_text = _clean_html(main_text)

    return main_text, quote_author, quote_text


def _clean_html(text: str) -> str:
    """
    清理 HTML 文本，转换为纯文本。

    - 解码 HTML 实体
    - <br> 转换为换行
    - 移除媒体标签
    - 移除其他 HTML 标签
    - 清理多余空白
    """
    if not text:
        return ""

    # HTML 实体解码
    text = html.unescape(text)

    # <br> 转换为换行
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)

    # 移除 script/style 标签及内容
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>',
                  '', text, flags=re.DOTALL | re.IGNORECASE)

    # 移除 img/video 标签（内容已在 _extract_media 中提取）
    text = re.sub(r'<(img|video)[^>]*/?\s*>', '', text, flags=re.IGNORECASE)

    # 移除闭合的 video 标签
    text = re.sub(r'</video>', '', text, flags=re.IGNORECASE)

    # 移除其他 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)

    # 清理空白
    text = re.sub(r'[ \t]+', ' ', text)      # 水平空白合并
    text = re.sub(r'\n[ \t]+', '\n', text)   # 行首空白
    text = re.sub(r'[ \t]+\n', '\n', text)   # 行尾空白
    text = re.sub(r'\n{3,}', '\n\n', text)   # 最多两个连续换行

    return text.strip()
