# Scrape & Review Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

A human-in-the-loop web content agent. Give it a public URL and it:

1. Downloads ordinary HTML pages quickly with HTTP.
2. Detects blocked, thin, or JavaScript-rendered pages and falls back to a headless Chromium browser.
3. Runs several independent extractors (trafilatura, readability-lxml, and a custom DOM-based extractor) and keeps the highest-quality structured Markdown.
4. Preserves headings, ordered/nested lists, tables, links, images, code, and lazy-loaded content.
5. Optionally sends the extraction to a Groq-hosted LLM for cleanup.
6. Pauses in a browser UI — with a live Markdown preview — so a human can inspect, edit, and approve the result before it goes anywhere else.

It's built as a small, readable reference implementation of a "scrape responsibly" pipeline: SSRF guards, multi-candidate extraction, and a mandatory human approval step, rather than a scraper that tries to defeat bot protection.

## Architecture

![Architecture diagram: the browser UI posts to the FastAPI app, which validates the URL, fetches it over HTTP, extracts readable text from four scored candidates, optionally re-renders with a headless-Chromium subprocess when the page looks thin or JS-rendered, picks the best-scoring extraction, pulls metadata, optionally runs it through a Groq LLM cleanup pass, and returns it to the browser for human review and approval.](docs/architecture.png)

**Why a subprocess for the browser renderer?** Uvicorn's `--reload` mode on Windows uses a selector event loop, which can't spawn the subprocess Playwright needs internally. `browser_worker.py` runs as a fresh helper process (`python -m app.browser_worker`) so it gets a normal event loop regardless of what the parent server is doing — see [app/scraper.py](app/scraper.py)'s `_scrape_browser_sync`.

**Why four extraction candidates?** Different extractors disagree about what counts as "main content," especially on template-heavy sites (news, forums, product pages). Rather than trusting one, `extract_readable_text` scores every candidate with `content_quality()` — which rewards structure and useful text while penalizing boilerplate and duplicated paragraphs — and keeps the winner. See [app/scraper.py](app/scraper.py).

## Quick start

Requires Python 3.11 or newer.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

**macOS / Linux**

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Add your Groq API key to `.env`:

```dotenv
GROQ_API_KEY=your_key_here
```

The app still works without a key; it simply shows the locally extracted text for human editing instead of an LLM-cleaned version.

Start the app:

```bash
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Configuration

All settings are read from `.env` (see [.env.example](.env.example)) via [app/config.py](app/config.py).

| Variable | Default | Description |
| --- | --- | --- |
| `GROQ_API_KEY` | *(empty)* | Enables the optional LLM cleanup step. Left empty, the app returns the raw extraction. |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Any Groq-hosted chat-completion model. |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | OpenAI-compatible endpoint; point elsewhere for a different provider. |
| `REQUEST_TIMEOUT_SECONDS` | `20` | Timeout for both the HTTP fetch and the headless browser render. |
| `MAX_DOWNLOAD_BYTES` | `5000000` | Hard cap on downloaded page size. |
| `MAX_LLM_INPUT_CHARS` | `60000` | Extraction is clipped to this length before being sent to the LLM. |
| `ENABLE_BROWSER_FALLBACK` | `true` | Set to `false` to disable the headless-Chromium fallback entirely (HTTP-only). |

## API

- `POST /api/scrape` — scrape, extract, and optionally LLM-clean a URL.
- `POST /api/approve` — validate and return the human-edited final content.
- `GET /api/health` — health check.
- `GET /docs` — interactive OpenAPI documentation.

## Project structure

```
app/
├── main.py            FastAPI routes (/api/scrape, /api/approve, /api/health)
├── scraper.py          HTTP fetch, multi-candidate extraction, JS-rendering heuristics
├── browser_worker.py   Isolated Playwright/Chromium renderer (run as a subprocess)
├── llm.py              Optional Groq cleanup pass
├── security.py         SSRF guard (validate_public_url)
├── config.py            Settings loaded from .env
├── models.py            Pydantic request/response models
└── static/              Front end (vanilla HTML/CSS/JS, no build step)
tests/                   pytest suite for extraction, security, and the browser subprocess boundary
```

## Tests

```bash
python -m pytest
```

## Current boundaries

- Only public HTTP/HTTPS HTML pages are accepted. Local, loopback, link-local, and other non-global IPs are blocked to reduce server-side request forgery risk (see [app/security.py](app/security.py)).
- The MVP returns the approved content to the browser; it does not persist it anywhere.
- Pages behind authentication, CAPTCHAs, paywalls, or aggressive bot protection are intentionally not bypassed.
- This fetches whatever URL a user gives it. If you deploy it publicly, treat it as an open fetch-and-render proxy and add your own rate limiting/access control as appropriate for your audience.
- Respect each site's terms, robots policy, copyright, and applicable law.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to get set up, the project's style expectations, and how to submit a pull request.

## License

[MIT](LICENSE)
