"""X/Twitter 推文转发脚本（基于 RSSHub）。

功能:
- 通过 RSSHub 获取指定用户最新推文，无需官方 API。
- 保存最后发送的推文 ID，避免重复通知。
- 图片: 发送 Telegram 图片或图片组；视频/转推: 只发送文本+原链接。

环境变量（.env 或 CI secrets）:
- GOAL_USERNAME: 目标用户名（不含 @），用于格式化显示。
- X_RSS_URL: RSSHub 链接，例如 https://rsshub-kurrna.fly.dev/twitter/user/<username>
- TG_TOKEN_2: Telegram Bot Token（用于本脚本）
- TG_CHAT_ID: Telegram Chat ID（接收通知的聊天）
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
import time
import json
import html
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv


ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

GOAL_USERNAME = os.getenv("GOAL_USERNAME", "")
X_RSS_URL = os.getenv("X_RSS_URL", "")
TG_TOKEN = os.getenv("TG_TOKEN_2", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

DATA_DIR = ROOT / "messages" / "x_monitor"
LAST_TWEET_FILE = DATA_DIR / "last_tweet_id.txt"
STATE_FILE = DATA_DIR / "state.json"
ARCHIVE_DIR = DATA_DIR / "archive"


@dataclass
class Tweet:
    id: str
    text: str
    url: str
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    timestamp: Optional[str] = None
    is_retweet: bool = False


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def load_last_id() -> Optional[str]:
    if LAST_TWEET_FILE.exists():
        v = LAST_TWEET_FILE.read_text(encoding="utf-8").strip()
        return v or None
    return None


def save_last_id(tid: str) -> None:
    ensure_data_dir()
    LAST_TWEET_FILE.write_text(tid, encoding="utf-8")


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: Dict[str, Any]) -> None:
    ensure_data_dir()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def content_hash(tweet: Tweet) -> str:
    base = "||".join([
        tweet.text,
        "|".join(tweet.images),
        "|".join(tweet.videos),
    ])
    return hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()

def fetch_rss(url: str, retries: int = 3, backoff: float = 2.0) -> str:
    if not url:
        raise RuntimeError("X_RSS_URL 未配置")
    final_url = url
    last_err = None
    headers = {"User-Agent": "Mozilla/5.0"}
    for i in range(retries):
        try:
            resp = requests.get(final_url, headers=headers, timeout=20)
            if resp.status_code == 200 and resp.text.strip():
                return resp.text
            last_err = RuntimeError(f"HTTP {resp.status_code}")
        except Exception as e:
            last_err = e
        time.sleep(backoff)
    raise RuntimeError(f"RSS 获取失败: {last_err}")


def parse_rss(content: str) -> List[Tweet]:
    tweets: List[Tweet] = []
    try:
        root = ET.fromstring(content)
    except Exception as e:
        raise RuntimeError(f"RSS 解析失败: {e}")

    for item in root.findall(".//item"):
        link = _get_text(item, "link") or ""
        guid = _get_text(item, "guid") or ""
        tid = _extract_tweet_id(link) or _extract_tweet_id(guid)
        if not tid:
            continue

        title = _get_text(item, "title") or ""
        desc = _get_text(item, "description") or ""
        desc = html.unescape(desc)
        # 取更长的文本（title 有时被截断）
        base_text = title if len(title) >= len(desc) else desc
        pub_date = _get_text(item, "pubDate")

        images, videos = _extract_media(desc)
        text = _clean_text(base_text)
        is_retweet = text.startswith("RT @") or "转推" in text[:10]

        tweet = Tweet(
            id=tid,
            text=text,
            url=link or f"https://x.com/{GOAL_USERNAME}/status/{tid}",
            images=images,
            videos=videos,
            timestamp=pub_date,
            is_retweet=is_retweet,
        )
        tweets.append(tweet)

    return tweets


def _get_text(item: ET.Element, tag: str) -> Optional[str]:
    el = item.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return None


def _extract_tweet_id(url: str) -> Optional[str]:
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None


def _extract_media(desc: str) -> tuple[List[str], List[str]]:
    images: List[str] = []
    videos: List[str] = []
    # img 标签
    for m in re.finditer(r"<img[^>]+src=['\"]([^'\"]+)['\"]", desc, re.IGNORECASE):
        images.append(m.group(1))
    # mp4 链接
    for m in re.finditer(r"https?://[^\s\"]+\.mp4", desc):
        videos.append(m.group(0))
    return images, videos


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&")
    return text.strip()


def _escape_md(text: str) -> str:
    # 简单转义 Markdown 特殊字符，避免截断
    for ch in ["_", "*", "`", "[", "]"]:
        text = text.replace(ch, f"\\{ch}")
    return text


def format_jst_now() -> str:
    jst = ZoneInfo("Asia/Tokyo")
    now = datetime.now(jst)
    return now.strftime("%Y/%m/%d %H:%M:%S JST")


# Telegram 发送函数
def send_text(msg: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        print("未配置 TG_TOKEN_2 或 TG_CHAT_ID")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": False}
    try:
        r = requests.post(url, json=payload, timeout=15)
        ok = r.ok and r.json().get("ok")
        if not ok:
            print(f"发送文本失败: {r.text}")
        return bool(ok)
    except Exception as e:
        print(f"发送文本异常: {e}")
        return False


def send_photo(photo_url: str, caption: str = "") -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    payload = {"chat_id": TG_CHAT_ID, "photo": photo_url, "caption": caption[:1024], "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=30)
        ok = r.ok and r.json().get("ok")
        if not ok:
            print(f"发送图片失败: {r.text}")
        return bool(ok)
    except Exception as e:
        print(f"发送图片异常: {e}")
        return False


def send_media_group(imgs: List[str], caption: str = "") -> bool:
    if not imgs:
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup"
    media = []
    for i, img in enumerate(imgs[:10]):  # Telegram 限制 10 张
        item = {"type": "photo", "media": img}
        if i == 0 and caption:
            item["caption"] = caption[:1024]
            item["parse_mode"] = "Markdown"
        media.append(item)
    payload = {"chat_id": TG_CHAT_ID, "media": media}
    try:
        r = requests.post(url, json=payload, timeout=60)
        ok = r.ok and r.json().get("ok")
        if not ok:
            print(f"发送图片组失败: {r.text}")
        return bool(ok)
    except Exception as e:
        print(f"发送图片组异常: {e}")
        return False


def write_archive(tweet: Tweet, status: str, now_iso: str) -> None:
    """将推文保存到本地存档以防被删除/编辑"""
    ensure_data_dir()
    fname = ARCHIVE_DIR / f"{tweet.id}.md"
    lines = [
        f"# {status} {tweet.id}",
        "",
        f"时间: {now_iso}",
        f"链接: {tweet.url}",
        "",
        tweet.text,
        "",
    ]
    if tweet.images:
        lines.append("图片:")
        lines.extend(tweet.images)
        lines.append("")
    if tweet.videos:
        lines.append("视频:")
        lines.extend(tweet.videos)
        lines.append("")
    fname.write_text("\n".join(lines), encoding="utf-8")


def format_message(tweet: Tweet) -> str:
    user = GOAL_USERNAME or "user"
    lines = []
    if tweet.is_retweet:
        lines.append(f"🔁 *@{user}* 转推")
    else:
        lines.append(f"🐦 *@{user}* 发布新推文")
    lines.append("")
    safe_text = _escape_md(tweet.text)
    lines.append(safe_text)
    lines.append("")
    lines.append(f"🔗 [查看原推]({tweet.url})")
    if tweet.timestamp:
        lines.append(f"⏰ {tweet.timestamp}")
    lines.append(f"🕓 {format_jst_now()}")
    if tweet.videos:
        for v in tweet.videos:
            lines.append(f"🎞 {v}")
    return "\n".join(lines)


def notify(tweet: Tweet) -> bool:
    msg = format_message(tweet)
    ok_text = send_text(msg)
    # 视频或转推：只发文本即可
    if tweet.is_retweet or tweet.videos:
        return ok_text
    # 图片：文本之后补发图片（不带 caption，避免截断文本）
    if tweet.images:
        if len(tweet.images) == 1:
            send_photo(tweet.images[0], "")
        else:
            send_media_group(tweet.images, "")
    return ok_text


def check_and_send() -> int:
    if not X_RSS_URL:
        print("错误：未配置 X_RSS_URL")
        return 1
    if not TG_TOKEN or not TG_CHAT_ID:
        print("错误：未配置 TG_TOKEN_2 或 TG_CHAT_ID")
        return 1

    ensure_data_dir()

    try:
        content = fetch_rss(X_RSS_URL)
        tweets = parse_rss(content)
    except Exception as e:
        print(f"拉取或解析失败: {e}")
        return 1

    if not tweets:
        print("未获取到推文")
        return 0

    # 当前时间
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # 载入历史状态
    state = load_state()
    last_id_file = load_last_id()

    current_ids = set()
    notifications = []  # (tweet, status)

    for t in tweets:
        current_ids.add(t.id)
        h = content_hash(t)
        rec = state.get(t.id)
        if rec is None:
            # 新推文
            notifications.append((t, "new"))
            state[t.id] = {
                "hash": h,
                "text": t.text,
                "images": t.images,
                "videos": t.videos,
                "url": t.url,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "missing_streak": 0,
                "deleted": False,
            }
        else:
            # 已存在，检查编辑
            if rec.get("hash") != h:
                notifications.append((t, "edited"))
            state[t.id].update({
                "hash": h,
                "text": t.text,
                "images": t.images,
                "videos": t.videos,
                "url": t.url,
                "last_seen": now_iso,
                "missing_streak": 0,
                "deleted": False,
            })

    # 检测可能删除的推文：未出现在当前列表的历史推文
    for tid, rec in list(state.items()):
        if tid in current_ids:
            continue
        if rec.get("deleted"):
            continue
        rec["missing_streak"] = rec.get("missing_streak", 0) + 1
        # 连续缺失 3 次认为被删除
        if rec["missing_streak"] >= 3:
            rec["deleted"] = True
            rec["last_seen"] = now_iso
            # 构造虚拟 Tweet 用于通知
            t = Tweet(
                id=tid,
                text=rec.get("text", "(内容已存档)"),
                url=rec.get("url", ""),
                images=rec.get("images", []),
                videos=rec.get("videos", []),
                timestamp=rec.get("last_seen"),
                is_retweet=False,
            )
            notifications.append((t, "deleted"))
        state[tid] = rec

    # 按 ID 排序，避免乱序
    notifications.sort(key=lambda x: int(x[0].id) if x[0].id else 0)

    # 发送通知
    sent = 0
    for t, status in notifications:
        print(f"通知 {status}: {t.id}")
        header = {
            "new": "🆕 新推文",
            "edited": "✏️ 推文已编辑",
            "deleted": "❌ 推文可能已删除",
        }.get(status, "🆕 新推文")
        # 在文本前加状态头
        orig_text = t.text
        t.text = f"{header}\n\n{orig_text}"
        if notify(t):
            sent += 1
        # 写存档
        write_archive(t, status, now_iso)
        # 更新 last_tweet_id 文件
        save_last_id(t.id)
        time.sleep(1)

    # 保存状态
    save_state(state)

    print(f"发送完成: {sent}/{len(notifications)}")
    return 0


def main() -> int:
    return check_and_send()


if __name__ == "__main__":
    sys.exit(main())
