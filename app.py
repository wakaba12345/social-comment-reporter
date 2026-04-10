import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(override=True)

import streamlit as st
from url_parser import parse_url, UnsupportedPlatformError
from crawler import fetch_post, PostNotFoundError, CrawlerError
from preprocessor import preprocess
from reporter import generate_report

MAX_COMMENTS = 500  # 盡量抓最多

PLATFORM_LABEL = {
    "facebook": "Facebook", "threads": "Threads",
    "x": "X", "instagram": "Instagram",
    "youtube": "YouTube", "reddit": "Reddit",
    "dcard": "Dcard", "ptt": "PTT",
}

# ── 頁面設定 ────────────────────────────────────────────────
st.set_page_config(
    page_title="社群留言報導生成器",
    page_icon="📰",
    layout="wide",
)

st.title("📰 社群留言報導生成器")
st.caption("輸入社群貼文網址，自動擷取留言並生成風傳媒風格報導草稿")

# ── 輸入區 ───────────────────────────────────────────────────
with st.form("input_form"):
    urls_input = st.text_area(
        "貼文網址（每行一個，可輸入多個）",
        placeholder="https://www.facebook.com/xxx/posts/xxx\nhttps://x.com/username/status/xxx",
        height=100,
    )
    topic = st.text_input(
        "報導主題（選填，留空則自動推斷）",
        placeholder="例：捷運票價漲價爭議",
    )
    model = st.selectbox(
        "Claude 模型",
        ["claude-sonnet-4-6", "claude-opus-4-6"],
        index=0,
    )
    run_btn = st.form_submit_button("開始生成報導", type="primary", use_container_width=True)

# ── 執行 ─────────────────────────────────────────────────────
if run_btn:
    urls = [u.strip() for u in urls_input.strip().splitlines() if u.strip()]
    if not urls:
        st.warning("請至少輸入一個貼文網址。")
        st.stop()

    posts = []
    for url in urls:
        try:
            platform, post_id = parse_url(url)
        except UnsupportedPlatformError:
            st.error(f"不支援的網址格式：{url}")
            continue

        label = PLATFORM_LABEL.get(platform, platform)
        with st.spinner(f"正在擷取 {label} 貼文與留言..."):
            try:
                post = fetch_post(platform, post_id, url, MAX_COMMENTS)
            except PostNotFoundError as e:
                st.error(str(e))
                continue
            except CrawlerError as e:
                st.error(f"擷取失敗：{e}")
                continue
            except Exception as e:
                st.error(f"網路錯誤：{e}")
                continue

        post.comments = preprocess(post.comments, MAX_COMMENTS)

        if platform == "threads":
            note = f"{post.comments_count} 則留言（Threads 不提供留言擷取）"
        elif platform == "x" and not post.comments:
            note = f"{post.comments_count} 則留言（未能取得回覆）"
        else:
            note = f"已擷取 {len(post.comments)} / {post.comments_count} 則留言（按讚數排序）"

        st.success(f"**{label}** | 作者：{post.author or '（未知）'} | {note}")
        posts.append(post)

    if not posts:
        st.stop()

    # 自動推斷主題
    if not topic:
        for p in posts:
            if p.content:
                topic = p.content[:40].replace("\n", " ") + "..."
                break
        if not topic:
            topic = "社群輿論分析"
        st.info(f"自動推斷主題：**{topic}**")

    primary = posts[0]

    # 生成報導
    with st.spinner("正在生成報導，請稍候..."):
        try:
            report = generate_report(primary, topic, model)
        except Exception as e:
            st.error(f"Claude API 錯誤：{e}")
            st.stop()

    # 儲存檔案
    os.makedirs("./reports", exist_ok=True)
    now = datetime.now()
    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{primary.platform}_{primary.post_id}.md"
    filepath = os.path.join("./reports", filename)
    source_urls_yaml = "\n".join(f"  - {p.url}" for p in posts)
    frontmatter = f"""---
generated_at: {now.isoformat()}
source_urls:
{source_urls_yaml}
platform: {primary.platform}
post_id: "{primary.post_id}"
comments_scraped: {len(primary.comments)}
model: {model}
---

"""
    full_content = frontmatter + report
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)

    # ── 比對版面：左原始資料，右報導 ──────────────────────────
    st.divider()
    left, right = st.columns(2, gap="large")

    with left:
        st.subheader("原始資料")

        # 貼文內容
        with st.expander("貼文內容", expanded=True):
            st.markdown(f"**作者：** {primary.author or '（未知）'}")
            st.markdown(f"**發布：** {primary.published_at}")
            st.markdown(f"**互動：** {primary.likes} 讚 ｜ {primary.shares} 分享 ｜ {primary.comments_count} 留言")
            st.divider()
            st.write(primary.content or "（無貼文內容）")
            # 照片／影片
            if primary.media:
                for m in primary.media:
                    if m["type"] == "image":
                        try:
                            st.image(m["url"], use_container_width=True)
                        except Exception:
                            st.markdown(f"[圖片連結]({m['url']})")
                    elif m["type"] in ("video", "animated_gif"):
                        st.markdown(f"[影片連結]({m['url']})")

        # 留言列表
        st.markdown(f"**留言（{len(primary.comments)} 則，按讚數排序）**")
        if primary.comments:
            for i, c in enumerate(primary.comments, 1):
                reply_tag = " ↳" if c.is_reply else ""
                st.markdown(
                    f"`{i}.` **{c.likes} 讚**{reply_tag} &nbsp; {c.author}  \n{c.content}",
                    unsafe_allow_html=False,
                )
                if i < len(primary.comments):
                    st.divider()
        else:
            st.caption("無留言資料")

    with right:
        st.subheader("報導草稿")
        st.markdown(report)
        st.divider()

        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                label="下載 Markdown",
                data=full_content.encode("utf-8"),
                file_name=filename,
                mime="text/markdown",
                use_container_width=True,
            )
        with col_b:
            st.download_button(
                label="下載純文字",
                data=report.encode("utf-8"),
                file_name=filename.replace(".md", ".txt"),
                mime="text/plain",
                use_container_width=True,
            )
        st.caption(f"已儲存：{filepath}")
