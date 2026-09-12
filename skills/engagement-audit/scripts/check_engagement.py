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
            "summary": (
                "Install required python packages, "
                "populated from PyPI via requirements.txt, "
                "because missing audit dependencies prevent local execution of the engagement audit. "
                "Verify: python -c 'import requests, bs4'."
            ),
            "priority": "low",
        },
        "mechanism": "Missing audit dependencies prevent local evaluation of site navigation and user engagement paths.",
        "fix_effort": "low",
        "verification": "python -c 'import requests, bs4'",
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

def make_finding(title, severity, evidence, action, mechanism=None, fix_effort=None, verification=None):
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
        "mechanism": mechanism or "Navigation and layout friction prevents visitors arriving from AI assistant citations from engaging or converting.",
        "fix_effort": fix_effort or ("medium" if severity in ("critical", "high") else "low"),
        "verification": verification or "curl -sI <url>",
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
                "Implement 301 redirects or update href attributes for broken targets, populated from your server routing table or CMS content editor, "
                "because broken internal links dead-end AI crawler discovery loops and destroy conversion when referred visitors land on HTTP 404 pages. "
                "Verify: curl -sI <broken_url> returns HTTP 200 or 301."
            ),
            mechanism="Broken internal links strand visitors referred by AI assistants and waste crawler traversal budget.",
            fix_effort="medium",
            verification="curl -sI <broken_url>",
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
                "Add contextual navigation links and related content modules, populated from your site template components or related article feeds, "
                "because dead-end pages offer no forward pathways, causing visitors and crawlers to bounce immediately. "
                "Verify: curl -s <dead_end_url> | grep -c '<a href=' shows > 3 outbound links."
            ),
            mechanism="Pages lacking outbound links terminate visitor exploration sessions and prevent AI crawlers from continuing traversals.",
            fix_effort="low",
            verification="curl -s <dead_end_url> | grep -c '<a href='",
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
                    f"Wrap primary site navigation links in a semantic <nav aria-label='Main navigation'> element, populated from your header template layout, "
                    "because AI parser agents rely on semantic HTML5 landmarks to distinguish main navigational hierarchies from page body text. "
                    f"Verify: curl -s {url} | grep -i '<nav'."
                ),
                mechanism="Absence of semantic navigation elements hinders AI screen readers and bots from identifying site structure.",
                fix_effort="low",
                verification=f"curl -s {url} | grep -i '<nav'",
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
                    f"Flatten menu hierarchies to a maximum of 3 levels, populated from your navigation configuration or taxonomy manager, "
                    "because deep multi-tier menus overwhelm human users and exceed AI model link-extraction heuristics. "
                    f"Verify: curl -s {url} shows no <ul> nested deeper than 3 levels."
                ),
                mechanism="Overly deep navigation structures impede efficient bot traversal and user category discovery.",
                fix_effort="medium",
                verification=f"curl -s {url} | grep -c '<ul'",
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
                    f"Add a clear, descriptive <h1> heading above the fold, populated from brand positioning copy in the homepage hero section, "
                    "because AI answer extractors look for <h1> as the primary topic definition of the entire domain. "
                    f"Verify: curl -s {url} | grep -i '<h1'."
                ),
                mechanism="Missing H1 headings prevent AI summarizers from rapidly determining the core purpose and value proposition of the site.",
                fix_effort="low",
                verification=f"curl -s {url} | grep -i '<h1'",
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
                    f"Insert a prominent CTA button in the hero area, populated from your primary conversion goal (e.g. 'Get Started', 'Start Free Trial'), "
                    "because users arriving from AI recommendations need an immediate conversion pathway without scrolling. "
                    f"Verify: curl -s {url} contains an above-fold button or link with action text."
                ),
                mechanism="Absence of above-the-fold calls-to-action reduces user engagement and conversion from AI-directed traffic.",
                fix_effort="low",
                verification=f"curl -s {url} | grep -iE 'btn|button|cta'",
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
                        "Deploy breadcrumb navigation with BreadcrumbList JSON-LD, populated from your page hierarchy or CMS breadcrumb module, "
                        "because breadcrumb trails convey parent-child relationships essential for AI deep-link citations. "
                        "Verify: curl -s <subpage_url> | grep -i 'breadcrumb'."
                    ),
                    mechanism="Missing breadcrumbs obscure hierarchical site context for search indexers and increase page bounce rates.",
                    fix_effort="medium",
                    verification="curl -s <subpage_url> | grep -i 'breadcrumb'",
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
                        f"Add an accessible site search form with <input type='search'>, populated from your header navigation or search index backend, "
                        "because visitors who fail to immediately locate specific brand facts rely on search before bouncing. "
                        f"Verify: curl -s {url} | grep -i 'type=\"search\"'."
                    ),
                    mechanism="Without site search, visitors referred by AI assistants with specific queries quickly abandon the site.",
                    fix_effort="medium",
                    verification=f"curl -s {url} | grep -i 'type=\"search\"'",
                ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_engagement.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
