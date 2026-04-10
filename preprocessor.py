import re
from models import Comment

_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def _is_spam(comment: Comment) -> bool:
    text = comment.content.strip()
    if not text:
        return True
    if _URL_ONLY_RE.match(text):
        return True
    return False


def preprocess(comments: list[Comment], max_comments: int) -> list[Comment]:
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

    return filtered[:max_comments]
