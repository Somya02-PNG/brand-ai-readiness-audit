#!/usr/bin/env python3
"""
render-readability-audit/scripts/check_render_gap.py

Detects content only visible after JavaScript execution by diffing
raw HTTP response text against Playwright-rendered DOM text.

Usage:
    python check_render_gap.py <url>
    python check_render_gap.py https://example.com

Returns JSON list of findings to stdout.
"""

import sys
import json
import time
from urllib.parse import urlparse, urljoin
from collections import deque
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(json.dumps([{
        "title": "Missing dependency for render-readability-audit",
        "severity": "low",
        "category": "discoverability",
        "skill_source": "render-readability-audit",
        "evidence": f"Required package not installed: {e}",
        "suggested_action": {
            "summary": "Install required packages: pip install requests beautifulsoup4 lxml",
            "priority": "low"
        }
    }]))
    sys.exit(0)

# Playwright is optional — degrade gracefully
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_RAW_CRAWL_PAGES = 15       # Pages to crawl for link discovery
MAX_PLAYWRIGHT_PAGES = 8       # Max pages to render (time budget)
REQUEST_TIMEOUT = 12
CRAWL_DELAY = 0.5
RENDER_GAP_HIGH_THRESHOLD = 30.0   # % — high severity
RENDER_GAP_MEDIUM_THRESHOLD = 15.0 # % — medium severity
PLAYWRIGHT_TIMEOUT = 20_000        # ms

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BrandAuditBot/1.0; "
        "+https://github.com/brand-ai-readiness-audit)"
    )
}

