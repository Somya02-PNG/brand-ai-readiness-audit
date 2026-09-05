#!/usr/bin/env python3
"""
engagement-audit/scripts/check_engagement.py

Evaluates on-site visitor engagement signals: broken internal links,
dead-end pages, navigation depth, above-fold orientation cues,
and wayfinding elements (breadcrumbs, search).

Usage:
    python check_engagement.py <url>
    python check_engagement.py https://example.com

Returns JSON list of findings to stdout.
"""

import sys
import json
import re
import time
from urllib.parse import urlparse, urljoin
from collections import deque
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup, Tag
except ImportError as e:
    print(json.dumps([{
        "title": "Missing dependency for engagement-audit",
        "severity": "low",
        "category": "engagement",
        "skill_source": "engagement-audit",
        "evidence": f"Required package not installed: {e}",
        "suggested_action": {
            "summary": "Install required packages: pip install requests beautifulsoup4 lxml",
            "priority": "low"
        }
    }]))
    sys.exit(0)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_CRAWL_PAGES = 15
MAX_LINK_CHECK_PAGES = 80   # cap link status checks for time budget
REQUEST_TIMEOUT = 10
CRAWL_DELAY = 0.3           # tighter for link checking (read-only GETs)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BrandAuditBot/1.0; "
        "+https://github.com/brand-ai-readiness-audit)"
    )
}

# CTA keywords for above-fold detection
CTA_KEYWORDS = [
    "get started", "start free", "sign up", "signup", "try for free", "try free",
    "free trial", "buy now", "shop now", "order now", "add to cart",
    "learn more", "see how", "request demo", "book demo", "schedule demo",
    "contact us", "get in touch", "talk to us", "speak to", "reach out",
    "download", "get the app", "install", "watch demo", "see demo",
    "explore", "discover", "view plans", "see pricing",
]

BROKEN_PCT_CRITICAL = 20.0
BROKEN_PCT_HIGH = 10.0
BROKEN_PCT_MEDIUM = 5.0

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def get_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def safe_get(url: str, method: str = "get") -> Optional[requests.Response]:
    try:
        fn = getattr(requests, method)
        return fn(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    except Exception:
        return None


def safe_head(url: str) -> Optional[requests.Response]:
    """Use HEAD first; fall back to GET if server doesn't support HEAD."""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                             allow_redirects=True)
        if resp.status_code == 405:
            return safe_get(url)
        return resp
    except Exception:
        return None


