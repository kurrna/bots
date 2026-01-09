"""Telegram 消息发送模块。"""

from __future__ import annotations

from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

import requests

from .models import Tweet


class TelegramBot:
    """Telegram Bot 封装。"""
    
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    def send_text(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_preview: bool = False
    ) -> bool:
        """发送文本消息。"""
        if not self.token or not self.chat_id:
            print("未配置 Telegram Token 或 Chat ID")
            return False
        
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        
        try:
            r = requests.post(url, json=payload, timeout=15)
            result = r.json()
            if not result.get("ok"):
                print(f"发送文本失败: {r.text}")
                return False
            return True
        except Exception as e:
            print(f"发送文本异常: {e}")
            return False
    
    def send_photo(self, photo_url: str, caption: str = "") -> bool:
        """发送单张图片。"""
        if not self.token or not self.chat_id:
            return False
        
        url = f"{self.base_url}/sendPhoto"
        payload = {
            "chat_id": self.chat_id,
            "photo": photo_url,
            "caption": caption[:1024] if caption else "",
        }
        
        try:
            r = requests.post(url, json=payload, timeout=30)
            result = r.json()
            if not result.get("ok"):
                print(f"发送图片失败: {r.text}")
                return False
            return True
        except Exception as e:
            print(f"发送图片异常: {e}")
            return False
    
    def send_media_group(self, images: List[str], caption: str = "") -> bool:
        """发送图片组（最多 10 张）。"""
        if not images or not self.token or not self.chat_id:
            return False
        
        url = f"{self.base_url}/sendMediaGroup"
        media = []
        
        for i, img_url in enumerate(images[:10]):
            item = {"type": "photo", "media": img_url}
            if i == 0 and caption:
                item["caption"] = caption[:1024]
            media.append(item)
        
        payload = {"chat_id": self.chat_id, "media": media}
        
        try:
            r = requests.post(url, json=payload, timeout=60)
            result = r.json()
            if not result.get("ok"):
                print(f"发送图片组失败: {r.text}")
                return False
            return True
        except Exception as e:
            print(f"发送图片组异常: {e}")
            return False


# ============================================================
# 消息格式化
# ============================================================

def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符。"""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def format_jst_now() -> str:
    """获取当前 JST 时间字符串。"""
    jst = ZoneInfo("Asia/Tokyo")
    now = datetime.now(jst)
    return now.strftime("%Y/%m/%d %H:%M:%S JST")


def format_tweet_message(tweet: Tweet, username: str, status_header: str = "") -> str:
    """
    格式化推文为 Telegram HTML 消息。
    
    Args:
        tweet: 推文数据
        username: 用户名
        status_header: 状态标题（如 "🆕 新推文"）
    
    Returns:
        格式化后的 HTML 消息
    """
    lines = []
    
    # 状态标题
    if status_header:
        lines.append(status_header)
        lines.append("")
    
    # 用户标题
    if tweet.is_retweet:
        lines.append(f"🔁 <b>@{_escape_html(username)}</b> 转推")
    else:
        lines.append(f"🐦 <b>@{_escape_html(username)}</b> 发布新推文")
    lines.append("")
    
    # 正文
    lines.append(_escape_html(tweet.text))
    
    # 引用推文
    if tweet.quote_author or tweet.quote_text:
        lines.append("")
        lines.append("┌──── 引用 ────")
        if tweet.quote_author:
            lines.append(f"│ <b>{_escape_html(tweet.quote_author)}</b>")
        if tweet.quote_text:
            for line in tweet.quote_text.split('\n'):
                if line.strip():
                    lines.append(f"│ {_escape_html(line)}")
        lines.append("└─────────────")
    
    lines.append("")
    lines.append(f'🔗 <a href="{tweet.url}">查看原推</a>')
    
    # 视频链接
    if tweet.videos:
        for v in tweet.videos:
            lines.append(f'🎞 <a href="{v}">视频链接</a>')
    
    return "\n".join(lines)


def notify_tweet(
    bot: TelegramBot,
    tweet: Tweet,
    username: str,
    status: str = "new"
) -> bool:
    """
    发送推文通知。
    
    Args:
        bot: Telegram Bot 实例
        tweet: 推文数据
        username: 用户名
        status: 状态类型 (new/edited/deleted)
    
    Returns:
        是否发送成功
    """
    # 状态标题映射
    headers = {
        "new": "🆕 新推文",
        "edited": "✏️ 推文已编辑",
        "deleted": "❌ 推文可能已删除",
    }
    header = headers.get(status, "🆕 新推文")
    
    # 格式化消息
    msg = format_tweet_message(tweet, username, header)
    
    # 发送文本
    ok = bot.send_text(msg)
    
    # 转推或有视频：只发文本
    if tweet.is_retweet or tweet.videos:
        return ok
    
    # 发送图片
    if tweet.images:
        if len(tweet.images) == 1:
            bot.send_photo(tweet.images[0])
        else:
            bot.send_media_group(tweet.images)
    
    return ok
