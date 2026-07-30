import asyncio
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from readability import Document as ReadabilityDocument
from trafilatura import extract as extract_main_content
from trafilatura.metadata import extract_metadata as extract_trafilatura_metadata

from .config import settings
from .security import validate_public_url


@dataclass
class ScrapedPage:
    url: str
    title: str
    text: str
    method: str
    author: str | None = None
    published_date: str | None = None
    description: str | None = None
    warning: str | None = None


DROP_TAGS = {
    "script", "style", "noscript", "svg", "canvas", "iframe", "nav",
    "footer", "header", "form", "button", "aside",
}


def _resolve_url(value: str, base_url: str | None) -> str:
    value = value.strip()
    if base_url and value and not value.startswith("data:"):
        return urljoin(base_url, value)
    return value


def _image_markdown(img, base_url: str | None) -> str:
    src = (
        img.get("src")
        or img.get("data-src")
        or img.get("data-lazy-src")
        or img.get("data-original")
        or ""
    )
    src = src.strip()
    if not src or src.startswith("data:"):
        return ""
    alt = re.sub(r"\s+", " ", (img.get("alt") or "").strip())
    return f"![{alt}]({_resolve_url(src, base_url)})"


def _inline_markdown(node, base_url: str | None = None) -> str:
    pieces: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            pieces.append(child)
        elif child.name == "a":
            label = child.get_text(" ", strip=True)
            href = child.get("href")
            href = _resolve_url(href, base_url) if href else None
            pieces.append(f"[{label}]({href})" if label and href else label)
        elif child.name == "img":
            pieces.append(_image_markdown(child, base_url))
        elif child.name in {"ul", "ol"}:
            # A nested list inside this item is rendered separately as its
            # own block-level lines; flattening its text here would
            # duplicate it inline as well.
            continue
        elif child.name in {"strong", "b"}:
            pieces.append(f"**{child.get_text(' ', strip=True)}**")
        elif child.name in {"em", "i"}:
            pieces.append(f"*{child.get_text(' ', strip=True)}*")
        elif child.name == "code":
            pieces.append(f"`{child.get_text(' ', strip=True)}`")
        else:
            pieces.append(child.get_text(" ", strip=True))
    return re.sub(r"\s+", " ", "".join(pieces)).strip()


