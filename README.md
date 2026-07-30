# Scrape & Review Agent

A functional human-in-the-loop web content agent. It:

1. Downloads ordinary HTML pages quickly with HTTP.
2. Detects blocked, thin, or JavaScript-rendered pages and falls back to headless Chromium.
3. Compares multiple extraction candidates and keeps the highest-quality structured Markdown.
4. Preserves useful headings, lists, tables, links, code, and lazy-loaded content.
5. Optionally sends the extraction to a Groq-hosted LLM for cleanup.
6. Pauses in a browser UI so a human can inspect, edit, and approve the result.

## Quick start

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

Add your Groq API key to `.env`:

```dotenv
GROQ_API_KEY=your_key_here
```

The model name and Groq-compatible endpoint are configurable in the same file.
The app still works without a key; it simply shows the locally extracted text
for human editing.

Start the app:

```powershell
python -m uvicorn app.main:app --reload
```

On Windows, the headless-browser fallback is executed in an isolated helper
process so it remains compatible with Uvicorn's `--reload` event loop.

Open `http://127.0.0.1:8000`.

## Tests

```powershell
python -m pytest
```

## Current boundaries

- Only public HTTP/HTTPS HTML pages are accepted. Local/private IPs are blocked
  to reduce server-side request forgery risk.
- The MVP returns the approved content to the browser; it does not persist it.
- Pages behind authentication, CAPTCHAs, paywalls, or aggressive bot protection
  are intentionally not bypassed.
- Respect each site's terms, robots policy, copyright, and applicable law.

## API

- `POST /api/scrape` — scrape, extract, and optionally LLM-clean a URL.
- `POST /api/approve` — validate and return the human-edited final content.
- `GET /api/health` — health check.
- `GET /docs` — interactive OpenAPI documentation.
