#!/usr/bin/env python3
"""
crawl-access-audit/scripts/check_access.py

Checks whether AI crawlers and search bots can access a website.
Inspects robots.txt rules, HTTP status codes, redirect chains, and sitemap.xml.

Usage:
    python check_access.py <url>
    python check_access.py https://example.com

Returns JSON list of findings to stdout.
"""

import sys
import json
import time
import re
import urllib.robotparser
from urllib.parse import urlparse, urljoin
from collections import deque
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(json.dumps([{
        "title": "Missing dependency for crawl-access-audit",
        "severity": "low",
        "category": "discoverability",
        "skill_source": "crawl-access-audit",
        "evidence": f"Required package not installed: {e}. Install with: pip install requests beautifulsoup4",
        "suggested_action": {
            "summary": "Install required packages: pip install requests beautifulsoup4 lxml",
            "priority": "low"
        }
    }]))
    sys.exit(0)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_PAGES = 15
REQUEST_TIMEOUT = 12
CRAWL_DELAY = 0.5  # seconds between requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BrandAuditBot/1.0; "
        "+https://github.com/brand-ai-readiness-audit)"
    )
}

# AI and major search crawler user-agents to test against robots.txt
AI_CRAWLERS = [
    ("GPTBot", "OpenAI's GPT crawler"),
    ("ChatGPT-User", "ChatGPT browsing plugin"),
    ("Google-Extended", "Google AI training crawler"),
    ("PerplexityBot", "Perplexity AI crawler"),
    ("anthropic-ai", "Anthropic Claude crawler"),
    ("CCBot", "Common Crawl (used by many LLM training sets)"),
    ("Omgilibot", "Webz.io AI crawler"),
    ("Googlebot", "Google Search (baseline)"),
]

# Static fallback paths to check for disallow rules if dynamic discovery fails
STATIC_KEY_PATHS = ["/", "/products", "/blog", "/pricing", "/about", "/faq", "/shop"]
KEY_PATHS = STATIC_KEY_PATHS

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def get_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def safe_get(url: str, allow_redirects: bool = True) -> Optional[requests.Response]:
    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=allow_redirects,
        )
        return resp
    except Exception:
        return None


def get_redirect_chain(url: str) -> list[str]:
    """Follow redirects manually to measure chain length."""
    chain = []
    current = url
    visited = set()
    for _ in range(10):
        if current in visited:
            break
        visited.add(current)
        resp = safe_get(current, allow_redirects=False)
        if resp is None:
            break
        chain.append((current, resp.status_code))
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if not location:
                break
            if not location.startswith("http"):
                location = urljoin(current, location)
            current = location
        else:
            break
    return chain