def extract_internal_links(html: str, base_url: str, current_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        abs_url = urljoin(current_url, href).split("#")[0].rstrip("/")
        if abs_url.startswith(base_url) and abs_url != current_url:
            links.append(abs_url)
    return links   # duplicates preserved — count multiple links to same target


def measure_nav_depth(soup: BeautifulSoup) -> int:
    """Measure the maximum nesting depth of <ul>/<ol> inside <nav> elements."""
    max_depth = 0
    for nav in soup.find_all("nav"):
        depth = _ul_depth(nav, 0)
        max_depth = max(max_depth, depth)
    return max_depth


def _ul_depth(tag: Tag, current_depth: int) -> int:
    if not isinstance(tag, Tag):
        return current_depth
    max_child = current_depth
    for child in tag.children:
        if isinstance(child, Tag) and child.name in ("ul", "ol"):
            max_child = max(max_child, _ul_depth(child, current_depth + 1))
        elif isinstance(child, Tag):
            max_child = max(max_child, _ul_depth(child, current_depth))
    return max_child


def has_breadcrumb(soup: BeautifulSoup) -> bool:
    """Detect breadcrumb navigation by multiple heuristics."""
    # aria-label
    for nav in soup.find_all("nav"):
        aria = (nav.get("aria-label") or "").lower()
        if "breadcrumb" in aria:
            return True
    # class name containing breadcrumb
    for tag in soup.find_all(True):
        classes = " ".join(tag.get("class", [])).lower()
        if "breadcrumb" in classes:
            return True
    # structured data BreadcrumbList
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        if "BreadcrumbList" in (script.string or ""):
            return True
    # schema.org breadcrumb in itemtype
    for tag in soup.find_all(attrs={"itemtype": True}):
        if "BreadcrumbList" in tag.get("itemtype", ""):
            return True
    return False


def has_search(soup: BeautifulSoup) -> bool:
    """Detect site search input."""
    # <input type="search">
    if soup.find("input", {"type": "search"}):
        return True
    # role="search"
    if soup.find(attrs={"role": "search"}):
        return True
    # aria-label containing search
    for tag in soup.find_all(True):
        aria = (tag.get("aria-label") or "").lower()
        if "search" in aria:
            return True
    return False


def detect_above_fold_cta(html: str) -> bool:
    """
    Heuristic: check if any CTA-keyword link/button appears in the first
    25% of the HTML body content.
    """
    soup = BeautifulSoup(html, "lxml")
    body = soup.body
    if not body:
        return False
    body_html = str(body)
    cutoff = max(1, len(body_html) // 4)
    above_fold_html = body_html[:cutoff].lower()
    return any(kw in above_fold_html for kw in CTA_KEYWORDS)


def count_outbound_internal(html: str, base_url: str, current_url: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    count = 0
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        abs_url = urljoin(current_url, href).split("#")[0].rstrip("/")
        if abs_url.startswith(base_url) and abs_url != current_url:
            count += 1
    return count

# ── Making findings ───────────────────────────────────────────────────────────

def make_finding(title, severity, evidence, action):
    return {
        "title": title,
        "severity": severity,
        "category": "engagement",
        "skill_source": "engagement-audit",
        "evidence": evidence,
        "suggested_action": {
            "summary": action,
            "priority": severity,
        },
    }

# ── Main audit logic ───────────────────────────────────────────────────────────

def run(url: str) -> list[dict]:
    """Run engagement-audit and return list of findings."""
    url = normalize_url(url)
    base_url = get_base_url(url)
    findings = []

    # ── Phase 1: Crawl pages & collect all internal links ────────────────────
    queue = deque([url])
    visited_pages = {url}
    pages_html: dict[str, str] = {}
    all_internal_link_targets: list[str] = []  # (possibly duplicate)
    dead_end_pages: list[str] = []

    while queue and len(visited_pages) <= MAX_CRAWL_PAGES:
        current = queue.popleft()
        time.sleep(CRAWL_DELAY)
        resp = safe_get(current)
        if not resp or resp.status_code != 200:
            continue

        pages_html[current] = resp.text

        links_from_page = extract_internal_links(resp.text, base_url, current)
        unique_links_from_page = list(set(links_from_page))
        all_internal_link_targets.extend(links_from_page)

        if len(unique_links_from_page) == 0:
            dead_end_pages.append(current)

        for link in unique_links_from_page:
            if link not in visited_pages:
                visited_pages.add(link)
                queue.append(link)

    pages_crawled = len(pages_html)

    # ── Phase 2: Check broken internal links ─────────────────────────────────
    all_unique_targets = list(set(all_internal_link_targets))
    # Cap link checking
    links_to_check = all_unique_targets[:MAX_LINK_CHECK_PAGES]
    broken_links: list[tuple[str, int]] = []
    checked = 0

    for link in links_to_check:
        time.sleep(CRAWL_DELAY)
        resp = safe_head(link)
        status = resp.status_code if resp else 0
        if status in range(400, 600) or status == 0:
            broken_links.append((link, status))
        checked += 1

    total_checked = checked
    broken_count = len(broken_links)
    broken_pct = broken_count / max(total_checked, 1) * 100

    if broken_count > 0:
        broken_sample = [f"{link} (HTTP {status})" for link, status in broken_links[:10]]
        if broken_pct >= BROKEN_PCT_CRITICAL:
            severity = "critical"
        elif broken_pct >= BROKEN_PCT_HIGH:
            severity = "high"
        else:
            severity = "medium"
        findings.append(make_finding(
            title=f"{broken_count}/{total_checked} internal links are broken ({broken_pct:.1f}%)",
            severity=severity,
            evidence=(
                f"Checked {total_checked} unique internal link targets; "
                f"{broken_count} returned HTTP 4xx/5xx. "
                f"Sample broken URLs: {'; '.join(broken_sample)}."
            ),
            action=(
                "Set up 301 redirects for moved content. Delete or update links to removed pages. "
                "Add a link-checking step to your CI/CD pipeline (e.g., lychee, broken-link-checker). "
                "Configure your CMS to warn editors when linking to non-existent pages."
            ),
        ))

    # ── Phase 3: Dead-end pages ───────────────────────────────────────────────
    # Exclude homepage from dead-end check (it might be unusual)
    dead_ends_excluding_home = [p for p in dead_end_pages if p != url]
    if dead_ends_excluding_home and pages_crawled > 3:
        findings.append(make_finding(
            title=f"{len(dead_ends_excluding_home)} dead-end pages with no internal links",
            severity="medium",
            evidence=(
                f"The following crawled pages contain zero outbound internal links: "
                f"{'; '.join(dead_ends_excluding_home[:6])}. "
                "Dead-end pages trap visitors with no path forward, increasing bounce rate."
            ),
            action=(
                "Add navigation links, related content sections, or CTAs to every page. "
                "Minimum: a link back to the section index or homepage. "
                "Consider adding a 'Related articles' or 'You might also like' section."
            ),
        ))

    # ── Phase 4: Navigation depth (homepage) ──────────────────────────────────
    if url in pages_html:
        hp_soup = BeautifulSoup(pages_html[url], "lxml")
        nav_depth = measure_nav_depth(hp_soup)
        nav_present = bool(hp_soup.find("nav"))

        if not nav_present:
            findings.append(make_finding(
                title="No <nav> element on homepage",
                severity="high",
                evidence=(
                    f"Homepage ({url}) raw HTML contains no <nav> element. "
                    "Without semantic navigation markup, screen readers, bots, and "
                    "AI parsers cannot identify the site's navigation structure."
                ),
                action=(
                    "Wrap your main navigation in a <nav> element with aria-label='Main navigation'. "
                    "This is both an accessibility and SEO best practice."
                ),
            ))
        elif nav_depth > 3:
            findings.append(make_finding(
                title=f"Navigation is {nav_depth} levels deep — too complex",
                severity="medium",
                evidence=(
                    f"Homepage navigation has {nav_depth} nested <ul>/<li> levels. "
                    "Deeply nested navigation is hard for visitors to scan and for "
                    "AI models to parse as a site structure signal."
                ),
                action=(
                    "Flatten navigation to a maximum of 3 levels. "
                    "Move rarely-used deep links to footer or secondary navigation."
                ),
            ))

        # ── Phase 5: Above-fold orientation ──────────────────────────────────
        has_h1 = bool(hp_soup.find("h1"))
        if not has_h1:
            findings.append(make_finding(
                title="No <h1> heading on homepage",
                severity="high",
                evidence=(
                    f"Homepage ({url}) raw HTML contains 0 <h1> elements. "
                    "Without an H1, visitors and AI parsers cannot determine the page's primary topic "
                    "within the first few seconds."
                ),
                action=(
                    "Add a single, descriptive <h1> to the homepage that clearly states what the brand does "
                    "(e.g., 'AI-Powered Inventory Management for E-Commerce Brands'). "
                    "Keep it under 70 characters and make it human-scannable."
                ),
            ))

        has_cta = detect_above_fold_cta(pages_html[url])
        if not has_cta:
            findings.append(make_finding(
                title="No call-to-action detected above the fold on homepage",
                severity="medium",
                evidence=(
                    f"Scanned the first 25% of homepage ({url}) HTML body for CTA keywords "
                    f"({', '.join(CTA_KEYWORDS[:8])}...). None found in above-fold region. "
                    "Visitors arriving from AI assistant recommendations need an immediate next action."
                ),
                action=(
                    "Place a prominent CTA button/link in the hero section of the homepage. "
                    "Use action-oriented text (e.g., 'Start Free Trial', 'Get a Demo', 'Shop Now'). "
                    "Ensure it's visible without scrolling on desktop (above ~700px)."
                ),
            ))

        # ── Phase 6: Wayfinding elements ──────────────────────────────────────
        if pages_crawled >= 5:  # Only flag for multi-page sites
            breadcrumb_found = False
            search_found = False

            for page_url, page_html in pages_html.items():
                soup = BeautifulSoup(page_html, "lxml")
                if has_breadcrumb(soup):
                    breadcrumb_found = True
                if has_search(soup):
                    search_found = True
                if breadcrumb_found and search_found:
                    break

            if not breadcrumb_found:
                findings.append(make_finding(
                    title="No breadcrumb navigation found on any page",
                    severity="low",
                    evidence=(
                        f"Checked {pages_crawled} pages for breadcrumb patterns "
                        "(aria-label='breadcrumb', .breadcrumb class, BreadcrumbList JSON-LD, "
                        "itemtype BreadcrumbList). None found. "
                        "Breadcrumbs help visitors orient themselves and reduce bounce rate."
                    ),
                    action=(
                        "Add breadcrumb navigation to all non-homepage pages. "
                        "Also add BreadcrumbList JSON-LD for AI and search engine context. "
                        "Example: Home > Category > Product Name."
                    ),
                ))

            if not search_found:
                findings.append(make_finding(
                    title="No site search found",
                    severity="low",
                    evidence=(
                        f"Checked {pages_crawled} pages for <input type='search'> and role='search'. "
                        "None found. Visitors who don't immediately find what they need "
                        "and can't search are likely to leave."
                    ),
                    action=(
                        "Add a site search to your header or navigation. "
                        "Options: native CMS search, Algolia, or Google Custom Search Engine. "
                        "Use <input type='search'> and wrap in <form role='search'> for semantic markup."
                    ),
                ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_engagement.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
