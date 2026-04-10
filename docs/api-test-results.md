# byCrawl API 實測結果

測試日期：2026-04-10

## 結果摘要

| 平台 | 貼文 Endpoint | 留言 Endpoint | 留言回傳方式 | 備註 |
|------|--------------|--------------|-------------|------|
| facebook | `GET /facebook/posts?url=xxx` | `GET /facebook/posts/comments?url=xxx` | `{"comments":[...],"nextCursor":null}` | 實測部分公開貼文返回空陣列，需公開頁面貼文 |
| threads | `GET /threads/posts/:id`（數字ID或shortcode均可） | ❌ 無（404） | 無法擷取 | 改以貼文本身 stats.replies 顯示回覆數 |
| x | `GET /x/posts/:id` | ❌ 無（404），改用 Search | `GET /x/posts/search?q=conversation_id:{id}` | 搜尋結果含 isReply:true，可當留言用 |
| instagram | 未測 | 未測 | 未知 | Phase 2 |
| youtube | 未測 | 未測 | 未知 | Phase 2 |
| reddit | 未測 | 未測 | 未知 | Phase 2 |
| dcard | 未測 | 未測 | 未知 | Phase 2 |
| ptt | 未測 | 未測 | 未知 | Phase 2 |

---

## 各平台實際 JSON 結構

### Facebook

**貼文** `GET /facebook/posts?url=xxx`
```json
{
  "id": "1139416194901028",
  "url": "https://www.facebook.com/...",
  "author": { "id": "", "name": "" },
  "text": "",
  "createdAt": "",
  "reactionCount": 0,
  "commentCount": 0,
  "shareCount": 0,
  "viewCount": 0,
  "media": []
}
```

**留言** `GET /facebook/posts/comments?url=xxx`
```json
{
  "comments": [
    {
      "author": { "id": "...", "name": "..." },
      "text": "...",
      "likeCount": 0,
      "createdAt": "...",
      "replies": []
    }
  ],
  "nextCursor": null
}
```

---

### Threads

**貼文** `GET /threads/posts/:id`（數字 ID 或 shortcode 均可）
```json
{
  "id": "3870872187813562164",
  "mediaId": "17986679135965141",
  "code": "DW4Gb79kQc0",
  "text": "Today we're sharing...",
  "user": { "id": "...", "username": "zuck", "profilePic": "...", "isVerified": true },
  "media": [],
  "views": 121827,
  "stats": { "likes": 2585, "replies": 474, "quotes": 54, "reposts": 184, "shares": 336 },
  "createdAt": "2026-04-08T15:59:05.000Z",
  "replyTo": null,
  "isReply": false
}
```

**留言**：無獨立 endpoint（404），無法擷取回覆內容。

---

### X（Twitter）

**貼文** `GET /x/posts/:id`
```json
{
  "id": "1519480761749016577",
  "text": "Next I'm buying Coca-Cola...",
  "createdAt": "2022-04-28T00:56:58.000Z",
  "user": { "id": "44196397", "username": "elonmusk", "name": "Elon Musk", "isVerified": true },
  "likeCount": 4234792,
  "retweetCount": 584613,
  "replyCount": 168568,
  "quoteCount": 167468,
  "bookmarkCount": 21376,
  "viewCount": null,
  "media": [],
  "isRetweet": false,
  "isReply": false,
  "lang": "en",
  "url": "https://x.com/elonmusk/status/1519480761749016577"
}
```

**留言**：無 `/comments` endpoint（404）。
**替代方案**：`GET /x/posts/search?q=conversation_id:{post_id}` 可取得回覆推文（`isReply: true`）。

---

## 欄位對應表

| 欄位 | Facebook | Threads | X |
|------|----------|---------|---|
| 作者 | `author.name` | `user.username` | `user.username` |
| 內容 | `text` | `text` | `text` |
| 發布時間 | `createdAt` | `createdAt` | `createdAt` |
| 讚數 | `reactionCount` | `stats.likes` | `likeCount` |
| 分享數 | `shareCount` | `stats.reposts` | `retweetCount` |
| 留言數 | `commentCount` | `stats.replies` | `replyCount` |
| 留言擷取 | `comments[].text` + `comments[].author.name` | ❌ 不支援 | search `q=conversation_id:id` |
