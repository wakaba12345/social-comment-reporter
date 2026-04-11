import re
from urllib.parse import urlparse, parse_qs


class UnsupportedPlatformError(Exception):
    pass


def parse_url(url: str) -> tuple[str, str]:
    """
    Parse a social media URL and return (platform, post_id).
    Raises UnsupportedPlatformError if the URL cannot be recognized.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")
    path = parsed.path
    query = parse_qs(parsed.query)

    # Facebook
    if "facebook.com" in domain:
        # https://www.facebook.com/permalink.php?story_fbid=123&id=456
        if "permalink.php" in path:
            story_fbid = query.get("story_fbid", [None])[0]
            if story_fbid:
                return ("facebook", story_fbid)
        # https://www.facebook.com/username/posts/123456789
        match = re.search(r"/posts/(\d+)", path)
        if match:
            return ("facebook", match.group(1))
        # https://www.facebook.com/photo/?fbid=123
        # https://www.facebook.com/photo.php?fbid=123
        fbid = query.get("fbid", [None])[0]
        if fbid:
            return ("facebook", fbid)
        # https://www.facebook.com/watch/?v=948795611051587
        v = query.get("v", [None])[0]
        if v and "/watch" in path:
            return ("facebook", v)
        # https://www.facebook.com/share/p/1AzY7PhTkS/
        # https://www.facebook.com/share/v/1CKPvY4omx/
        # https://www.facebook.com/share/18JieiNmf7/
        if "/share/" in path:
            match = re.search(r"/share/(?:(?:p|v|r)/)?([A-Za-z0-9_-]+)", path)
            if match:
                return ("facebook", match.group(1))
        # https://www.facebook.com/username/videos/948795611051587/
        match = re.search(r"/videos/(\d+)", path)
        if match:
            return ("facebook", match.group(1))
        # https://www.facebook.com/reel/1234567890
        match = re.search(r"/reel/(\d+)", path)
        if match:
            return ("facebook", match.group(1))

    # Threads
    elif "threads.net" in domain or "threads.com" in domain:
        # https://www.threads.net/@username/post/AbCdEfG
        # https://www.threads.net/username/post/AbCdEfG  (無 @)
        match = re.search(r"/@?[^/]+/post/([A-Za-z0-9_-]+)", path)
        if match:
            return ("threads", match.group(1))
        # https://www.threads.net/t/AbCdEfG  (短連結)
        match = re.search(r"/t/([A-Za-z0-9_-]+)", path)
        if match:
            return ("threads", match.group(1))

    # X / Twitter
    elif "x.com" in domain or "twitter.com" in domain:
        # https://x.com/username/status/1234567890
        match = re.search(r"/status/(\d+)", path)
        if match:
            return ("x", match.group(1))

    # Instagram
    elif "instagram.com" in domain:
        # https://www.instagram.com/p/AbCdEfG/
        match = re.search(r"/p/([A-Za-z0-9_-]+)", path)
        if match:
            return ("instagram", match.group(1))

    # YouTube
    elif "youtube.com" in domain or "youtu.be" in domain:
        # https://www.youtube.com/watch?v=dQw4w9WgXcQ
        v = query.get("v", [None])[0]
        if v:
            return ("youtube", v)
        # https://youtu.be/dQw4w9WgXcQ
        if "youtu.be" in domain:
            vid = path.strip("/")
            if vid:
                return ("youtube", vid)

    # Reddit
    elif "reddit.com" in domain:
        # https://www.reddit.com/r/taiwan/comments/abc123/title/
        match = re.search(r"/comments/([A-Za-z0-9]+)", path)
        if match:
            return ("reddit", match.group(1))

    # Dcard
    elif "dcard.tw" in domain:
        # https://www.dcard.tw/f/talk/p/123456
        match = re.search(r"/p/(\d+)", path)
        if match:
            return ("dcard", match.group(1))

    # PTT
    elif "ptt.cc" in domain:
        # https://www.ptt.cc/bbs/Gossiping/M.1234567890.A.123.html
        match = re.search(r"/bbs/[^/]+/([^/]+)\.html", path)
        if match:
            return ("ptt", match.group(1))

    raise UnsupportedPlatformError(f"不支援的平台或 URL 格式：{url}")