def _table_markdown(table) -> list[str]:
    rows = [
        [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        for row in table.find_all("tr")
    ]
    rows = [row for row in rows if row]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    output = ["| " + " | ".join(rows[0]) + " |"]
    output.append("| " + " | ".join(["---"] * width) + " |")
    output.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return output


def _list_item_marker(node) -> str:
    depth = len(node.find_parents("li"))
    indent = "  " * depth
    list_parent = node.find_parent(["ul", "ol"])
    if list_parent is not None and list_parent.name == "ol":
        siblings = list_parent.find_all("li", recursive=False)
        try:
            index = siblings.index(node) + 1
        except ValueError:
            index = 1
        start = list_parent.get("start")
        if start and str(start).isdigit():
            index += int(start) - 1
        return f"{indent}{index}."
    return f"{indent}-"


def _element_markdown(root, base_url: str | None = None) -> str:
    lines: list[str] = []
    block_tags = {
        "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre",
        "blockquote", "table", "img",
    }
    for node in root.find_all(block_tags):
        parent = node.find_parent(block_tags)
        if node.name == "img":
            if parent:
                continue
        elif parent and parent.name not in {"li", "blockquote"}:
            continue
        if node.name.startswith("h"):
            value = f"{'#' * int(node.name[1])} {_inline_markdown(node, base_url)}"
        elif node.name == "li":
            value = f"{_list_item_marker(node)} {_inline_markdown(node, base_url)}"
        elif node.name == "pre":
            value = f"```\n{node.get_text(chr(10), strip=True)}\n```"
        elif node.name == "blockquote":
            value = "\n".join(
                f"> {line}" for line in node.get_text("\n", strip=True).splitlines()
            )
        elif node.name == "table":
            lines.extend(_table_markdown(node))
            continue
        elif node.name == "img":
            value = _image_markdown(node, base_url)
        else:
            value = _inline_markdown(node, base_url)
        if value and (not lines or value != lines[-1]):
            lines.append(value)
    return "\n".join(lines)


def _candidate_score(node, markdown: str) -> float:
    words = markdown.split()
    if not words:
        return 0
    all_text = node.get_text(" ", strip=True)
    link_text = " ".join(link.get_text(" ", strip=True) for link in node.find_all("a"))
    link_density = len(link_text) / max(len(all_text), 1)
    paragraph_words = sum(
        len(paragraph.get_text(" ", strip=True).split())
        for paragraph in node.find_all("p")
    )
    semantic_bonus = 120 if node.name in {"main", "article"} else 0
    return (
        content_quality(markdown)
        + min(paragraph_words, 1_500) * 0.35
        + semantic_bonus
        - link_density * min(len(words), 1_000) * 1.2
    )


def _basic_extract(html: str, url: str | None = None) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Untitled page"
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()

    selectors = (
        "main", "article", '[role="main"]', "#content", "#main-content",
        ".content", ".main-content", ".article-content", ".post-content",
        ".entry-content", ".product", ".product-detail",
    )
    candidates = []
    seen: set[int] = set()
    for selector in selectors:
        for node in soup.select(selector):
            if id(node) not in seen:
                candidates.append(node)
                seen.add(id(node))
    if soup.body:
        candidates.append(soup.body)
    elif not candidates:
        candidates.append(soup)

    scored = [
        (_candidate_score(node, markdown), markdown)
        for node in candidates
        if (markdown := _element_markdown(node, url))
    ]
    return title, max(scored, default=(0, ""), key=lambda item: item[0])[1]


def _readability_extract(html: str, url: str | None) -> str | None:
    """Run readability-lxml's density-based extractor as a third candidate.

    It disagrees with trafilatura often enough on template-heavy pages
    (news sites, forums) to be worth comparing rather than trusting either
    extractor blindly.
    """
    try:
        summary_html = ReadabilityDocument(html).summary(html_partial=True)
    except Exception:
        return None
    if not summary_html:
        return None
    soup = BeautifulSoup(summary_html, "html.parser")
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    return _element_markdown(soup, url) or None


def extract_readable_text(html: str, url: str | None = None) -> tuple[str, str]:
    """Extract the main content as structured Markdown.

    Several independent extractors disagree on which part of a page is the
    "main content", especially on template-heavy sites, so multiple
    candidates are generated and the one with the best content-quality score
    wins. Weights break near-ties in favor of the generally more reliable
    extractors instead of picking whichever happens to score a point higher.
    """
    title, fallback_text = _basic_extract(html, url)

    candidates: list[tuple[float, str]] = []
    if fallback_text:
        candidates.append((content_quality(fallback_text) * 1.0, fallback_text))

    recall_extracted = extract_main_content(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_links=True,
        include_formatting=True,
        include_images=True,
        deduplicate=True,
        favor_recall=True,
    )
    if recall_extracted and len(recall_extracted.split()) >= 20:
        recall_extracted = recall_extracted.strip()
        candidates.append((content_quality(recall_extracted) * 1.2, recall_extracted))

    precision_extracted = extract_main_content(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_links=True,
        include_formatting=True,
        include_images=True,
        deduplicate=True,
        favor_precision=True,
    )
    if precision_extracted and len(precision_extracted.split()) >= 20:
        precision_extracted = precision_extracted.strip()
        candidates.append(
            (content_quality(precision_extracted) * 1.15, precision_extracted)
        )

    readability_text = _readability_extract(html, url)
    if readability_text and len(readability_text.split()) >= 20:
        candidates.append((content_quality(readability_text) * 1.05, readability_text))

    if not candidates:
        return title, fallback_text
    return title, max(candidates, key=lambda item: item[0])[1]


def extract_metadata(html: str, url: str | None) -> dict[str, str | None]:
    """Best-effort author/date/description for human review context."""
    try:
        document = extract_trafilatura_metadata(html, default_url=url)
    except Exception:
        document = None
    if document is None:
        return {"author": None, "published_date": None, "description": None}
    return {
        "author": document.author or None,
        "published_date": document.date or None,
        "description": document.description or None,
    }


def content_quality(text: str) -> float:
    """Estimate usefulness when choosing raw HTML versus rendered HTML."""
    words = text.split()
    if not words:
        return 0
    unique_ratio = len({word.casefold() for word in words}) / len(words)
    structure = sum(
        1
        for line in text.splitlines()
        if line.lstrip().startswith(("#", "-", "*", "|"))
    )
    sentence_marks = sum(text.count(mark) for mark in ".?!:")
    boilerplate = sum(
        text.casefold().count(term)
        for term in (
            "accept cookies",
            "privacy policy",
            "sign up",
            "all rights reserved",
            "enable javascript",
        )
    )
    # Some extractors occasionally repeat a paragraph verbatim (e.g. when a
    # trailing sentence gets re-emitted as its own block). Repetition never
    # adds information for the human reviewer, so it should not be able to
    # win purely by inflating word count.
    substantial_lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 40]
    seen_lines: set[str] = set()
    duplicate_penalty = 0
    for line in substantial_lines:
        if line in seen_lines:
            duplicate_penalty += 40
        else:
            seen_lines.add(line)
    return (
        min(len(words), 2_000)
        + min(structure, 30) * 8
        + min(sentence_marks, 100) * 2
        + unique_ratio * 100
        - boilerplate * 80
        - duplicate_penalty
    )