def extract_internal_links(html: str, base_url: str, current_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        abs_url = urljoin(current_url, href).split("#")[0].rstrip("/")
        if abs_url.startswith(base_url):
            links.append(abs_url)
    return links


def extract_paths_from_sitemap(sitemap_url: str, base_url: str) -> list[str]:
    """Extract paths from an XML sitemap or sitemap index."""
    try:
        resp = safe_get(sitemap_url)
        if not resp or resp.status_code != 200:
            return []

        locs = re.findall(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", resp.text, re.IGNORECASE)
        # If this is a sitemap index (locs point to .xml files), follow the first child sitemap
        xml_locs = [l for l in locs if ".xml" in l.lower()]
        if xml_locs and ("<sitemapindex" in resp.text.lower() or len(xml_locs) == len(locs)):
            time.sleep(CRAWL_DELAY)
            sub_resp = safe_get(xml_locs[0])
            if sub_resp and sub_resp.status_code == 200:
                locs = re.findall(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", sub_resp.text, re.IGNORECASE)

        base_netloc = urlparse(base_url).netloc
        paths = set()
        for loc in locs:
            parsed = urlparse(loc)
            if not parsed.netloc or parsed.netloc == base_netloc:
                p = parsed.path.rstrip("/")
                if p:
                    paths.add(p)
                if len(paths) >= 15:
                    break

        if paths:
            paths.add("/")
            return sorted(list(paths))
    except Exception:
        pass
    return []


def extract_paths_from_homepage(base_url: str) -> list[str]:
    """Extract internal paths from links found on the homepage."""
    try:
        resp = safe_get(base_url)
        if resp and resp.status_code == 200:
            links = extract_internal_links(resp.text, base_url, base_url)
            paths = set()
            for link in links:
                p = urlparse(link).path.rstrip("/")
                if p:
                    paths.add(p)
                if len(paths) >= 15:
                    break
            if paths:
                paths.add("/")
                return sorted(list(paths))
    except Exception:
        pass
    return []


def discover_key_paths(base_url: str, robots_text: Optional[str] = None) -> list[str]:
    """
    Dynamically discover representative paths for robots.txt testing:
    1. First try sitemap.xml
    2. Fall back to links found on homepage
    3. Last-resort fallback to static list
    """
    # 1. First try sitemap.xml
    sitemap_url = None
    if robots_text:
        for line in robots_text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("sitemap:"):
                sitemap_url = stripped.split(":", 1)[1].strip()
                break

    if not sitemap_url:
        for candidate in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/sitemap.xml"]:
            resp = safe_get(base_url + candidate)
            if resp and resp.status_code == 200:
                sitemap_url = base_url + candidate
                break

    if sitemap_url:
        sitemap_paths = extract_paths_from_sitemap(sitemap_url, base_url)
        if len(sitemap_paths) > 1:
            return sitemap_paths

    # 2. Fall back to links on the homepage
    homepage_paths = extract_paths_from_homepage(base_url)
    if len(homepage_paths) > 1:
        return homepage_paths

    # 3. Last-resort fallback
    return STATIC_KEY_PATHS


def making_finding(title, severity, evidence, action, priority=None):
    return {
        "title": title,
        "severity": severity,
        "category": "discoverability",
        "skill_source": "crawl-access-audit",
        "evidence": evidence,
        "suggested_action": {
            "summary": action,
            "priority": priority or severity,
        },
    }

# ── Check functions ────────────────────────────────────────────────────────────

def audit_robots(base_url: str) -> tuple[list[dict], Optional[urllib.robotparser.RobotFileParser]]:
    findings = []
    robots_url = f"{base_url}/robots.txt"
    resp = safe_get(robots_url)

    if resp is None or resp.status_code != 200:
        status = resp.status_code if resp else "connection error"
        findings.append(making_finding(
            title="robots.txt not found or unreachable",
            severity="medium",
            evidence=(
                f"GET {robots_url} returned status {status}. "
                "Without a robots.txt, crawlers may apply conservative default policies."
            ),
            action=(
                "Create a robots.txt at the root of your domain. "
                "Explicitly allow all crawlers with 'User-agent: *\\nAllow: /' "
                "to signal openness to AI and search indexers."
            ),
        ))
        return findings, None

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    rp.parse(resp.text.splitlines())

    key_paths = discover_key_paths(base_url, robots_text=resp.text if resp else None)

    # Check AI crawler blocks
    blocked = []
    for agent, description in AI_CRAWLERS:
        blocked_paths = []
        for path in key_paths:
            test_url = base_url + path
            if not rp.can_fetch(agent, test_url):
                blocked_paths.append(path)
        if blocked_paths:
            blocked.append((agent, description, blocked_paths))

    if blocked:
        all_blocked_paths = [p for p in key_paths if any(p in bp for _, _, bp in blocked)]
        for _, _, bp in blocked:
            for p in bp:
                if p not in all_blocked_paths:
                    all_blocked_paths.append(p)

        bot_names = [agent for agent, _, _ in blocked]
        severity = "critical" if any("/" in bp for _, _, bp in blocked) else "high"
        bot_count = len(blocked)
        bot_label = f"{bot_count} AI crawler" if bot_count == 1 else f"{bot_count} AI crawlers"

        findings.append(making_finding(
            title=f"{bot_label} blocked by robots.txt",
            severity=severity,
            evidence=(
                f"robots.txt Disallow rules prevent {bot_label} ({', '.join(bot_names)}) "
                f"from accessing: {', '.join(all_blocked_paths)}."
            ),
            action=(
                f"Review the Disallow rules in robots.txt for the blocked AI crawlers ({', '.join(bot_names)}). "
                "If you want AI assistants to cite and summarize your content, remove or narrow these rules to allow "
                "access to key public pages, or add compensating Allow directives."
            ),
        ))

    return findings, rp


def audit_sitemap(base_url: str, rp: Optional[urllib.robotparser.RobotFileParser]) -> list[dict]:
    findings = []
    sitemap_url = None

    # 1. Check robots.txt Sitemap directive
    if rp:
        for line in (rp.entries or []):
            pass  # robotparser doesn't expose Sitemap directives cleanly
        # Re-parse raw robots.txt for Sitemap directive
        robots_url = f"{base_url}/robots.txt"
        resp = safe_get(robots_url)
        if resp and resp.status_code == 200:
            for line in resp.text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("sitemap:"):
                    sitemap_url = stripped.split(":", 1)[1].strip()
                    break

    # 2. Fallback to common paths
    if not sitemap_url:
        for candidate in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/sitemap.xml"]:
            time.sleep(CRAWL_DELAY)
            resp = safe_get(base_url + candidate)
            if resp and resp.status_code == 200:
                sitemap_url = base_url + candidate
                break

    if not sitemap_url:
        findings.append(making_finding(
            title="No sitemap.xml discoverable",
            severity="high",
            evidence=(
                f"Checked: {base_url}/sitemap.xml (404), {base_url}/sitemap_index.xml (404). "
                "robots.txt contains no Sitemap: directive. "
                "Without a sitemap, AI crawlers must rely entirely on link discovery."
            ),
            action=(
                "Generate an XML sitemap and host it at /sitemap.xml. "
                "Declare it in robots.txt with 'Sitemap: https://yourdomain.com/sitemap.xml'. "
                "Submit it to Google Search Console and Bing Webmaster Tools."
            ),
        ))
    return findings


def audit_http_status(start_url: str, base_url: str) -> list[dict]:
    findings = []
    queue = deque([start_url])
    visited = {start_url}
    page_statuses = []
    redirect_issues = []

    while queue and len(visited) <= MAX_PAGES:
        url = queue.popleft()
        time.sleep(CRAWL_DELAY)

        # Check redirect chain first
        chain = get_redirect_chain(url)
        if len(chain) > 2:
            redirect_issues.append({
                "url": url,
                "chain_length": len(chain),
                "chain": [f"{u} → {s}" for u, s in chain],
            })

        # Final status
        resp = safe_get(url)
        if resp is None:
            page_statuses.append((url, 0, "connection error"))
            continue

        page_statuses.append((url, resp.status_code, ""))

        if resp.status_code == 200:
            links = extract_internal_links(resp.text, base_url, url)
            for link in links:
                if link not in visited:
                    visited.add(link)
                    queue.append(link)

    # Findings: non-200 homepage
    homepage_status = next((s for u, s, _ in page_statuses if u == start_url), None)
    if homepage_status and homepage_status not in (200, 301, 302):
        findings.append(making_finding(
            title=f"Homepage returns HTTP {homepage_status}",
            severity="critical",
            evidence=f"GET {start_url} returned HTTP {homepage_status}. AI crawlers cannot index a site with a non-successful homepage.",
            action=f"Investigate the server error returning HTTP {homepage_status} at {start_url}. Ensure the homepage returns HTTP 200.",
        ))

    # Findings: redirect chains
    for ri in redirect_issues:
        findings.append(making_finding(
            title=f"Long redirect chain ({ri['chain_length']} hops) at {ri['url']}",
            severity="medium",
            evidence=(
                f"URL {ri['url']} requires {ri['chain_length']} redirect hops before resolving. "
                f"Chain: {' → '.join(str(x) for x in ri['chain'][:4])}."
            ),
            action=(
                "Consolidate redirect chains to a single hop (original → canonical). "
                "Each extra hop adds latency and risks crawler timeouts."
            ),
        ))

    return findings, page_statuses

# ── Main entry point ───────────────────────────────────────────────────────────

def run(url: str) -> list[dict]:
    """Run crawl-access-audit and return list of findings."""
    url = normalize_url(url)
    base_url = get_base_url(url)
    findings = []

    try:
        robot_findings, rp = audit_robots(base_url)
        findings.extend(robot_findings)
        time.sleep(CRAWL_DELAY)

        sitemap_findings = audit_sitemap(base_url, rp)
        findings.extend(sitemap_findings)
        time.sleep(CRAWL_DELAY)

        http_findings, _ = audit_http_status(url, base_url)
        findings.extend(http_findings)

    except Exception as exc:
        findings.append({
            "title": "crawl-access-audit encountered an unexpected error",
            "severity": "low",
            "category": "discoverability",
            "skill_source": "crawl-access-audit",
            "evidence": f"Unhandled exception: {type(exc).__name__}: {exc}",
            "suggested_action": {
                "summary": "Re-run the audit. If the error persists, check network connectivity.",
                "priority": "low",
            },
        })

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_access.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
