# YCT Book Downloader — Render Deployment

## Files
```
app.py           → Flask backend (SSE streaming, job queue, file serving)
downloader.py    → Core logic (login, download, PDF, EPUB, ZIP, Telegram)
requirements.txt → Python dependencies
render.yaml      → Render deploy config
```

## Deploy to Render (step by step)

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "YCT Downloader"
   gh repo create yct-downloader --public --push
   ```

2. **Go to [render.com](https://render.com)**
   - New → Web Service
   - Connect your GitHub repo
   - Render auto-detects `render.yaml` — just click **Deploy**

3. **Done** — your URL will be `https://yct-book-downloader.onrender.com`

## How it works

- Frontend is served by Flask itself (no separate Vite/Node needed)
- Jobs run in background threads — no timeout issues
- Logs stream in real-time via SSE (Server-Sent Events)
- Files stored in `/tmp/yct_jobs/<job_id>/` (ephemeral — download before redeploy)
- Download links appear in the UI when files are ready

## Limits on Render Free Tier

| Limit | Detail |
|-------|--------|
| RAM | 512 MB — fine for ~100 pages |
| Storage | Ephemeral `/tmp` — files lost on restart |
| Sleep | App sleeps after 15 min inactivity |
| Timeout | No HTTP timeout (SSE keeps connection alive) |

## For large books (200+ pages)

Upgrade to Render Starter ($7/mo) or pipe files directly to:
- **Telegram** (built-in, up to 50 MB per file)
- **Cloudflare R2** (add `boto3` + R2 credentials as env vars)

## Local development

```bash
pip install -r requirements.txt
python app.py
# Visit http://localhost:5000
```
