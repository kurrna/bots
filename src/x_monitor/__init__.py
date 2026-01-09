"""X/Twitter 推文监控模块。

通过 RSSHub 获取指定用户最新推文，转发到 Telegram。
"""

from .models import Tweet
from .config import Config
from .feed import fetch_feed, parse_feed
from .telegram import TelegramBot, notify_tweet
from .state import StateManager
from .main import main, cli_main

__all__ = [
    "Tweet",
    "Config", 
    "fetch_feed",
    "parse_feed",
    "TelegramBot",
    "notify_tweet",
    "StateManager",
    "main",
    "cli_main",
]
