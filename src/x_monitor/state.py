"""状态管理模块。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .models import Tweet
from .config import Config


class StateManager:
    """推文状态管理器。"""
    
    def __init__(self, config: Config):
        self.config = config
        self._state: Dict[str, Any] = {}
        self._loaded = False
    
    def load(self) -> None:
        """加载状态文件。"""
        if self.config.state_file.exists():
            try:
                content = self.config.state_file.read_text(encoding="utf-8")
                self._state = json.loads(content)
            except Exception as e:
                print(f"加载状态文件失败: {e}")
                self._state = {}
        else:
            self._state = {}
        self._loaded = True
    
    def save(self) -> None:
        """保存状态文件。"""
        self.config.ensure_dirs()
        content = json.dumps(self._state, ensure_ascii=False, indent=2)
        self.config.state_file.write_text(content, encoding="utf-8")
    
    def load_last_id(self) -> Optional[str]:
        """加载最后处理的推文 ID。"""
        if self.config.last_id_file.exists():
            content = self.config.last_id_file.read_text(encoding="utf-8").strip()
            return content or None
        return None
    
    def save_last_id(self, tweet_id: str) -> None:
        """保存最后处理的推文 ID。"""
        self.config.ensure_dirs()
        self.config.last_id_file.write_text(tweet_id, encoding="utf-8")
    
    @staticmethod
    def content_hash(tweet: Tweet) -> str:
        """计算推文内容哈希。"""
        base = "||".join([
            tweet.text,
            "|".join(tweet.images),
            "|".join(tweet.videos),
        ])
        return hashlib.sha256(base.encode("utf-8", errors="ignore")).hexdigest()
    
    def process_tweets(
        self,
        tweets: List[Tweet]
    ) -> Tuple[List[Tuple[Tweet, str]], Dict[str, Any]]:
        """
        处理推文列表，检测新增、编辑、删除。
        
        Args:
            tweets: 当前获取到的推文列表
        
        Returns:
            (需要通知的列表[(tweet, status)], 更新后的状态)
        """
        if not self._loaded:
            self.load()
        
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        notifications: List[Tuple[Tweet, str]] = []
        current_ids = set()
        
        # 处理当前推文
        for tweet in tweets:
            current_ids.add(tweet.id)
            h = self.content_hash(tweet)
            rec = self._state.get(tweet.id)
            
            if rec is None:
                # 新推文
                notifications.append((tweet, "new"))
                self._state[tweet.id] = {
                    "hash": h,
                    "text": tweet.text,
                    "images": tweet.images,
                    "videos": tweet.videos,
                    "url": tweet.url,
                    "first_seen": now_iso,
                    "last_seen": now_iso,
                    "missing_streak": 0,
                    "deleted": False,
                }
            else:
                # 已存在，检查编辑
                if rec.get("hash") != h:
                    notifications.append((tweet, "edited"))
                
                self._state[tweet.id].update({
                    "hash": h,
                    "text": tweet.text,
                    "images": tweet.images,
                    "videos": tweet.videos,
                    "url": tweet.url,
                    "last_seen": now_iso,
                    "missing_streak": 0,
                    "deleted": False,
                })
        
        # 检测删除的推文
        for tid, rec in list(self._state.items()):
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
                deleted_tweet = Tweet(
                    id=tid,
                    text=rec.get("text", "(内容已存档)"),
                    url=rec.get("url", ""),
                    images=rec.get("images", []),
                    videos=rec.get("videos", []),
                    timestamp=rec.get("last_seen"),
                    is_retweet=False,
                )
                notifications.append((deleted_tweet, "deleted"))
            
            self._state[tid] = rec
        
        # 按 ID 排序
        notifications.sort(key=lambda x: int(x[0].id) if x[0].id.isdigit() else 0)
        
        return notifications, self._state
    
    def write_archive(self, tweet: Tweet, status: str) -> None:
        """将推文保存到本地存档。"""
        self.config.ensure_dirs()
        
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        fname = self.config.archive_dir / f"{tweet.id}.md"
        
        lines = [
            f"# {status} {tweet.id}",
            "",
            f"时间: {now_iso}",
            f"链接: {tweet.url}",
            "",
            "## 正文",
            tweet.text,
            "",
        ]
        
        if tweet.quote_author or tweet.quote_text:
            lines.append("## 引用推文")
            if tweet.quote_author:
                lines.append(f"作者: {tweet.quote_author}")
            if tweet.quote_text:
                lines.append(tweet.quote_text)
            lines.append("")
        
        if tweet.images:
            lines.append("## 图片")
            lines.extend(tweet.images)
            lines.append("")
        
        if tweet.videos:
            lines.append("## 视频")
            lines.extend(tweet.videos)
            lines.append("")
        
        fname.write_text("\n".join(lines), encoding="utf-8")
