import json
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from app.scraper import (
    content_quality,
    extract_metadata,
    extract_readable_text,
    needs_browser,
    scrape_browser,
)


def test_extract_readable_text_removes_noise():
    html = """
    <html><head><title>Useful page</title></head><body>
      <nav>Menu item</nav>
      <main><h1>Article</h1><p>This is the useful paragraph.</p></main>
      <script>bad()</script><footer>Copyright</footer>
    </body></html>
    """
    title, text = extract_readable_text(html)
    assert title == "Useful page"
    assert "Article" in text
    assert "useful paragraph" in text
    assert "Menu item" not in text
    assert "Copyright" not in text


def test_extraction_preserves_markdown_structure():
    html = """
    <html><head><title>Structured guide</title></head><body>
      <article>
        <h1>Installation guide</h1>
        <p>This detailed introduction explains the installation process clearly.</p>
        <h2>Requirements</h2>
        <ul><li>Python 3.10</li><li>A browser</li></ul>
        <p>Follow these requirements before continuing with the remaining steps.</p>
      </article>
    </body></html>
    """
    _, text = extract_readable_text(html, "https://example.com/guide")
    assert "# Installation guide" in text
    assert "## Requirements" in text
    assert "Python 3.10" in text


def test_short_page_keeps_lists_and_tables():
    html = """
    <main>
      <h1>Quick reference</h1>
      <p>A short but useful introduction to this reference page.</p>
      <ul><li>First item</li><li>Second item</li></ul>
      <table><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>1</td></tr></table>
    </main>
    """
    _, text = extract_readable_text(html, "https://example.com/reference")
    assert "# Quick reference" in text
    assert "- First item" in text
    assert "| Name | Value |" in text


def test_extraction_preserves_images_with_resolved_urls():
    html = """
    <html><head><title>Photo essay</title></head><body>
      <article>
        <h1>Photo essay</h1>
        <p>A detailed introduction to this photo essay about mountain trails.</p>
        <img src="/images/trail.jpg" alt="Mountain trail at dawn">
        <p>Another paragraph describing the scenery and hiking conditions in depth.</p>
      </article>
    </body></html>
    """
    _, text = extract_readable_text(html, "https://example.com/essay")
    assert "![Mountain trail at dawn](https://example.com/images/trail.jpg)" in text


def test_extraction_resolves_relative_links():
    html = """
    <html><head><title>Reference</title></head><body>
      <article>
        <h1>Reference guide</h1>
        <p>See the <a href="/docs/setup">setup docs</a> for detailed instructions.</p>
        <p>This reference page also covers configuration and troubleshooting steps.</p>
      </article>
    </body></html>
    """
    _, text = extract_readable_text(html, "https://example.com/reference")
    assert "[setup docs](https://example.com/docs/setup)" in text


def test_ordered_list_items_are_numbered():
    html = """
    <main>
      <h1>Setup steps</h1>
      <p>Follow these ordered steps carefully to complete the setup process.</p>
      <ol><li>Install Python</li><li>Create a virtual environment</li><li>Run the app</li></ol>
    </main>
    """
    _, text = extract_readable_text(html, "https://example.com/steps")
    assert "1. Install Python" in text
    assert "2. Create a virtual environment" in text
    assert "3. Run the app" in text


def test_metadata_extracts_author_and_description():
    html = """
    <html><head>
      <title>Article</title>
      <meta name="author" content="Jane Doe">
      <meta name="description" content="An in-depth look at trail conditions.">
      <meta property="article:published_time" content="2024-05-01T12:00:00Z">
    </head><body>
      <article><p>This is a sufficiently long paragraph describing the article body.</p></article>
    </body></html>
    """
    metadata = extract_metadata(html, "https://example.com/article")
    assert metadata["author"] == "Jane Doe"
    assert metadata["published_date"] == "2024-05-01"
    assert "trail conditions" in metadata["description"]


def test_quality_rewards_structured_useful_content():
    useful = "# Guide\n\n" + ("A complete useful sentence. " * 80)
    noise = "Accept cookies Privacy Policy Sign up " * 15
    assert content_quality(useful) > content_quality(noise)


def test_dom_ensemble_prefers_content_over_link_heavy_sidebar():
    links = "".join(f"<a href='/item/{i}'>Menu item {i}</a>" for i in range(80))
    html = f"""
    <body>
      <div class="content">
        <h1>Useful product</h1>
        <p>This product description contains detailed and meaningful information
        about materials, dimensions, compatibility, maintenance, and warranty.</p>
        <h2>Specifications</h2>
        <ul><li>Durable material</li><li>Two-year warranty</li></ul>
      </div>
      <aside>{links}</aside>
    </body>
    """
    _, text = extract_readable_text(html, "https://example.com/product")
    assert "Useful product" in text
    assert "Two-year warranty" in text
    assert "Menu item 79" not in text


def test_thin_javascript_shell_needs_browser():
    html = '<html><body><div id="root"></div><script src="app.js"></script></body></html>'
    assert needs_browser(html, "")


def test_content_rich_page_does_not_need_browser():
    text = " ".join(["content"] * 500)
    html = f"<html><body><main>{text}</main></body></html>"
    assert not needs_browser(html, text)


@pytest.mark.asyncio
async def test_browser_renderer_runs_outside_server_event_loop():
    completed = CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps(
            {"url": "https://example.com", "html": "<html>rendered</html>"}
        ),
        stderr="",
    )
    with patch("app.scraper.subprocess.run", return_value=completed) as renderer:
        result = await scrape_browser("https://example.com")

    assert result == ("https://example.com", "<html>rendered</html>")
    assert renderer.call_count == 1
