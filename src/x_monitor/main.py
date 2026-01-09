"""X/Twitter 监控机器人主入口。"""

from __future__ import annotations

import logging
import sys
import time

from .config import Config
from .feed import fetch_feed, parse_feed
from .state import StateManager
from .telegram import TelegramBot, notify_tweet


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run(
    config: Config,
    state: StateManager,
    bot: TelegramBot,
) -> None:
    """执行一次检查。"""
    # 获取 Feed（失败时会抛出 RuntimeError）
    raw = fetch_feed(config.feed_url)
    
    # 解析推文
    tweets = parse_feed(raw)
    if not tweets:
        logger.info("未解析到推文")
        return
    
    logger.info(f"解析到 {len(tweets)} 条推文")
    
    # 处理状态变化
    notifications, _ = state.process_tweets(tweets)
    
    if not notifications:
        logger.info("没有需要通知的变化")
        return
    
    logger.info(f"检测到 {len(notifications)} 条变化")
    
    # 发送通知
    for tweet, status in notifications:
        logger.info(f"通知: [{status}] {tweet.id}")
        
        # 写入存档
        state.write_archive(tweet, status)
        
        # 发送 Telegram 通知
        notify_tweet(bot, tweet, config.twitter_user, status)
    
    # 保存状态
    state.save()
    
    # 更新最后处理 ID
    if tweets:
        state.save_last_id(tweets[0].id)


def main() -> None:
    """主函数。"""
    # 加载配置
    config = Config.from_env()
    config.validate()
    config.ensure_dirs()
    
    # 初始化状态管理
    state = StateManager(config)
    state.load()
    
    # 初始化 Telegram Bot
    bot = TelegramBot(config.bot_token, config.chat_id)
    
    # 执行检查
    run(config, state, bot)


def cli_main() -> None:
    """CLI 入口点。"""
    main()


if __name__ == "__main__":
    cli_main()
