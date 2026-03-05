# Postiz Setup for Swing Shack TikTok

## What I Learned from Documentation

### How It Works (The Larry Workflow)

1. **Generate images** (with text overlays)
2. **Upload to Postiz** as draft
3. **Postiz sends to TikTok** with `privacy_level: "SELF_ONLY"` (lands in your TikTok drafts)
4. **You get the caption** from me in Discord
5. **You add trending sound** on TikTok app, paste caption, publish
6. **60 seconds your side**, 15-30 minutes my side

---

## What I Need from You

### 1. Postiz Account
- Sign up at https://postiz.com
- (You already have one?)

### 2. API Key
From Postiz Settings:
- Go to Settings → API Keys
- Create a new API key
- Send me the key

### 3. Connect TikTok
- In Postiz dashboard, add TikTok integration
- Authorize TikTok account access

### 4. Integration ID
After connecting, I need the **TikTok integration ID** (looks like `uuid`)

---

## How the API Works

### Upload Image/Video
```
POST https://api.postiz.com/public/v1/upload
Header: Authorization: YOUR-API-KEY
Body: file=@image.jpg
```
Returns: `{ "id": "img-123", "path": "https://..." }`

### Create TikTok Draft Post
```json
{
  "type": "schedule",
  "date": "2024-12-14T10:00:00.000Z",
  "posts": [{
    "integration": { "id": "TIKTOK-INTEGRATION-ID" },
    "value": [{
      "content": "Your caption here #hashtags",
      "image": [{ "id": "uploaded-image-id", "path": "https://..." }]
    }],
    "settings": {
      "__type": "tiktok",
      "privacy_level": "SELF_ONLY",
      "autoAddMusic": "no",
      "content_posting_method": "UPLOAD"
    }
  }]
}
```

---

## Key Settings for Draft Mode

| Setting | Value | Purpose |
|---------|-------|---------|
| `privacy_level` | `SELF_ONLY` | Lands in your drafts |
| `autoAddMusic` | `no` | You add sound manually |
| `content_posting_method` | `UPLOAD` | Upload for manual post |

---

## What I Can Do Once Connected

✅ Generate images with text overlays
✅ Upload to Postiz
✅ Create TikTok draft posts
✅ Send you the caption in Discord
❌ Add trending music (you do this manually)

---

## Next Steps

1. **You:** Set up Postiz account + connect TikTok
2. **You:** Get API key + integration ID
3. **Me:** Test the workflow with one post

Want me to help you set up Postiz?
