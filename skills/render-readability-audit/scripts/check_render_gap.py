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
MAX_PLAYWRIGHT_PAGES = 3       # Max pages to render (keeps worker within orchestrator time budget)
REQUEST_TIMEOUT = 12
CRAWL_DELAY = 0.5
RENDER_GAP_HIGH_THRESHOLD = 30.0   # % — high severity
RENDER_GAP_MEDIUM_THRESHOLD = 15.0 # % — medium severity
PLAYWRIGHT_TIMEOUT = 40_000        # ms — initial goto timeout
PLAYWRIGHT_RETRY_TIMEOUT = 55_000  # ms — extended retry after both networkidle & load fail

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

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


# Transient network error substrings that warrant a retry (not hard failures)
_TRANSIENT_NET_ERRORS = (
    "ConnectionError",
    "ConnectionReset",
    "RemoteDisconnected",
    "ChunkedEncodingError",
    "ReadTimeout",
)


def safe_get(url: str, retries: int = 3, backoff: float = 2.0) -> Optional[requests.Response]:
    """GET with automatic retry on transient network errors."""
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        except Exception as exc:
            err = str(exc)
            is_transient = any(t in err for t in _TRANSIENT_NET_ERRORS)
            if is_transient and attempt < retries:
                wait = backoff * attempt
                print(
                    f"[render-readability] safe_get transient error on {url} "
                    f"(attempt {attempt}/{retries}): {err[:80]}. Retrying in {wait}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            return None
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


# Cookie/consent banner selectors to try dismissing before reading innerText
_CONSENT_SELECTORS = [
    'button:has-text("Accept All")',
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("I Accept")',
    'button:has-text("Allow all")',
    '[id*="accept" i]',
    '[class*="cookie"] button',
    '#onetrust-accept-btn-handler',
    '[aria-label*="accept" i]',
]


def _dismiss_consent(page) -> None:
    """Attempt to click common cookie/consent banners. Silently ignores failures."""
    for selector in _CONSENT_SELECTORS:
        try:
            page.click(selector, timeout=2000)
            print(
                f"[render-readability] Dismissed consent banner with selector: {selector}",
                file=sys.stderr,
            )
            break  # stop after first successful click
        except Exception:
            continue


def render_page_playwright(url: str, pw_context, extra_wait_ms: int = 0) -> Optional[tuple[str, str]]:
    """Render a page with Playwright. Returns (final_url, inner_text) or None."""

    def _try_goto(page, wait_until: str, timeout_ms: int) -> bool:
        """Attempt page.goto and return True on success. Handles ERR_NETWORK_CHANGED by
        waiting 3 s and retrying once, since this is a transient local-network blip."""
        for net_attempt in range(2):  # first try + one network-error retry
            try:
                page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                return True
            except Exception as exc:
                err = str(exc)
                if "ERR_NETWORK_CHANGED" in err and net_attempt == 0:
                    print(
                        f"[render-readability] ERR_NETWORK_CHANGED on {url} "
                        f"(wait_until={wait_until}). Waiting 3s for network to stabilise...",
                        file=sys.stderr,
                    )
                    time.sleep(3)
                    continue  # retry same wait_until after brief pause
                # Genuine timeout or unrecoverable error
                raise
        return False  # unreachable but satisfies type checker

    def _read_text(page, extra_wait_ms: int) -> str:
        """Dismiss consent banners, wait, then return document.body.innerText."""
        _dismiss_consent(page)
        # Wait 2 s after dismissal for any re-render triggered by consent acceptance
        try:
            page.wait_for_timeout(2000)
        except Exception:
            pass
        if extra_wait_ms > 0:
            try:
                page.wait_for_timeout(extra_wait_ms)
            except Exception:
                pass
        return page.evaluate("document.body.innerText") or ""

    page = None
    for wait_until in ("networkidle", "load"):
        try:
            page = pw_context.new_page()
            _try_goto(page, wait_until, PLAYWRIGHT_TIMEOUT)
            # Extra wait for any deferred JS rendering (max 3s)
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            final_url = page.url
            text = _read_text(page, extra_wait_ms)
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

    # If networkidle AND load both failed, retry once with a longer timeout
    print(
        f"[render-readability] Both networkidle and load failed on {url} at {PLAYWRIGHT_TIMEOUT}ms. "
        f"Increasing timeout to {PLAYWRIGHT_RETRY_TIMEOUT}ms and retrying once...",
        file=sys.stderr,
    )
    try:
        page = pw_context.new_page()
        _try_goto(page, "load", PLAYWRIGHT_RETRY_TIMEOUT)
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        final_url = page.url
        text = _read_text(page, extra_wait_ms)
        page.close()
        return (final_url, text)
    except Exception as exc:
        err_msg = str(exc)[:120]
        print(f"[render-readability] retry (load, {PLAYWRIGHT_RETRY_TIMEOUT}ms) failed on {url}: {err_msg}", file=sys.stderr)
        try:
            if page:
                page.close()
        except Exception:
            pass
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
    timed_out_urls: list[str] = []     # pages that failed after all retries
    inconclusive_urls: list[str] = []  # pages where rendered ratio < 20% of raw (SPA gating)

    # Ratio threshold: if rendered_words < this fraction of raw_words, the page
    # is likely behind a JS gate/consent wall and render data is not usable.
    RENDER_RATIO_INCONCLUSIVE = 0.20

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=BROWSER_USER_AGENT,
                viewport={"width": 1280, "height": 800},
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
                    # Hard timeout / full failure even after the 55s retry inside render_page_playwright
                    timed_out_urls.append(page_url)
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

                # Log rendered/raw ratio for every page (useful for debugging)
                ratio = rendered_words / raw_words if raw_words > 0 else 1.0
                print(
                    f"[render-readability] {page_url}: rendered={rendered_words} raw={raw_words} "
                    f"ratio={ratio:.2%}",
                    file=sys.stderr,
                )

                # If rendered_words < raw_words, extraction was likely incomplete/premature.
                # Attempt a 5s-wait retry to let JS fully hydrate.
                if rendered_words < raw_words:
                    print(
                        f"[render-readability] rendered_words ({rendered_words}) < raw_words ({raw_words}) "
                        f"on {page_url}. Retrying with 5000ms wait...",
                        file=sys.stderr,
                    )
                    retry_result = render_page_playwright(page_url, context, extra_wait_ms=5000)
                    if retry_result is not None:
                        retry_final_url, retry_rendered_text = retry_result
                        retry_rendered_words = len(retry_rendered_text.split())
                        if retry_final_url.rstrip("/") != page_url.rstrip("/"):
                            raw_resp2 = safe_get(retry_final_url)
                            if raw_resp2 and raw_resp2.status_code == 200:
                                raw_text = extract_visible_text_bs4(raw_resp2.text)
                                raw_words = len(raw_text.split())
                        if retry_rendered_words >= rendered_words:
                            rendered_text = retry_rendered_text
                            rendered_words = retry_rendered_words
                            ratio = rendered_words / raw_words if raw_words > 0 else 1.0
                            print(
                                f"[render-readability] After retry: rendered={rendered_words} "
                                f"raw={raw_words} ratio={ratio:.2%}",
                                file=sys.stderr,
                            )

                # After all retries: check the rendered/raw ratio.
                # < 20% → inconclusive (likely JS-gated / consent-walled)
                # ≥ 20% → compute render gap and include in gap_results
                if raw_words > 0 and (rendered_words / raw_words) < RENDER_RATIO_INCONCLUSIVE:
                    print(
                        f"[render-readability] Render inconclusive for {page_url}: "
                        f"rendered {rendered_words} words = {ratio:.1%} of raw {raw_words} words "
                        f"(< {RENDER_RATIO_INCONCLUSIVE:.0%} threshold). Marking as inconclusive.",
                        file=sys.stderr,
                    )
                    inconclusive_urls.append(page_url)
                    continue

                gap_pct = compute_render_gap(raw_text, rendered_text)
                gap_results.append({
                    "url": page_url,
                    "raw_words": raw_words,
                    "rendered_words": rendered_words,
                    "gap_pct": gap_pct,
                })

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

    # ── Inconclusive pages (rendered ratio < 20% of raw) ──────────────────────
    # Emit ONE per-site finding — never one per page.
    if inconclusive_urls:
        n = len(inconclusive_urls)
        url_list = "\n".join(f"  - {u}" for u in inconclusive_urls)
        findings.append(making_finding(
            title=f"Render check inconclusive for {n} page{'s' if n != 1 else ''} — possible JS gate or consent wall",
            severity="low",
            evidence=(
                f"After consent-banner dismissal and extended waits, {n} page(s) returned rendered text "
                f"that was less than {int(RENDER_RATIO_INCONCLUSIVE * 100)}% of the raw-HTML word count. "
                "This typically means content is behind a JavaScript gate, cookie-consent paywall, or "
                "login wall that automated rendering cannot reliably pass. "
                f"Render-gap analysis could not run for these pages:\n{url_list}"
            ),
            action=(
                "Ensure primary page content is accessible without requiring JavaScript interaction, "
                "login, or cookie acceptance. AI crawlers and search bots may not execute JS or accept "
                "consent prompts, making this content invisible to them."
            ),
        ))
        if not gap_results and not timed_out_urls:
            return findings

    # ── Timed-out pages ───────────────────────────────────────────────────────
    if timed_out_urls:
        n = len(timed_out_urls)
        url_list = "\n".join(f"  - {u}" for u in timed_out_urls)
        findings.append(making_finding(
            title=f"Render check blocked/unreachable for {n} page{'s' if n != 1 else ''}",
            severity="low",
            evidence=(
                f"Playwright attempted to render {n} page(s) but every attempt timed out or "
                f"failed to load even after extended retries "
                f"(initial timeout: {PLAYWRIGHT_TIMEOUT // 1000}s, "
                f"retry timeout: {PLAYWRIGHT_RETRY_TIMEOUT // 1000}s). "
                f"Affected URLs:\n{url_list}\n"
                "This may indicate bot-detection, a WAF challenge, or extreme page latency. "
                "Render-gap analysis was skipped for these pages."
            ),
            action=(
                "Verify the affected pages load in a standard browser. "
                "If bot management (e.g. Cloudflare, Akamai) is active, ensure legitimate "
                "AI crawler user-agents are not blocked or challenged."
            ),
        ))
        # If ALL pages timed out, no gap data at all — return early.
        if not gap_results:
            return findings

    # Evaluate render gaps
    gap_pages = [r for r in gap_results if r["gap_pct"] >= RENDER_GAP_MEDIUM_THRESHOLD]

    if len(gap_pages) > 2:
        avg_gap = round(sum(r["gap_pct"] for r in gap_pages) / len(gap_pages), 1)
        any_high = any(r["gap_pct"] >= RENDER_GAP_HIGH_THRESHOLD for r in gap_pages)
        sev = "critical" if avg_gap >= RENDER_GAP_HIGH_THRESHOLD else ("high" if any_high else "medium")
        evidence_lines = [
            f"{len(gap_pages)} pages show significant content missing from the raw HTML response that requires JavaScript execution to render:"
        ]
        for r in gap_pages:
            evidence_lines.append(
                f"- {r['url']}: {r['gap_pct']}% gap (raw: {r['raw_words']} words, rendered: {r['rendered_words']} words)"
            )
        findings.append(making_finding(
            title=f"{len(gap_pages)} pages show significant JS-render gaps (avg {avg_gap}%)",
            severity=sev,
            evidence="\n".join(evidence_lines),
            action=(
                "Implement Server-Side Rendering (SSR) or Static Site Generation (SSG) so content is present "
                "in the initial HTML response across these pages. At minimum, ensure product names, descriptions, "
                "pricing, and primary navigation appear in raw HTML."
            ),
        ))
    else:
        for r in gap_pages:
            page_url = r["url"]
            gap_pct = r["gap_pct"]
            raw_words = r["raw_words"]
            rendered_words = r["rendered_words"]
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
            else:
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

    # Summary finding if site-wide average gap is high (when not already consolidated)
    if len(gap_pages) <= 2 and gap_results:
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
