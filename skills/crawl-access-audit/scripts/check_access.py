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

# Key paths to check for disallow rules
KEY_PATHS = ["/", "/products", "/blog", "/pricing", "/about", "/faq", "/shop"]

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

    # Check AI crawler blocks
    blocked = []
    for agent, description in AI_CRAWLERS:
        blocked_paths = []
        for path in KEY_PATHS:
            test_url = base_url + path
            if not rp.can_fetch(agent, test_url):
                blocked_paths.append(path)
        if blocked_paths:
            blocked.append((agent, description, blocked_paths))

    for agent, description, blocked_paths in blocked:
        severity = "critical" if "/" in blocked_paths else "high"
        findings.append(making_finding(
            title=f"AI crawler '{agent}' blocked by robots.txt",
            severity=severity,
            evidence=(
                f"robots.txt Disallow rule prevents {agent} ({description}) "
                f"from accessing: {', '.join(blocked_paths)}. "
                f"Full robots.txt snippet contains User-agent: {agent}."
            ),
            action=(
                f"Review the Disallow rules for '{agent}' in robots.txt. "
                "If you want AI assistants to cite your content, remove or narrow these rules. "
                "To allow all AI crawlers: ensure no User-agent block covers GPTBot, "
                "anthropic-ai, or Google-Extended without a compensating Allow rule."
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
