import sys
import os
from datetime import datetime

# Windows 終端機強制 UTF-8 輸出
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import click

from url_parser import parse_url, UnsupportedPlatformError
from crawler import fetch_post, PostNotFoundError, CrawlerError
from preprocessor import preprocess
from reporter import generate_report
from config import DEFAULT_MAX_COMMENTS, DEFAULT_OUTPUT_DIR, DEFAULT_MODEL


PLATFORM_ZH = {
    "facebook": "Facebook",
    "threads": "Threads",
    "x": "X",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "reddit": "Reddit",
    "dcard": "Dcard",
    "ptt": "PTT",
}


def _infer_topic(posts) -> str:
    for post in posts:
        if post.content:
            snippet = post.content[:40].replace("\n", " ")
            return f"{snippet}..."
    return "社群輿論分析"


def _save_report(content: str, post, output_dir: str, model: str, source_urls: list[str]) -> str:
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{post.platform}_{post.post_id}.md"
    filepath = os.path.join(output_dir, filename)

    urls_yaml = "\n".join(f"  - {u}" for u in source_urls)
    frontmatter = f"""---
generated_at: {now.isoformat()}
source_urls:
{urls_yaml}
platform: {post.platform}
post_id: "{post.post_id}"
comments_scraped: {len(post.comments)}
model: {model}
---

"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + content)

    return filepath


@click.command()
@click.option("--url", "urls", multiple=True, required=True, help="社群貼文 URL（可重複使用多次）")
@click.option("--topic", default=None, help="報導主題描述（可選，預設從貼文內容自動推斷）")
@click.option("--max-comments", default=DEFAULT_MAX_COMMENTS, show_default=True, help="每篇貼文最多擷取幾則留言")
@click.option("--output", default=DEFAULT_OUTPUT_DIR, show_default=True, help="報導 Markdown 輸出目錄")
@click.option("--no-report", is_flag=True, default=False, help="只擷取留言，不生成報導")
@click.option("--model", default=DEFAULT_MODEL, show_default=True, help="使用的 Claude 模型")
@click.option("--lang", default="zh-TW", hidden=True)
def main(urls, topic, max_comments, output, no_report, model, lang):
    """社群留言擷取 x 風傳媒報導生成器

    輸入社群貼文 URL，自動擷取留言並生成風傳媒風格報導草稿。
    """
    posts = []

    for url in urls:
        # --- Parse URL ---
        try:
            platform, post_id = parse_url(url)
        except UnsupportedPlatformError as e:
            click.echo(f"[!] {e}")
            continue

        # --- Fetch from byCrawl ---
        click.echo(f"\n[*] 正在擷取：{PLATFORM_ZH.get(platform, platform)} 貼文 ({post_id})...")
        try:
            post = fetch_post(platform, post_id, url, max_comments)
        except PostNotFoundError as e:
            click.echo(f"[x] {e}")
            continue
        except CrawlerError as e:
            click.echo(f"[x] 擷取失敗：{e}")
            continue
        except Exception as e:
            click.echo(f"[x] 網路錯誤：{e}\n   請確認 BYCRAWL_API_KEY 與網路連線是否正常。")
            continue

        # --- Preprocess comments ---
        post.comments = preprocess(post.comments, max_comments)

        click.echo(f"[v] 成功擷取：{PLATFORM_ZH.get(platform, platform)} 貼文 (post_id: {post_id})")
        click.echo(f"    作者：{post.author}")
        if platform == "threads":
            click.echo(f"    留言數：{post.comments_count} 則（Threads 不支援留言擷取，僅使用貼文內容生成報導）")
        elif platform == "x" and not post.comments:
            click.echo(f"    留言數：{post.comments_count} 則（未能從搜尋取得回覆，將以貼文內容生成報導）")
        else:
            click.echo(f"    留言數：{post.comments_count} 則，已擷取前 {len(post.comments)} 則")

        posts.append(post)

    if not posts:
        click.echo("\n[x] 沒有成功擷取任何貼文，程式結束。")
        sys.exit(1)

    if no_report:
        click.echo("\n[v] 已完成留言擷取（--no-report 模式，不生成報導）。")
        return

    # --- Infer topic ---
    if not topic:
        topic = _infer_topic(posts)
        click.echo(f"\n[*] 自動推斷主題：{topic}")

    primary = posts[0]
    source_urls = [p.url for p in posts]

    click.echo("\n[*] 正在生成報導...\n")
    try:
        report = generate_report(primary, topic, model)
    except Exception as e:
        click.echo(f"[x] Claude API 錯誤：{e}")
        click.echo("    提示：可改用 --no-report 先輸出留言資料。")
        sys.exit(1)

    # --- Display preview ---
    divider = "=" * 50
    click.echo(divider)
    click.echo("【報導預覽】")
    click.echo(divider)
    click.echo(report)
    click.echo(divider)

    # --- Save to file ---
    try:
        filepath = _save_report(report, primary, output, model, source_urls)
        click.echo(f"\n[v] 已儲存：{filepath}")
    except Exception as e:
        click.echo(f"\n[!] 儲存失敗：{e}")


if __name__ == "__main__":
    main()
