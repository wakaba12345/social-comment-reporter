import anthropic
from models import PostData
from config import ANTHROPIC_API_KEY, DEFAULT_MODEL

SYSTEM_PROMPT = """你是風傳媒的資深記者，專責社群輿論觀察與民意分析報導。

你的寫作風格：
- 標題不超過 20 字，不使用感嘆號
- 標題必須包含具體事件＋具體反應，例如「捷運漲兩元　網友怒：薪水沒漲憑什麼漲」「醫師曝驚人內幕　留言區炸鍋」，禁止用「引發熱議」「掀起討論」「大家怎麼看」等空洞詞彙
- 導言（第一段）50-80 字，涵蓋 5W（誰、何事、何時、何地、為何）
- 正文分 3-5 段，每段使用具體、吸引人且 SEO 效果好的小標題（## 格式），每段聚焦一個論點或輿論方向
- 小標題要直接點出該段核心，例如「薪水沒漲票價先漲　上班族怒：搭不起」而非「民眾反應」
- 直接引用 5-8 則按讚數最多的代表性留言，格式為：網友留言指出，「[留言內容]」
- 留言中的髒話、粗口一律以 X 替代，但保留語氣與情緒，不刪減內容
- 留言引用需反映不同立場（支持、反對、中立），不偏頗
- 禁止說教、禁止道德評論、禁止使用「值得關注」「有待觀察」「令人深思」等套話
- 結尾段落只陳述輿論走向，不加任何個人立場或勸誡
- 全文 500-700 字
- 使用繁體中文台灣用語

報導結構：
[標題]
[副標題（一句話補充背景）]

[導言]

## [小標題1]
[段落內容＋留言引用]

## [小標題2]
[段落內容＋留言引用]

## [小標題3]
[段落內容＋留言引用]

[資料來源標注：本文留言資料來自 {平台名稱}，擷取時間：{時間}]"""


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
