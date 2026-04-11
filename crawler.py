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

_FB_TRACKING_PARAMS = {"mibextid", "rdid", "share_url", "sfnsn", "ref", "_rdr"}

def _resolve_facebook_url(url: str) -> str:
    """Follow Facebook share redirects to get the canonical post URL."""
    if "/share/" not in url:
        return url
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; bot/1.0)"},
            allow_redirects=True,
            timeout=15,
        )
        from urllib.parse import urlparse, urlencode, parse_qs
        p = urlparse(resp.url)
        # Keep functional params (fbid, set, type…), drop tracking-only ones
        clean_qs = {k: v for k, v in parse_qs(p.query).items()
                    if k not in _FB_TRACKING_PARAMS}
        clean_query = urlencode(clean_qs, doseq=True)
        return p._replace(query=clean_query, fragment="").geturl()
    except Exception:
        return url


def _fetch_facebook(post_id: str, original_url: str, max_comments: int) -> PostData:
    # Resolve share/redirect URLs to canonical post URL
    resolved_url = _resolve_facebook_url(original_url)

    # Fetch post metadata
    items = _apify_run(
        "apify/facebook-posts-scraper",
        {"startUrls": [{"url": resolved_url}], "resultsLimit": 1},
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

        # ── Post text ────────────────────────────────────────────────────────
        # Regular post: container_story.message.text
        # Video post: previewTitle / previewDescription
        content = (
            (post.get("container_story") or {}).get("message", {}).get("text", "")
            or post.get("previewTitle", "")
            or post.get("previewDescription", "")
            or ""
        )

        # ── Author ───────────────────────────────────────────────────────────
        # Regular post: container_story.url → extract username
        # Video post: pageName or permalink_url
        container_url = (post.get("container_story") or {}).get("url", "") or ""
        permalink = post.get("permalink_url", "") or post.get("facebookUrl", "") or resolved_url
        for source_url in [container_url, permalink, resolved_url]:
            if source_url:
                m = re.match(r"https://www\.facebook\.com/([^/?#]+)", source_url)
                if m and m.group(1) not in ("photo", "video", "videos", "watch", "share"):
                    author = m.group(1)
                    break

        # ── Timestamp ────────────────────────────────────────────────────────
        # Regular post: created_time (unix int)
        # Video post: publish_time (unix int)
        ts = post.get("created_time") or post.get("publish_time") or 0
        if ts:
            try:
                dt = datetime.datetime.utcfromtimestamp(int(ts))
                published_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass

        # ── Reactions ────────────────────────────────────────────────────────
        # Regular post: feedback.unified_reactors.count
        # Video post: reaction_count.count
        likes = int(
            (post.get("feedback") or {}).get("unified_reactors", {}).get("count", 0)
            or (post.get("reaction_count") or {}).get("count", 0)
            or 0
        )

        # ── Comment count ────────────────────────────────────────────────────
        comments_count = int(post.get("total_comment_count", 0) or 0)

        # ── Media ────────────────────────────────────────────────────────────
        image_uri = (post.get("image") or {}).get("uri", "") or ""
        thumb = (post.get("preferred_thumbnail") or {}).get("image", {}).get("uri", "") or ""
        cover = image_uri or thumb
        if cover:
            media = [{"type": "image", "url": cover}]

    # Fetch comments via facebook-comments-scraper (supports nested replies)
    # Use a generous timeout: 500 comments can take 3-4 minutes on Apify
    comments_timeout = max(180, min(max_comments * 1, 300))
    try:
        comment_items = _apify_run(
            "apify/facebook-comments-scraper",
            {"startUrls": [{"url": resolved_url}], "resultsLimit": max_comments},
            timeout=comments_timeout,
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
    except Exception as e:
        print(f"[crawler] comments fetch error: {e}")
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
    # Fetch post
    post = _get_x(f"/threads/posts/{post_id}")
    user = post.get("user", {})
    author = user.get("username", "") or user.get("name", "") or ""
    content = post.get("text", "") or ""
    published_at = post.get("createdAt", "") or ""
    stats = post.get("stats", {})
    likes = int(stats.get("likes", 0) or 0)
    shares = int(stats.get("reposts", 0) or 0)
    comments_count = int(stats.get("replies", 0) or 0)

    # Fetch replies — byCrawl primary, Apify fallback if empty
    comments: list[Comment] = []
    try:
        data = _get_x(f"/threads/posts/{post_id}/replies")
        replies = data.get("replies", []) or []
        for r in replies[:max_comments]:
            text = r.get("text", "") or ""
            if not text.strip():
                continue
            ru = r.get("user", {})
            r_stats = r.get("stats", {})
            comments.append(Comment(
                author=ru.get("username", "") or ru.get("name", "") or "",
                content=text,
                likes=int(r_stats.get("likes", 0) or 0),
                published_at=r.get("createdAt", "") or "",
                is_reply=r.get("isReply", False),
            ))
    except Exception as e:
        print(f"[crawler] threads replies error: {e}")

    # Apify fallback when byCrawl returns nothing
    if not comments:
        print("[crawler] threads byCrawl empty, trying Apify fallback...")
        try:
            items = _apify_run(
                "7xFgGDhba8W5ZvOke",
                {"startUrls": [{"url": original_url}], "resultsLimit": 20},
                timeout=60,
            )
            for item in items:
                for r in (item.get("replies") or [])[:max_comments]:
                    text = r.get("text", "") or ""
                    if not text.strip():
                        continue
                    comments.append(Comment(
                        author=r.get("username", "") or "",
                        content=text,
                        likes=int(r.get("like_count", 0) or 0),
                        published_at="",
                        is_reply=True,
                    ))
                if len(comments) >= max_comments:
                    break
            print(f"[crawler] Apify fallback got {len(comments)} replies")
        except Exception as e:
            print(f"[crawler] Apify fallback error: {e}")

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
        comments=comments,
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
