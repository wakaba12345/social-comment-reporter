import re
from models import Comment


_EMOJI_ONLY_RE = re.compile(
    r"^[\U0001F000-\U0001FFFF\U00002600-\U000027BF\s]+$", re.UNICODE
)
_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def _is_spam(comment: Comment) -> bool:
    text = comment.content.strip()
    if len(text) < 5:
        return True
    if _EMOJI_ONLY_RE.match(text):
        return True
    if _URL_ONLY_RE.match(text):
        return True
    return False


def preprocess(comments: list[Comment], max_comments: int) -> list[Comment]:
    """
    Clean, deduplicate, filter, and sort comments.
    Returns a list of up to max_comments top-quality comments.
    """
    # Deduplicate by exact content
    seen = set()
    unique = []
    for c in comments:
        key = c.content.strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    # Filter spam/low-quality
    filtered = [c for c in unique if not _is_spam(c)]

    # Sort by likes descending
    filtered.sort(key=lambda c: c.likes, reverse=True)

    # Truncate
    return filtered[:max_comments]
