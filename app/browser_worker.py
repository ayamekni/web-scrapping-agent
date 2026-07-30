"""Isolated Playwright renderer for Windows/Uvicorn compatibility."""

import json
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .config import settings


def render(url: str) -> tuple[str, str]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (compatible; ContentReviewBot/1.0)"
        )
        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(settings.request_timeout_seconds * 1000),
            )
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except PlaywrightTimeoutError:
                pass
            # Trigger common lazy-loading implementations by scrolling until
            # the document stops growing (bounded, so endless feeds don't
            # scroll forever), then give one last settle window for any
            # trailing fetch/render cycle to land.
            page.evaluate(
                """async () => {
                    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                    let stableRounds = 0;
                    let lastHeight = 0;
                    const maxRounds = 25;
                    for (let round = 0; round < maxRounds && stableRounds < 2; round++) {
                        window.scrollTo(0, document.body.scrollHeight);
                        await delay(220);
                        const height = document.body.scrollHeight;
                        stableRounds = height === lastHeight ? stableRounds + 1 : 0;
                        lastHeight = height;
                    }
                    window.scrollTo(0, 0);
                    await delay(300);
                }"""
            )
            try:
                page.wait_for_load_state("networkidle", timeout=4_000)
            except PlaywrightTimeoutError:
                pass
            return page.url, page.content()
        finally:
            browser.close()


def main() -> None:
    request = json.load(sys.stdin)
    final_url, html = render(request["url"])
    json.dump({"url": final_url, "html": html}, sys.stdout)


if __name__ == "__main__":
    main()
