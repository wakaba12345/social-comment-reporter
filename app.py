import sys
import os
import base64
import json
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(override=True)

import requests as http_requests
import streamlit as st
import streamlit.components.v1 as components
import extra_streamlit_components as stx
from url_parser import parse_url, UnsupportedPlatformError
from crawler import fetch_post, PostNotFoundError, CrawlerError
from preprocessor import preprocess
from reporter import generate_report
from config import ADMIN_API, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

_REDIRECT_URI = "https://social-comment-reporter-nxayfk9rwvwnovzsqe6gjg.streamlit.app/"

MAX_COMMENTS = 50
_COOKIE_KEY = "_sct"  # obscure session cookie name


def _decode_jwt_payload(credential: str) -> dict:
    """Decode Google JWT payload (no signature verification needed — server validates)."""
    try:
        payload_b64 = credential.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


def _exchange_token(credential: str, user: dict) -> tuple:
    """POST to ADMIN_API and return (storm_token, raw_response)."""
    try:
        resp = http_requests.post(
            f"{ADMIN_API}v1/loging",
            json={
                "email": user.get("email", ""),
                "name": user.get("name", ""),
                "token": credential,
                "refreshToken": "",
                "expiresIn": user.get("exp", 0),
                "avatar": user.get("picture", ""),
                "tokenName": "社群留言報導生成器",
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15,
        )
        data = resp.json()
        if str(data.get("code")) == "200":
            return data["data"]["token"], data
        return "", data
    except Exception as e:
        print(f"[auth] token exchange error: {e}")
        return "", {"error": str(e)}

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

# ── Cookie manager（必須在頁面最早初始化）────────────────────
cookie_manager = stx.CookieManager()

# ── 處理 OAuth2 callback（Google 回傳 ?code=）────────────────
_code = st.query_params.get("code", "")
_oauth_error_from_google = st.query_params.get("error", "")

if _oauth_error_from_google:
    st.session_state["_auth_error"] = f"Google 拒絕授權：{_oauth_error_from_google}"

# 有 code，且尚未登入 → 進行 token 交換
# 不清除 query_params（清除會導致 Streamlit Cloud 重建 session，session_state 遺失）
if _code and not st.session_state.get("_storm_token") and not cookie_manager.get(_COOKIE_KEY):
    try:
        _token_resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": _code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": _REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        _resp_json = _token_resp.json()
        _id_token_str = _resp_json.get("id_token", "")
        if not _id_token_str:
            st.session_state["_auth_error"] = f"Google 未回傳 id_token。回應：{_resp_json}"
        else:
            _user = _decode_jwt_payload(_id_token_str)
            if _user:
                with st.spinner("登入中..."):
                    _token, _storm_resp = _exchange_token(_id_token_str, _user)
                with st.expander("🔍 DEBUG Storm API 回應（暫時）", expanded=True):
                    st.write(_storm_resp)
                if _token:
                    st.session_state["_storm_token"] = _token
                    cookie_manager.set(_COOKIE_KEY, _token, key="cookie_set")
                    st.query_params.clear()
                else:
                    st.session_state["_auth_error"] = f"Storm API 登入失敗：{_storm_resp}"
            else:
                st.session_state["_auth_error"] = "無法解析 Google 帳號資訊"
    except Exception as e:
        st.session_state["_auth_error"] = f"OAuth 錯誤：{e}"

# ── 驗證：本機開發模式直接跳過登入 ──────────────────────────
_local_dev = os.getenv("LOCAL_DEV", "").lower() in ("1", "true", "yes")

if not _local_dev:
    _stored_token = st.session_state.get("_storm_token") or cookie_manager.get(_COOKIE_KEY)

    if not _stored_token:
        st.title("📰 社群留言報導生成器")
        st.write("")
        if "_auth_error" in st.session_state:
            st.error(st.session_state.pop("_auth_error"))
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            st.error(
                "**設定錯誤：** `GOOGLE_CLIENT_ID` 或 `GOOGLE_CLIENT_SECRET` 未設定。\n\n"
                "請至 Streamlit Cloud → App settings → Secrets 補上這兩個值。"
            )
            st.stop()
        _auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "prompt": "select_account",
        })
        col = st.columns([1, 2, 1])[1]
        with col:
            st.link_button("使用 Google 帳號登入", _auth_url, use_container_width=True)
        st.stop()

# ── 登出按鈕（本機開發模式不顯示）───────────────────────────
with st.sidebar:
    if _local_dev:
        st.caption("🛠 本機開發模式（已跳過登入）")
    elif st.button("登出", use_container_width=True):
        st.session_state.pop("_storm_token", None)
        cookie_manager.delete(_COOKIE_KEY, key="cookie_del")
        st.rerun()

st.title("📰 社群留言報導生成器")
st.caption("輸入社群貼文網址，自動擷取留言並生成風傳媒風格報導草稿")

# ── 輸入區 ───────────────────────────────────────────────────
with st.form("input_form"):
    urls_input = st.text_area(
        "貼文網址",
        placeholder="https://www.facebook.com/xxx/posts/xxx",
        height=100,
    )
    topic = st.text_input(
        "報導主題（選填，留空則自動推斷）",
        placeholder="例：捷運票價漲價爭議",
    )
    model = "claude-sonnet-4-6"
    run_btn = st.form_submit_button("開始生成報導", type="primary", use_container_width=True)

# ── 執行 ─────────────────────────────────────────────────────
if run_btn:
    urls = [urls_input.strip()] if urls_input.strip() else []
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

        if platform == "threads" and not post.comments:
            note = f"{post.comments_count} 則留言（未能取得回覆）"
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
