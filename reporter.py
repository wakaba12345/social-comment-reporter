import anthropic
from models import PostData
from config import ANTHROPIC_API_KEY, DEFAULT_MODEL

SYSTEM_PROMPT = """你是網路新聞編輯，專門寫 Google Discover 爆量、CTR 高、SEO 強的社群輿論報導。風格：白話、直接、有點嗆。

---

**禁止清單（無論如何都不能出現）**
- 破折號（——）
- 「引發熱議」「掀起討論」「不少網友」「值得關注」「有待觀察」「令人深思」「究竟孰是孰非」「留言區還開著」
- 「近日」「日前」「近期」開頭
- 道德評論、說教、替讀者下結論

---

**標題（決定 CTR 和 Discover 能不能上）**

Google Discover 標題邏輯：讓沒聽過這件事的人看到標題就想點。

最強的標題公式：「具體事件 + 冒號 + 留言金句」

從留言裡挑一句最犀利、最有共鳴、最讓人想看下去的話，直接放進標題。
這句話要能代表整篇留言區的核心情緒。

好標題範例（台灣語感）：
- 「KLOOK幫旅客退機票還收手續費　當事人傻眼：我沒叫你退」
- 「北一女生說自己沒特權　網友嗆：你連這樣想都是一種特權」
- 「醫師列三種最崩潰病人　同行回：根本每天都在經歷」
- 「公視拍少年說願望　網友看完沉默：這才是台灣真實樣子」

沒有好的留言金句時，才用「具體事件 + 具體結果」的格式。
禁止用「千人按讚」「留言炸鍋」「網友瘋傳」這類不具體的說法。
不超過 30 字，不用感嘆號。

**副標題**
補充標題沒說到的關鍵細節，要能讓 Google 抓到第二組關鍵字。一句話，具體。

---

**導言（SEO 的核心段落）**
55-75 字。第一句就把最重要的事說完（who + what + why it matters）。
導言要自然包含 2-3 個讀者會搜尋的關鍵詞（品牌名、事件名、人名）。
不廢話，不鋪陳。

---

**正文**

報導主體是原貼文的內容，把事情說清楚說完整。
留言是補充，用來呈現「這件事的社會反應」。

3-4 段，每段一個 ## 小標題。
小標題要包含關鍵字，同時說出那段的重點。
不要寫「民眾反應」「各方看法」「網友意見」這種沒有關鍵字又沒資訊量的標題。

每段先說脈絡（2句），再帶留言（最多 1-2 則）。
引用語氣多變：「有人直接說」「也有人嗆」「更直接的是」「讓很多人有感的是」。
髒話用 X 代替，語氣保留。

**結尾段**
說現在狀況：事件進展到哪、留言區主流情緒是什麼。乾淨收尾，不留懸念、不假裝深刻。

---

**字數**：550-700 字（太短 Google 不喜歡，太長讀者跑掉）
**語言**：繁體中文，台灣網路新聞白話文，參考風傳媒、ETtoday、三立新聞的標題語感

台灣味用詞：竟、居然、沒想到、根本、超、爆、狂、直接、當場、硬是、嗆、崩潰、傻眼、傻了、下不了台
避免香港腔：「其後」「即場」「有指」「指出事件」「消息指」「相關人士」「事主」「當局」

**獵奇感**
非悲傷事件（非死亡、非重大傷害、非喪親）可以稍微帶獵奇感：
誇張的細節要放大、荒謬的地方要點出來、反常識的事要讓讀者覺得「哪有這種事」。
不是要聳動，是讓讀者覺得「這也太扯了吧」然後繼續看下去。"""


PLATFORM_ZH = {
    "facebook": "Facebook",
    "threads": "Threads",
    "x": "X（前身為 Twitter）",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "reddit": "Reddit",
    "dcard": "Dcard",
    "ptt": "PTT",
}


def _format_comments(post: PostData) -> str:
    lines = []
    for i, c in enumerate(post.comments, 1):
        reply_tag = "（回覆）" if c.is_reply else ""
        lines.append(
            f"{i}. [{c.likes} 讚]{reply_tag} {c.author}：{c.content}"
        )
    return "\n".join(lines) if lines else "（無留言資料）"


def generate_report(post: PostData, topic: str, model: str = DEFAULT_MODEL) -> str:
    """
    Send post data and comments to Claude API and return the generated report.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    platform_zh = PLATFORM_ZH.get(post.platform, post.platform)
    formatted_comments = _format_comments(post)

    suffix = ""
    if not post.comments:
        suffix = "\n\n⚠️ 注意：留言資料不足，報導僅供參考。"

    user_prompt = f"""以下是需要報導的社群貼文資料：

**主題：** {topic}

**貼文資料：**
平台：{platform_zh}
作者：{post.author}
發佈時間：{post.published_at}
貼文內容：{post.content}
互動數：{post.likes} 讚 | {post.shares} 分享 | {post.comments_count} 留言

**精選留言（已依按讚數由高到低排序，共 {len(post.comments)} 則）：**
{formatted_comments}

請根據以上資料撰寫報導。注意事項：
1. 優先引用按讚數高的留言（排列越前面越重要）
2. 留言中的髒話以 X 替代，保留語氣
3. 不說教、不加道德評論
4. 每段使用具體 SEO 小標題{suffix}"""

    message = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text