# Patterns that indicate key brand facts
KEY_FACT_PATTERNS = [
    r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",  # phone
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # email
    r"\$[\d,]+(?:\.\d{2})?",  # price USD
    r"€[\d,]+(?:\.\d{2})?",   # price EUR
    r"\b\d{5}(?:-\d{4})?\b",  # zip code
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def get_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def safe_get(url: str) -> Optional[requests.Response]:
    try:
        return requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except Exception:
        return None


def extract_visible_text_bs4(html: str) -> str:
    """Extract visible text from raw HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")
    # Remove non-visible elements
    for tag in soup(["script", "style", "head", "meta", "noscript", "template"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def tokenize(text: str) -> set[str]:
    """Split text into a set of lowercase word tokens (≥3 chars)."""
    import re
    words = re.findall(r"[a-z]{3,}", text.lower())
    return set(words)


def compute_render_gap(raw_text: str, rendered_text: str) -> float:
    """
    Returns the % of rendered words that are absent from raw HTML.
    Uses BOTH token-set overlap AND absolute word-count ratio.
    Token-set gap: what fraction of rendered vocabulary is completely absent from raw HTML.
    Absolute ratio: if raw has very few words but rendered has many, that is also a gap.
    Returns the higher of the two measures.
    """
    raw_tokens = tokenize(raw_text)
    rendered_tokens = tokenize(rendered_text)
    raw_words = len(raw_text.split())
    rendered_words = len(rendered_text.split())

    # Metric 1: token-set gap
    if rendered_tokens:
        missing = rendered_tokens - raw_tokens
        token_gap_pct = round(len(missing) / len(rendered_tokens) * 100, 1)
    else:
        token_gap_pct = 0.0

    # Metric 2: absolute word-count ratio gap
    # If raw has very few words (< 100) but rendered has many more,
    # the missing content gap = (rendered - raw) / rendered
    if rendered_words > 0 and raw_words < rendered_words:
        abs_gap_pct = round((rendered_words - raw_words) / rendered_words * 100, 1)
    else:
        abs_gap_pct = 0.0

    # Return the more sensitive metric
    return max(token_gap_pct, abs_gap_pct)


def extract_internal_links(html: str, base_url: str, current_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = urljoin(current_url, href).split("#")[0].rstrip("/")
        if abs_url.startswith(base_url) and abs_url != current_url:
            links.append(abs_url)
    return list(set(links))


def discover_pages(start_url: str, base_url: str, max_pages: int) -> list[str]:
    """BFS crawl to collect representative pages."""
    queue = deque([start_url])
    visited = {start_url}
    pages = [start_url]

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        time.sleep(CRAWL_DELAY)
        resp = safe_get(url)
        if resp and resp.status_code == 200:
            links = extract_internal_links(resp.text, base_url, url)
            for link in links:
                if link not in visited:
                    visited.add(link)
                    queue.append(link)
                    pages.append(link)
                    if len(pages) >= max_pages:
                        break
    return pages


def render_page_playwright(url: str, pw_context) -> Optional[tuple[str, str]]:
    """Render a page with Playwright. Returns (final_url, inner_text) or None."""
    page = None
    for wait_until in ("networkidle", "load"):
        try:
            page = pw_context.new_page()
            page.goto(url, wait_until=wait_until, timeout=PLAYWRIGHT_TIMEOUT)
            # Extra wait for any deferred JS rendering (max 3s)
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            final_url = page.url
            text = page.evaluate("document.body.innerText") or ""
            page.close()
            return (final_url, text)
        except Exception as exc:
            err_msg = str(exc)[:120]
            print(f"[render-readability] {wait_until} failed on {url}: {err_msg}", file=sys.stderr)
            try:
                if page:
                    page.close()
            except Exception:
                pass
            page = None
            if "networkidle" in wait_until:
                continue   # retry with 'load'
            return None
    return None

# ── Making findings ───────────────────────────────────────────────────────────

def making_finding(title, severity, evidence, action):
    return {
        "title": title,
        "severity": severity,
        "category": "discoverability",
        "skill_source": "render-readability-audit",
        "evidence": evidence,
        "suggested_action": {
            "summary": action,
            "priority": severity,
        },
    }

# ── Main audit logic ───────────────────────────────────────────────────────────

def run(url: str) -> list[dict]:
    """Run render-readability-audit and return list of findings."""
    url = normalize_url(url)
    base_url = get_base_url(url)
    findings = []

    if not PLAYWRIGHT_AVAILABLE:
        findings.append(making_finding(
            title="Playwright not available — render gap analysis skipped",
            severity="low",
            evidence=(
                "The 'playwright' Python package is not installed in this environment. "
                "JavaScript render gap analysis requires Playwright with headless Chromium. "
                "Raw HTML analysis only was performed."
            ),
            action=(
                "Install Playwright and Chromium: "
                "pip install playwright && playwright install chromium. "
                "Re-run to get full render gap analysis."
            ),
        ))
        # Fall back to basic raw HTML checks only
        resp = safe_get(url)
        if resp and resp.status_code == 200:
            raw_text = extract_visible_text_bs4(resp.text)
            raw_word_count = len(raw_text.split())
            if raw_word_count < 100:
                findings.append(making_finding(
                    title="Extremely low raw HTML word count suggests heavy client-side rendering",
                    severity="high",
                    evidence=(
                        f"Raw HTML of {url} contains only {raw_word_count} visible words. "
                        "Sites with fewer than 100 raw-HTML words typically require JS execution "
                        "to render their primary content — invisible to AI crawlers."
                    ),
                    action=(
                        "Implement Server-Side Rendering (SSR) or Static Site Generation (SSG) "
                        "so your primary content is present in the raw HTTP response. "
                        "Frameworks: Next.js (SSR/SSG), Nuxt (Vue), SvelteKit, Astro."
                    ),
                ))
        return findings

    # Discover pages to audit
    try:
        pages = discover_pages(url, base_url, MAX_RAW_CRAWL_PAGES)
    except Exception as exc:
        findings.append(making_finding(
            title="Page discovery failed in render-readability-audit",
            severity="low",
            evidence=f"Could not crawl pages for render gap analysis: {exc}",
            action="Check network connectivity and that the site is publicly accessible.",
        ))
        return findings

    # Select pages to render (prioritize homepage, then sample)
    render_targets = pages[:MAX_PLAYWRIGHT_PAGES]
    gap_results = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                ignore_https_errors=True,
            )
            for page_url in render_targets:
                time.sleep(CRAWL_DELAY)

                # Raw fetch
                raw_resp = safe_get(page_url)
                if not raw_resp or raw_resp.status_code != 200:
                    continue
                raw_text = extract_visible_text_bs4(raw_resp.text)
                raw_words = len(raw_text.split())

                # Rendered fetch
                result = render_page_playwright(page_url, context)
                if result is None:
                    continue
                final_url, rendered_text = result

                # If Playwright redirected to a different page (e.g. login),
                # use the raw fetch of the FINAL URL to get a fair raw baseline
                if final_url.rstrip("/") != page_url.rstrip("/"):
                    raw_resp2 = safe_get(final_url)
                    if raw_resp2 and raw_resp2.status_code == 200:
                        raw_text = extract_visible_text_bs4(raw_resp2.text)
                        raw_words = len(raw_text.split())
                rendered_words = len(rendered_text.split())

                gap_pct = compute_render_gap(raw_text, rendered_text)
                gap_results.append({
                    "url": page_url,
                    "raw_words": raw_words,
                    "rendered_words": rendered_words,
                    "gap_pct": gap_pct,
                })

                # Per-page finding
                if gap_pct >= RENDER_GAP_HIGH_THRESHOLD:
                    findings.append(making_finding(
                        title=f"{gap_pct}% of content on {urlparse(page_url).path or '/'} absent from raw HTML",
                        severity="high",
                        evidence=(
                            f"Raw HTML: {raw_words} words. "
                            f"Playwright-rendered: {rendered_words} words. "
                            f"Render gap: {gap_pct}% of rendered words absent from raw crawler view. "
                            f"Affected URL: {page_url}"
                        ),
                        action=(
                            "Implement SSR or SSG so content is in the initial HTML response. "
                            "At minimum, ensure product names, prices, and key facts appear in raw HTML. "
                            "Use Next.js getServerSideProps/getStaticProps or equivalent."
                        ),
                    ))
                elif gap_pct >= RENDER_GAP_MEDIUM_THRESHOLD:
                    findings.append(making_finding(
                        title=f"{gap_pct}% of content on {urlparse(page_url).path or '/'} requires JS to render",
                        severity="medium",
                        evidence=(
                            f"Raw HTML: {raw_words} words. "
                            f"Playwright-rendered: {rendered_words} words. "
                            f"Render gap: {gap_pct}%. Affected URL: {page_url}"
                        ),
                        action=(
                            "Review client-side-only components. Move key informational content "
                            "to server-rendered or static HTML."
                        ),
                    ))

            context.close()
            browser.close()

    except Exception as exc:
        findings.append(making_finding(
            title="Playwright rendering failed",
            severity="low",
            evidence=f"Playwright browser error: {type(exc).__name__}: {exc}",
            action="Ensure Chromium is installed: playwright install chromium",
        ))
        return findings

    # Summary finding if average gap is high
    if gap_results:
        avg_gap = round(sum(r["gap_pct"] for r in gap_results) / len(gap_results), 1)
        pages_above_threshold = sum(1 for r in gap_results if r["gap_pct"] >= RENDER_GAP_HIGH_THRESHOLD)
        if avg_gap >= RENDER_GAP_HIGH_THRESHOLD and pages_above_threshold > 1:
            findings.insert(0, making_finding(
                title=f"Site-wide average render gap of {avg_gap}% — heavily JS-dependent",
                severity="critical",
                evidence=(
                    f"Checked {len(gap_results)} pages. Average render gap: {avg_gap}%. "
                    f"{pages_above_threshold}/{len(gap_results)} pages have >30% content absent from raw HTML. "
                    "AI crawlers that do not execute JS will see a heavily degraded version of this site."
                ),
                action=(
                    "Prioritize migrating to SSR or SSG. This is the single highest-impact "
                    "change for AI discoverability on this site. "
                    "Consider Next.js, SvelteKit, Astro, or Remix."
                ),
            ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_render_gap.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
