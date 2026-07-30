import httpx

from .config import settings


SYSTEM_PROMPT = """You are a precise web-content editor preparing an extraction
for human review. This is a cleanup task, not a summarization task.

Rules:
- Preserve every meaningful fact, name, number, quote, caveat, and source link.
- Preserve the document's order and Markdown hierarchy.
- Preserve useful headings, paragraphs, lists, tables, and code blocks.
- Remove only obvious navigation, cookie banners, advertisements, sharing
  controls, repeated boilerplate, and unrelated page chrome.
- Repair broken line wrapping and formatting without rewriting the author's
  meaning or tone.
- Never invent information or add an introduction, conclusion, analysis, or
  comments about your work.
- Return only the cleaned Markdown document."""


async def clean_content(text: str, instructions: str) -> tuple[str, bool, str | None]:
    if not settings.groq_api_key:
        return (
            text,
            False,
            "GROQ_API_KEY is not configured, so the extracted text is shown without LLM cleanup.",
        )

    clipped = text[: settings.max_llm_input_chars]
    payload = {
        "model": settings.groq_model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"User instructions:\n{instructions}\n\nExtracted page:\n{clipped}",
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.groq_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            cleaned = response.json()["choices"][0]["message"]["content"].strip()
            return cleaned or text, True, None
    except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
        return text, False, f"LLM cleanup failed; showing extracted text instead: {exc}"
