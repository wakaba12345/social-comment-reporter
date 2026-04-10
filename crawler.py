import time
import re
import datetime
import requests
from models import PostData, Comment
import config


class CrawlerError(Exception):
    pass


class PostNotFoundError(CrawlerError):
    pass


def _apify_run(actor: str, payload: dict, timeout: int = 120) -> list:
    """Run an Apify actor synchronously and return dataset items."""
    token = config._get("APIFY_API_TOKEN")
    actor_slug = actor.replace("/", "~")
    resp = requests.post(
        f"https://api.apify.com/v2/acts/{actor_slug}/run-sync-get-dataset-items"
        f"?token={token}&timeout={timeout}",
        json=payload,
        timeout=timeout + 30,
    )
    if resp.status_code == 404:
        raise PostNotFoundError("找不到貼文，請確認 URL 是否為公開貼文")
    if resp.status_code not in (200, 201):
        raise CrawlerError(f"Apify 回傳錯誤：{resp.status_code} {resp.text[:200]}")
    return resp.json()


# ---------------------------------------------------------------------------
# Facebook
# ---------------------------------------------------------------------------

def _fetch_facebook(post_id: str, original_url: str, max_comments: int) -> PostData:
    # Fetch post metadata
    items = _apify_run(
        "apify/facebook-posts-scraper",
        {"startUrls": [{"url": original_url}], "resultsLimit": 1},
        timeout=120,
    )

    author = ""
    content = ""
    published_at = ""
    likes = 0
    shares = 0
    comments_count = 0
    media = []

    if items:
        post = items[0]
        # Post text
        content = (
            post.get("container_story", {}).get("message", {}).get("text", "")
            or ""
        )
        # Author: extract username/pagename from the resolved post URL
        container_url = post.get("container_story", {}).get("url", "") or ""
        if container_url:
            m = re.match(r"https://www\.facebook\.com/([^/?#]+)", container_url)
            if m:
                author = m.group(1)
        # Timestamp
        created_time = post.get("created_time", 0) or 0
        if created_time:
            dt = datetime.datetime.utcfromtimestamp(created_time)
            published_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Reactions
        likes = int(
            post.get("feedback", {}).get("unified_reactors", {}).get("count", 0) or 0
        )
        # Cover image
        image_uri = post.get("image", {}).get("uri", "") or ""
        if image_uri:
            media = [{"type": "image", "url": image_uri}]

    # Fetch comments via facebook-comments-scraper (supports nested replies)
    try:
        comment_items = _apify_run(
            "apify/facebook-comments-scraper",
            {"startUrls": [{"url": original_url}], "resultsLimit": max_comments},
            timeout=120,
        )
        comments = []
        for c in comment_items:
            text = c.get("text", "") or ""
            if not text.strip():
                continue
            try:
                c_likes = int(c.get("likesCount") or 0)
            except (ValueError, TypeError):
                c_likes = 0
            depth = c.get("threadingDepth", 0)
            comments.append(Comment(
                author=c.get("profileName", "") or "",
                content=text,
                likes=c_likes,
                published_at=c.get("date", "") or "",
                is_reply=depth > 0,
            ))
        comments_count = len(comments)
    except Exception:
        comments = []

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


# ---------------------------------------------------------------------------
# Threads — no comments API available
# ---------------------------------------------------------------------------

def _fetch_threads(post_id: str, original_url: str, max_comments: int) -> PostData:
    """Threads has no public comments API; returns post stub with empty comments."""
    return PostData(
        platform="threads",
        post_id=post_id,
        url=original_url,
        author="",
        content="（Threads 不提供留言抓取，僅顯示貼文網址）",
        published_at="",
        likes=0,
        shares=0,
        comments_count=0,
        comments=[],
        media=[],
    )


# ---------------------------------------------------------------------------
# X / Twitter
# ---------------------------------------------------------------------------

def _get_x(endpoint: str, params: dict | None = None) -> dict:
    """Make a GET request to byCrawl X endpoints (still used for X)."""
    url = f"https://api.bycrawl.com{endpoint}"
    for attempt, delay in enumerate([0] + [5, 15, 30]):
        if delay:
            print(f"   Rate limit, retrying in {delay}s (attempt {attempt})...")
            time.sleep(delay)
        resp = requests.get(
            url,
            headers={"x-api-key": config._get("BYCRAWL_API_KEY")},
            params=params,
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise PostNotFoundError("找不到貼文，請確認 URL 是否為公開貼文")
        if resp.status_code == 429:
            continue
        resp.raise_for_status()
    raise CrawlerError("byCrawl API 持續回傳 429 Rate Limit")


def _fetch_x(post_id: str, original_url: str, max_comments: int) -> PostData:
    post = _get_x(f"/x/posts/{post_id}")
    user = post.get("user", {})
    author = user.get("username", "") or user.get("name", "") or ""
    content = post.get("text", "") or ""
    published_at = post.get("createdAt", "") or ""
    likes = int(post.get("likeCount", 0) or 0)
    shares = int(post.get("retweetCount", 0) or 0)
    comments_count = int(post.get("replyCount", 0) or 0)

    comments: list[Comment] = []
    cursor = None
    try:
        while len(comments) < max_comments:
            params = {"q": f"conversation_id:{post_id}", "count": 15, "product": "Latest"}
            if cursor:
                params["cursor"] = cursor
            data = _get_x("/x/posts/search", params=params)
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
    except Exception:
        pass

    media = [{"type": m.get("type", "image"), "url": m.get("url", "")}
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
# Generic fallback for other platforms (uses byCrawl)
# ---------------------------------------------------------------------------

def _fetch_generic(platform: str, post_id: str, original_url: str, max_comments: int) -> PostData:
    post = _get_x(f"/{platform}/posts/{post_id}")
    author_raw = post.get("author", {})
    author = author_raw.get("name", "") if isinstance(author_raw, dict) else str(author_raw)
    content = post.get("text") or post.get("content") or post.get("message") or ""
    published_at = post.get("createdAt") or post.get("published_at") or ""
    likes = int(post.get("likeCount") or post.get("reactionCount") or 0)
    shares = int(post.get("shareCount") or post.get("retweetCount") or 0)
    comments_count = int(post.get("commentCount") or post.get("replyCount") or 0)

    comments: list[Comment] = []
    try:
        data = _get_x(f"/{platform}/posts/{post_id}/comments")
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
    except Exception:
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
    """Fetch post content and comments."""
    fetcher = _FETCHERS.get(platform, _fetch_generic)
    return fetcher(post_id, url, max_comments)
