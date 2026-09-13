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
        "evidence": f"Required package not installed: {e}",
        "suggested_action": {
            "summary": (
                "Install required python packages, "
                "populated from PyPI via requirements.txt, "
                "because missing audit dependencies prevent local execution of the crawler audit. "
                "Verify: python -c 'import requests, bs4'."
            ),
            "priority": "low",
        },
        "mechanism": "Missing audit dependencies prevent local evaluation of website crawl access rules.",
        "fix_effort": "low",
        "verification": "python -c 'import requests, bs4'",
    }]))
    sys.exit(0)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_PAGES = 20
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
    ("OAI-SearchBot", "OpenAI Search crawler"),
    ("ChatGPT-User", "ChatGPT browsing plugin"),
    ("PerplexityBot", "Perplexity AI crawler"),
    ("Perplexity-User", "Perplexity user browsing agent"),
    ("ClaudeBot", "Anthropic Claude crawler"),
    ("anthropic-ai", "Anthropic Claude crawler"),
    ("Claude-Web", "Claude web fetching agent"),
    ("Google-Extended", "Google AI training crawler"),
    ("CCBot", "Common Crawl (used by many LLM training sets)"),
    ("Bytespider", "ByteDance AI crawler"),
    ("Applebot-Extended", "Apple AI training crawler"),
    ("meta-externalagent", "Meta AI external crawler"),
    ("cohere-ai", "Cohere AI training crawler"),
    ("Omgilibot", "Webz.io AI crawler"),
    ("Googlebot", "Google Search (baseline)"),
]

# Static fallback paths to check for disallow rules if dynamic discovery fails
STATIC_KEY_PATHS = ["/", "/products", "/blog", "/pricing", "/about", "/faq", "/shop"]
KEY_PATHS = STATIC_KEY_PATHS

# ── Robots & Sitemap Helpers ──────────────────────────────────────────────────

