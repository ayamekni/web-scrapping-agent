from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .llm import clean_content
from .models import ApprovalRequest, ApprovalResponse, ScrapeRequest, ScrapeResponse
from .scraper import scrape
from .security import UnsafeUrlError


BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Scrape & Review Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_endpoint(request: ScrapeRequest):
    try:
        page = await scrape(str(request.url))
        cleaned, llm_used, llm_warning = await clean_content(
            page.text, request.instructions
        )
        warning = " ".join(
            item for item in (page.warning, llm_warning) if item
        ) or None
        return ScrapeResponse(
            url=page.url,
            title=page.title,
            method=page.method,
            raw_text=page.text,
            cleaned_text=cleaned,
            llm_used=llm_used,
            author=page.author,
            published_date=page.published_date,
            description=page.description,
            warning=warning,
        )
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not process page: {exc}") from exc


@app.post("/api/approve", response_model=ApprovalResponse)
async def approve(request: ApprovalRequest):
    return ApprovalResponse(
        status="approved",
        title=request.title.strip() or "Untitled page",
        content=request.content.strip(),
    )
