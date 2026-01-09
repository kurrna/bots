"""数据模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Tweet:
    """推文数据结构。"""
    
    id: str                                      # 推文 ID
    text: str                                    # 正文内容
    url: str                                     # 推文链接
    images: List[str] = field(default_factory=list)   # 图片 URL 列表
    videos: List[str] = field(default_factory=list)   # 视频 URL 列表
    timestamp: Optional[str] = None              # 发布时间
    is_retweet: bool = False                     # 是否为转推
    quote_text: Optional[str] = None             # 引用推文内容
    quote_author: Optional[str] = None           # 引用推文作者
    author_name: Optional[str] = None            # 推文作者名
    author_avatar: Optional[str] = None          # 作者头像