def needs_browser(html: str, text: str) -> bool:
    lower = html.lower()
    shell_markers = (
        'id="root"', "id='root'", 'id="app"', "id='app'",
        "__next_data__", "enable javascript", "javascript is required",
        "data-reactroot", "ng-version", 'id="__nuxt"', "id='__nuxt'",
        'id="___gatsby"', "id='___gatsby'", "__preloaded_state__",
        "__initial_state__", "window.__nuxt__",
    )
    visible_words = len(text.split())
    script_count = lower.count("<script")
    # A large document with very little visible text usually means the
    # markup is mostly framework/JS scaffolding rather than rendered content.
    text_to_html_ratio = len(text) / max(len(html), 1)
    return (
        visible_words < 180
        or any(marker in lower for marker in shell_markers) and visible_words < 400
        or script_count >= 8 and visible_words < 250
        or len(html) > 20_000 and text_to_html_ratio < 0.015 and visible_words < 350
    )


async def scrape_http(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ContentReviewBot/1.0; "
            "+https://localhost)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, follow_redirects=True
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                raise ValueError("The URL did not return an HTML page.")
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > settings.max_download_bytes:
                    raise ValueError("The page is larger than the configured download limit.")
            encoding = response.encoding or "utf-8"
            return str(response.url), chunks.decode(encoding, errors="replace")


def _scrape_browser_sync(url: str) -> tuple[str, str]:
    """Render a page in an isolated helper process.

    Uvicorn's Windows reload mode uses a selector event loop, which cannot
    create the subprocess used internally by Playwright. A fresh Python helper
    process receives Windows' normal Proactor policy, while Uvicorn keeps its
    own event loop unchanged.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.browser_worker"],
            input=json.dumps({"url": url}),
            text=True,
            capture_output=True,
            check=True,
            timeout=settings.request_timeout_seconds + 15,
        )
        response = json.loads(result.stdout)
        return response["url"], response["html"]
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Headless browser rendering timed out.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip().splitlines()
        message = detail[-1] if detail else "unknown browser error"
        raise RuntimeError(f"Headless browser failed: {message}") from exc
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError("Headless browser returned an invalid response.") from exc


async def scrape_browser(url: str) -> tuple[str, str]:
    return await asyncio.to_thread(_scrape_browser_sync, url)


async def scrape(url: str) -> ScrapedPage:
    validate_public_url(url)
    warning = None
    try:
        final_url, html = await scrape_http(url)
        validate_public_url(final_url)
        title, text = extract_readable_text(html, final_url)
        method = "http"
    except (httpx.HTTPError, ValueError) as exc:
        if not settings.enable_browser_fallback:
            raise
        final_url, html = await scrape_browser(url)
        validate_public_url(final_url)
        title, text = extract_readable_text(html, final_url)
        method = "browser"
        warning = f"Direct download failed, so the browser renderer was used: {exc}"

    if (
        settings.enable_browser_fallback
        and method == "http"
        and needs_browser(html, text)
    ):
        try:
            browser_url, rendered_html = await scrape_browser(final_url)
            validate_public_url(browser_url)
            rendered_title, rendered_text = extract_readable_text(
                rendered_html, browser_url
            )
            if content_quality(rendered_text) > content_quality(text) * 1.08:
                final_url, title, text, method, html = (
                    browser_url,
                    rendered_title,
                    rendered_text,
                    "browser",
                    rendered_html,
                )
        except Exception as exc:
            if not text:
                raise
            warning = (
                "Browser enhancement failed, so the direct HTML extraction "
                f"was retained: {exc}"
            )

    if not text:
        raise ValueError("No readable content was found on this page.")
    metadata = extract_metadata(html, final_url)
    return ScrapedPage(
        url=final_url,
        title=title,
        text=text,
        method=method,
        author=metadata["author"],
        published_date=metadata["published_date"],
        description=metadata["description"],
        warning=warning,
    )
