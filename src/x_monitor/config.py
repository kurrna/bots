"""配置加载模块。"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Config:
    """应用配置。"""
    
    # 目标用户名（不含 @）
    goal_username: str
    # RSSHub 链接
    rss_url: str
    # RSSHub 参数
    rss_params: str
    # Telegram Bot Token
    tg_token: str
    # Telegram Chat ID
    tg_chat_id: str
    # 数据目录
    data_dir: pathlib.Path
    # 存档目录
    archive_dir: pathlib.Path
    # 状态文件
    state_file: pathlib.Path
    # 最后推文 ID 文件
    last_id_file: pathlib.Path
    # 轮询间隔（秒）
    poll_interval: int = 300
    
    # 别名属性，保持兼容
    @property
    def twitter_user(self) -> str:
        return self.goal_username
    
    @property
    def feed_url(self) -> str:
        if self.rss_params[0] != "/":
            self.rss_params = "/" + self.rss_params
        return self.rss_url + self.rss_params
    
    @property
    def bot_token(self) -> str:
        return self.tg_token
    
    @property
    def chat_id(self) -> str:
        return self.tg_chat_id
    
    @classmethod
    def from_env(cls, root: Optional[pathlib.Path] = None) -> "Config":
        """从环境变量加载配置。"""
        if root is None:
            root = pathlib.Path(__file__).resolve().parents[2]
        
        # 加载 .env 文件
        env_file = root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        
        data_dir = root / "messages" / "x_monitor"
        
        return cls(
            goal_username=os.getenv("GOAL_USERNAME", ""),
            rss_url=os.getenv("X_RSS_URL", ""),
            rss_params=os.getenv("X_RSS_PARAMS", ""),
            tg_token=os.getenv("TG_TOKEN_2", ""),
            tg_chat_id=os.getenv("TG_CHAT_ID", ""),
            data_dir=data_dir,
            archive_dir=data_dir / "archive",
            state_file=data_dir / "state.json",
            last_id_file=data_dir / "last_tweet_id.txt",
            poll_interval=int(os.getenv("POLL_INTERVAL", "300")),
        )
    
    def ensure_dirs(self) -> None:
        """确保目录存在。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> list[str]:
        """验证配置，返回错误列表。"""
        errors = []
        if not self.rss_url:
            errors.append("未配置 X_RSS_URL")
        if not self.tg_token:
            errors.append("未配置 TG_TOKEN_2")
        if not self.tg_chat_id:
            errors.append("未配置 TG_CHAT_ID")
        return errors
