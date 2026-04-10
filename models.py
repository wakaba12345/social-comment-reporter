from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Comment:
    author: str
    content: str
    likes: int
    published_at: str
    is_reply: bool = False


@dataclass
class PostData:
    platform: str
    post_id: str
    url: str
    author: str
    content: str
    published_at: str
    likes: int
    shares: int
    comments_count: int
    comments: list[Comment] = field(default_factory=list)
    media: list[dict] = field(default_factory=list)  # [{"type": "image"|"video", "url": "..."}]
