import time
import requests
from models import PostData, Comment
from config import BYCRAWL_BASE_URL, RETRY_DELAYS
import config


class CrawlerError(Exception):
    pass


class PostNotFoundError(CrawlerError):
    pass


def _get(endpoint: str, params: dict | None = None) -> dict:
    """Make a GET request to byCrawl with retry on 429."""
    url = f"{BYCRAWL_BASE_URL}{endpoint}"
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"   ⏳ Rate limit，等待 {delay} 秒後重試（第 {attempt} 次）...")
            time.sleep(delay)
        resp = requests.get(url, headers={"x-api-key": config._get("BYCRAWL_API_KEY")}, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise PostNotFoundError("找不到貼文，請確認 URL 是否為公開貼文")
        if resp.status_code == 429:
            continue
        resp.raise_for_status()
    raise CrawlerError("已達最大重試次數，byCrawl API 持續回傳 429 Rate Limit")


# ---------------------------------------------------------------------------
# Platform-specific fetchers
# ---------------------------------------------------------------------------

def _fetch_facebook(post_id: str, original_url: str, max_comments: int) -> PostData:
    # Facebook uses URL-based params
    post = _get("/facebook/posts", params={"url": original_url})
    author = post.get("author", {}).get("name", "") or ""
    content = post.get("text", "") or ""
    published_at = post.get("createdAt", "") or ""
    likes = int(post.get("reactionCount", 0) or 0)
    shares = int(post.get("shareCount", 0) or 0)
    comments_count = int(post.get("commentCount", 0) or 0)

    # Fetch comments（分頁直到達到 max_comments）
    comments: list[Comment] = []
    cursor = None
    try:
        while len(comments) < max_comments:
            params = {"url": original_url}
            if cursor:
                params["cursor"] = cursor
            data = _get("/facebook/posts/comments", params=params)
            raw = data.get("comments", []) or []
            for c in raw:
                if len(comments) >= max_comments:
                    break
                comments.append(Comment(
                    author=c.get("authorName", "") or "",
                    content=c.get("text", "") or "",
                    likes=int(c.get("reactionCount", 0) or 0),
                    published_at=c.get("createdAt", "") or "",
                    is_reply=False,
                ))
                # 把巢狀回覆也加進來
                for reply in (c.get("replies", []) or []):
                    if len(comments) >= max_comments:
                        break
                    comments.append(Comment(
                        author=reply.get("authorName", "") or "",
                        content=reply.get("text", "") or "",
                        likes=int(reply.get("reactionCount", 0) or 0),
                        published_at=reply.get("createdAt", "") or "",
                        is_reply=True,
                    ))
            cursor = data.get("nextCursor")
            if not cursor or not raw:
                break  # 沒有下一頁了
    except PostNotFoundError:
        pass

    media = [{"type": m.get("type","image"), "url": m.get("url","")}
             for m in (post.get("media") or []) if m.get("url")]

    return PostData(
        platform="facebook",
        post_id=post_id,
        url=original_url,
        author=author,
        content=content,
        published_at=published_at,
        likes=likes,
        shares=shares,
        comments_count=comments_count,
        comments=comments,
        media=media,
    )


def _fetch_threads(post_id: str, original_url: str, max_comments: int) -> PostData:
    # post_id may be numeric ID or shortcode — both work
    post = _get(f"/threads/posts/{post_id}")
    user = post.get("user", {})
    author = user.get("username", "") or ""
    content = post.get("text", "") or ""
    published_at = post.get("createdAt", "") or ""
    stats = post.get("stats", {}) or {}
    likes = int(stats.get("likes", 0) or 0)
    shares = int(stats.get("reposts", 0) or 0)
    comments_count = int(stats.get("replies", 0) or 0)

    media = [{"type": m.get("type","image"), "url": m.get("url","")}
             for m in (post.get("media") or []) if m.get("url")]

    # Threads has no /comments endpoint — replies cannot be fetched
    return PostData(
        platform="threads",
        post_id=post_id,
        url=original_url,
        author=author,
        content=content,
        published_at=published_at,
        likes=likes,
        shares=shares,
        comments_count=comments_count,
        comments=[],
        media=media,
    )


def _fetch_x(post_id: str, original_url: str, max_comments: int) -> PostData:
    post = _get(f"/x/posts/{post_id}")
    user = post.get("user", {})
    author = user.get("username", "") or user.get("name", "") or ""
    content = post.get("text", "") or ""
    published_at = post.get("createdAt", "") or ""
    likes = int(post.get("likeCount", 0) or 0)
    shares = int(post.get("retweetCount", 0) or 0)
    comments_count = int(post.get("replyCount", 0) or 0)

    # Fetch replies via search（每次最多 15 則，分頁到 max_comments）
    comments: list[Comment] = []
    cursor = None
    try:
        while len(comments) < max_comments:
            params = {"q": f"conversation_id:{post_id}", "count": 15, "product": "Latest"}
            if cursor:
                params["cursor"] = cursor
            data = _get("/x/posts/search", params=params)
            tweets = data.get("tweets", []) or []
            for t in tweets:
                if len(comments) >= max_comments:
                    break
                if not t.get("isReply", False):
                    continue
                tu = t.get("user", {})
                comments.append(Comment(
                    author=tu.get("username", "") or tu.get("name", "") or "",
                    content=t.get("text", "") or "",
                    likes=int(t.get("likeCount", 0) or 0),
                    published_at=t.get("createdAt", "") or "",
                    is_reply=True,
                ))
            cursor = data.get("next_cursor") or data.get("nextCursor")
            if not cursor or not tweets:
                break
    except (PostNotFoundError, requests.HTTPError):
        pass

    media = [{"type": m.get("type","image"), "url": m.get("url","")}
             for m in (post.get("media") or []) if m.get("url")]

    return PostData(
        platform="x",
        post_id=post_id,
        url=original_url,
        author=author,
        content=content,
        published_at=published_at,
        likes=likes,
        shares=shares,
        comments_count=comments_count,
        comments=comments,
        media=media,
    )


# ---------------------------------------------------------------------------
# Generic fallback for other platforms
# ---------------------------------------------------------------------------

def _fetch_generic(platform: str, post_id: str, original_url: str, max_comments: int) -> PostData:
    post = _get(f"/{platform}/posts/{post_id}")
    author_raw = post.get("author", {})
    author = author_raw.get("name", "") if isinstance(author_raw, dict) else str(author_raw)
    content = post.get("text") or post.get("content") or post.get("message") or ""
    published_at = post.get("createdAt") or post.get("published_at") or ""
    likes = int(post.get("likeCount") or post.get("reactionCount") or 0)
    shares = int(post.get("shareCount") or post.get("retweetCount") or 0)
    comments_count = int(post.get("commentCount") or post.get("replyCount") or 0)

    # Try comments endpoint
    comments: list[Comment] = []
    try:
        data = _get(f"/{platform}/posts/{post_id}/comments")
        raw = data.get("comments") or data.get("data") or (data if isinstance(data, list) else [])
        for c in raw[:max_comments]:
            a = c.get("author", {})
            comments.append(Comment(
                author=a.get("name", "") if isinstance(a, dict) else str(a),
                content=c.get("text") or c.get("content") or "",
                likes=int(c.get("likeCount") or c.get("likes") or 0),
                published_at=c.get("createdAt") or c.get("published_at") or "",
                is_reply=c.get("isReply", False),
            ))
    except (PostNotFoundError, requests.HTTPError):
        pass

    return PostData(
        platform=platform,
        post_id=post_id,
        url=original_url,
        author=author,
        content=content,
        published_at=published_at,
        likes=likes,
        shares=shares,
        comments_count=comments_count,
        comments=comments,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_FETCHERS = {
    "facebook": _fetch_facebook,
    "threads": _fetch_threads,
    "x": _fetch_x,
}


def fetch_post(platform: str, post_id: str, url: str, max_comments: int) -> PostData:
    """Fetch post content and comments from byCrawl API."""
    fetcher = _FETCHERS.get(platform, _fetch_generic)
    return fetcher(post_id, url, max_comments)
