# Contributing

Thanks for considering a contribution. This is a small project, so the process is intentionally light.

## Setup

Follow the [Quick start](README.md#quick-start) in the README to get a virtual environment, dependencies, and Playwright's Chromium binary installed. Then run the test suite to confirm your environment is working:

```bash
python -m pytest
```

## Before opening a pull request

- Add or update tests in `tests/` for any behavior change — particularly in `app/scraper.py`, which has the most edge cases (extraction candidates, list/image/link rendering, the `needs_browser` heuristic).
- Run `python -m pytest` and make sure it passes.
- Keep changes focused. If you spot an unrelated cleanup opportunity while working, feel free to mention it in the PR description rather than bundling it in.
- Match the existing style: plain functions over unnecessary abstraction, comments only where the *why* isn't obvious from the code, no new dependencies unless they clearly earn their place (see how `readability-lxml` was justified in `app/scraper.py`'s docstrings, for example).

## Reporting bugs / proposing features

Open a GitHub issue with:
- What you expected vs. what happened (for bugs), ideally with the URL or a minimal HTML snippet that reproduces it.
- For feature proposals, a short description of the use case — this is a deliberately narrow tool (public HTML pages, human-reviewed output, no persistence), so proposals that fit that scope are easiest to land.

## Security

If you find a security issue (e.g. an SSRF bypass in `app/security.py`), please open an issue describing it rather than a public PR with an exploit — give the maintainer a chance to fix it first.