def parse_robots_txt(robots_text: Optional[str], base_url: str = "https://example.com") -> urllib.robotparser.RobotFileParser:
    """Parse robots.txt content into a RobotFileParser instance. Returns all-allowed parser if robots_text is None."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{base_url.rstrip('/')}/robots.txt")
    if robots_text is not None:
        rp.parse(robots_text.splitlines())
    else:
        rp.allow_all = True
    return rp


def extract_sitemap_from_robots(robots_text: Optional[str]) -> Optional[str]:
    """Extract sitemap URL from robots.txt content if present."""
    if not robots_text:
        return None
    for line in robots_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            return stripped.split(":", 1)[1].strip()
    return None

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
        if resp is not None:
            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
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
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []

    links = []
    base_netloc = urlparse(base_url).netloc
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "")
        if not isinstance(href, str):
            continue
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            abs_url = urljoin(current_url, href).split("#")[0].rstrip("/")
            parsed_abs = urlparse(abs_url)
            if (not parsed_abs.netloc or parsed_abs.netloc == base_netloc) and abs_url.startswith(base_url):
                links.append(abs_url)
        except Exception:
            continue
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
    sitemap_url = extract_sitemap_from_robots(robots_text)

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


def is_botwall_or_cloudflare(resp: Optional[requests.Response]) -> bool:
    """Detect whether a response indicates Cloudflare or bot-management blocking (403/503)."""
    if resp is None:
        return False
    if resp.status_code in (403, 503):
        server = resp.headers.get("Server", "").lower()
        cf_ray = resp.headers.get("cf-ray", "")
        cf_mitigated = resp.headers.get("cf-mitigated", "")
        body_sample = (resp.text or "")[:2000].lower()
        if "cloudflare" in server or cf_ray or cf_mitigated:
            return True
        if any(sig in body_sample for sig in (
            "cloudflare", "just a moment...", "attention required",
            "cf-browser-verification", "ddos-guard", "bot detection",
            "access denied", "security service", "captcha", "challenge-platform"
        )):
            return True
        return True
    return False


def make_botwall_finding(url: str, status_code: int, server: str = "Cloudflare/bot-wall") -> dict:
    """Diagnostic finding emitted when Cloudflare or a bot-wall blocks automated access."""
    return making_finding(
        title="Automated access blocked — manual review needed",
        severity="low",
        evidence=(
            f"Automated access blocked — manual review needed: HTTP {status_code} detected from {server} protection at {url}. "
            "Bot management security rules may be intercepting automated crawlers."
        ),
        action=(
            f"Configure bot-management and WAF firewall allowlists, populated from your CDN or Cloudflare security rules, "
            "because strict bot-wall challenges block verified AI crawlers such as GPTBot and OAI-SearchBot from retrieving site content. "
            f"Verify: curl -sI -A 'GPTBot' {url} | grep -E 'HTTP/|cf-ray'."
        ),
        priority="low",
        mechanism="Cloudflare and WAF bot-walls intercept automated user-agents with 403/503 challenges, preventing AI search indexing.",
        fix_effort="medium",
        verification=f"curl -sI -A 'GPTBot' {url}",
    )


def making_finding(title, severity, evidence, action, priority=None, mechanism=None, fix_effort=None, verification=None):
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
        "mechanism": mechanism or "Search and AI crawlers cannot index, parse, or cite content that is blocked by HTTP errors or robots.txt directives.",
        "fix_effort": fix_effort or ("medium" if severity in ("critical", "high") else "low"),
        "verification": verification or "curl -sI <base_url>/robots.txt",
    }

# ── Check functions ────────────────────────────────────────────────────────────

def audit_robots(base_url: str) -> tuple[list[dict], Optional[urllib.robotparser.RobotFileParser]]:
    findings = []
    robots_url = f"{base_url}/robots.txt"
    resp = safe_get(robots_url)

    if resp is not None and is_botwall_or_cloudflare(resp):
        findings.append(make_botwall_finding(
            robots_url,
            resp.status_code,
            resp.headers.get("Server", "Cloudflare/bot-wall"),
        ))

    if resp is None or resp.status_code != 200:
        status = f"HTTP {resp.status_code}" if resp else "connection error"
        rp = parse_robots_txt(None, base_url)
        findings.append(making_finding(
            title="robots.txt not found or unreachable",
            severity="medium",
            evidence=(
                f"GET {robots_url} returned status {status} (treated as all allowed per crawler standards: no disallow rules apply). "
                "Without an explicit robots.txt, crawlers may apply conservative default policies."
            ),
            action=(
                f"Create a robots.txt file, populated from your domain root server configuration with 'User-agent: *\\nAllow: /', "
                "because AI crawlers such as GPTBot and PerplexityBot default to conservative crawl policies or skip sites when "
                f"robots.txt is unreachable. Verify: curl -sI {robots_url} | grep -E 'HTTP/|200'."
            ),
            mechanism="Unreachable robots.txt causes AI indexers to apply cautious crawl restrictions or completely avoid indexing.",
            fix_effort="low",
            verification=f"curl -sI {robots_url}",
        ))
        return findings, rp

    rp = parse_robots_txt(resp.text, base_url)

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
                f"Remove or narrow Disallow rules in robots.txt, populated from your domain root server configuration to allow key paths ({', '.join(all_blocked_paths[:3])}), "
                f"because AI search crawlers ({', '.join(bot_names[:3])}) strictly respect robots.txt and will completely exclude disallowed pages from citations. "
                f"Verify: curl -s {base_url}/robots.txt | grep -iE 'User-agent|Disallow'."
            ),
            mechanism="Explicit robots.txt disallow rules prohibit AI models and assistant crawlers from fetching, parsing, and citing content.",
            fix_effort="low",
            verification=f"curl -s {base_url}/robots.txt",
        ))

    return findings, rp


def audit_sitemap(base_url: str, rp: Optional[urllib.robotparser.RobotFileParser]) -> list[dict]:
    findings = []
    sitemap_url = None

    # 1. Check robots.txt Sitemap directive
    if rp:
        robots_url = f"{base_url}/robots.txt"
        resp = safe_get(robots_url)
        if resp and resp.status_code == 200:
            sitemap_url = extract_sitemap_from_robots(resp.text)

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
                f"Generate an XML sitemap at /sitemap.xml and declare it in robots.txt, populated from your CMS or build routing table, "
                "because AI crawlers operating under crawl depth limits rely on sitemaps to discover deep authoritative URLs. "
                f"Verify: curl -sI {base_url}/sitemap.xml | grep 'HTTP/'."
            ),
            mechanism="Without a discoverable sitemap, AI indexers fail to uncover deep product, article, and reference pages.",
            fix_effort="medium",
            verification=f"curl -sI {base_url}/sitemap.xml",
        ))
    return findings


def audit_llms_txt(base_url: str) -> list[dict]:
    """Check for the presence of /llms.txt at the site root."""
    findings = []
    llms_url = f"{base_url.rstrip('/')}/llms.txt"
    resp = safe_get(llms_url)

    # If the response status code is 200 and content is non-empty, llms.txt is present.
    # Do not emit the "missing" finding.
    if resp is not None and resp.status_code == 200 and resp.text.strip():
        return findings

    # Only emit the "No /llms.txt file found" finding when genuinely 404, non-200, or unreachable.
    status_info = f"HTTP {resp.status_code}" if resp else "unreachable"
    findings.append(making_finding(
        title="No /llms.txt file found at site root",
        severity="low",
        evidence=(
            f"GET {llms_url} returned {status_info}. "
            "/llms.txt is an emerging web convention (llmstxt.org) where sites publish "
            "a curated, structured markdown summary of their content and documentation for LLMs."
        ),
        action=(
            f"Consider publishing an /llms.txt Markdown summary file at site root, populated from your core brand documentation and product catalog, "
            "because emerging AI reasoning agents can use /llms.txt as an optimized digest of site capabilities, which may strengthen AI citation likelihood. "
            f"Verify: curl -sI {llms_url} | grep 'HTTP/'."
        ),
        mechanism="Publishing /llms.txt is a recommended emerging convention (llmstxt.org) that can help AI agents more efficiently summarise brand capabilities.",
        fix_effort="low",
        verification=f"curl -sI {llms_url}",
    ))

    return findings


def audit_http_status(start_url: str, base_url: str) -> list[dict]:
    findings = []
    queue = deque([start_url])
    visited = {start_url}
    page_statuses = []
    redirect_issues = []

    while queue and len(page_statuses) < MAX_PAGES:
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

        # Check for Cloudflare / bot-wall blocking
        if is_botwall_or_cloudflare(resp):
            if not any(f["title"] == "Automated access blocked — manual review needed" for f in findings):
                findings.append(make_botwall_finding(
                    url,
                    resp.status_code,
                    resp.headers.get("Server", "Cloudflare/bot-wall"),
                ))

        if resp.status_code == 200:
            links = extract_internal_links(resp.text, base_url, url)
            if len(links) > 100:
                if not any(f["title"].startswith("High internal link count") for f in findings):
                    findings.append(making_finding(
                        title="High internal link count (>100 links) — crawl capped at 20 fetches",
                        severity="low",
                        evidence=(
                            f"Page at {url} contains {len(links)} internal links (>100 links detected); "
                            "link fetches were capped at 20 to prevent excessive crawl load."
                        ),
                        action=(
                            f"Review navigation and link architecture on high-link pages, populated from page templates, "
                            "because dense pages with over 100 links can dilute PageRank and exhaust AI crawler budget. "
                            f"Verify: curl -s {url} | grep -c '<a '."
                        ),
                        priority="low",
                        mechanism="Pages with over 100 links dilute crawl budget and link equity, causing AI crawlers to truncate discovery before indexing deeper content.",
                        fix_effort="low",
                        verification=f"curl -s {url} | grep -c '<a '",
                    ))
            for link in links:
                if link not in visited and len(visited) < MAX_PAGES:
                    visited.add(link)
                    queue.append(link)

    # Findings: non-200 homepage
    homepage_status = next((s for u, s, _ in page_statuses if u == start_url), None)
    if homepage_status and homepage_status not in (200, 301, 302):
        findings.append(making_finding(
            title=f"Homepage returns HTTP {homepage_status}",
            severity="critical",
            evidence=f"GET {start_url} returned HTTP {homepage_status}. AI crawlers cannot index a site with a non-successful homepage.",
            action=(
                f"Fix the web server response code for the homepage, populated from your reverse proxy or web host routing configuration, "
                "because AI crawlers abort crawling when the root landing page returns an error or non-200 status. "
                f"Verify: curl -sI {start_url} | grep 'HTTP/'."
            ),
            mechanism="Non-successful HTTP status codes on the homepage halt AI bot exploration and lead to complete exclusion from citations.",
            fix_effort="medium",
            verification=f"curl -sI {start_url}",
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
                f"Consolidate redirect rules to point directly to the canonical target URL, populated from your web server redirect configuration, "
                "because redirect chains greater than 2 hops trigger crawler timeout limits and waste crawl budget. "
                f"Verify: curl -sIL {ri['url']} | grep -E 'HTTP/|Location:'."
            ),
            mechanism="Excessive redirect hops increase fetch latency and trigger crawler abort thresholds before content is indexed.",
            fix_effort="low",
            verification=f"curl -sIL {ri['url']}",
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

        llms_findings = audit_llms_txt(base_url)
        findings.extend(llms_findings)
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
                "summary": (
                    f"Review network connectivity and server permissions for {url}, populated from host infrastructure logs, "
                    "because intermittent network dropouts prevent AI crawlers from fetching page resources. "
                    f"Verify: python skills/crawl-access-audit/scripts/check_access.py {url}."
                ),
                "priority": "low",
            },
            "mechanism": "Unhandled network or runtime errors prevent automated audit analysis and crawler page retrieval.",
            "fix_effort": "low",
            "verification": f"python skills/crawl-access-audit/scripts/check_access.py {url}",
        })

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_access.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
