#!/usr/bin/env python3
"""
freshness-corroboration-audit/scripts/check_freshness.py

Validates internal fact consistency (address, phone, email, prices)
across multiple pages and checks for content freshness signals.

Usage:
    python check_freshness.py <url>
    python check_freshness.py https://example.com

Returns JSON list of findings to stdout.
"""

import sys
import json
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urljoin
from collections import deque, defaultdict
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(json.dumps([{
        "title": "Missing dependency for freshness-corroboration-audit",
        "severity": "low",
        "category": "discoverability",
        "skill_source": "freshness-corroboration-audit",
        "evidence": f"Required package not installed: {e}",
        "suggested_action": {
            "summary": "Install required packages: pip install requests beautifulsoup4 lxml",
            "priority": "low"
        }
    }]))
    sys.exit(0)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_PAGES = 15
REQUEST_TIMEOUT = 12
CRAWL_DELAY = 0.5
STALE_THRESHOLD_DAYS = 365  # Content older than this is considered stale

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BrandAuditBot/1.0; "
        "+https://github.com/brand-ai-readiness-audit)"
    )
}

# Priority paths for fact extraction
PRIORITY_PATHS = ["/contact", "/about", "/about-us", "/company", "/pricing",
                  "/faq", "/help", "/support", "/location", "/store"]

# ── Regex patterns for fact extraction ────────────────────────────────────────

PHONE_PATTERNS = [
    # +1-XXX-XXX-XXXX, +1 (XXX) XXX-XXXX, etc.
    re.compile(r"\+?1?\s*[-.]?\s*\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"),
    # International: +XX XXXX XXXX
    re.compile(r"\+\d{1,3}[\s.-]\d{3,4}[\s.-]\d{3,4}(?:[\s.-]\d{3,4})?"),
]

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Street address: number + street name (basic heuristic)
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-zA-Z\s]{2,30}(?:St(?:reet)?|Ave(?:nue)?|Blvd|Dr(?:ive)?|"
    r"Rd|Road|Ln|Lane|Way|Ct|Court|Pl(?:ace)?|Pkwy|Parkway|Hwy|Highway)\b"
)

ZIP_PATTERN = re.compile(r"\b\d{5}(?:-\d{4})?\b")

PRICE_PATTERN = re.compile(
    r"(?:USD\s*|EUR\s*|GBP\s*)?\$\s*[\d,]+(?:\.\d{2})?|€\s*[\d,]+(?:\.\d{2})?|£\s*[\d,]+(?:\.\d{2})?"
)

# Date patterns in meta/JSON-LD
DATE_META_NAMES = [
    "article:modified_time",
    "article:published_time",
    "og:updated_time",
    "dateModified",
    "datePublished",
    "last-modified",
    "date",
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


def normalize_phone(raw: str) -> str:
    """Strip non-digit characters for comparison."""
    digits = re.sub(r"\D", "", raw)
    # Strip leading country code 1 for North American numbers
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_price(raw: str) -> str:
    return re.sub(r"[,\s]", "", raw.strip())


def extract_facts_from_page(html: str, page_url: str) -> dict:
    """Extract all fact types from a page's HTML and JSON-LD."""
    soup = BeautifulSoup(html, "lxml")
    visible_text = soup.get_text(separator=" ", strip=True)

    phones = set()
    emails = set()
    addresses = set()
    prices = set()

    # Extract from visible text
    for pat in PHONE_PATTERNS:
        for m in pat.finditer(visible_text):
            normalized = normalize_phone(m.group())
            if len(normalized) >= 7:
                phones.add(normalized)

    for m in EMAIL_PATTERN.finditer(visible_text):
        email = m.group().lower()
        # Filter out common placeholder/example emails
        if not any(placeholder in email for placeholder in ["example.", "test@", "user@"]):
            emails.add(email)

    for m in ADDRESS_PATTERN.finditer(visible_text):
        addresses.add(m.group().strip())

    for m in PRICE_PATTERN.finditer(visible_text):
        prices.add(normalize_price(m.group()))

    # Also extract from JSON-LD
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        raw = script.string or ""
        try:
            data = json.loads(raw)
            _extract_jsonld_facts(data, phones, emails, addresses)
        except json.JSONDecodeError:
            pass

    return {
        "url": page_url,
        "phones": phones,
        "emails": emails,
        "addresses": addresses,
        "prices": prices,
    }


def _extract_jsonld_facts(data, phones: set, emails: set, addresses: set):
    """Recursively pull facts from JSON-LD data."""
    if isinstance(data, list):
        for item in data:
            _extract_jsonld_facts(item, phones, emails, addresses)
    elif isinstance(data, dict):
        if "telephone" in data:
            normalized = normalize_phone(str(data["telephone"]))
            if len(normalized) >= 7:
                phones.add(normalized)
        if "email" in data:
            emails.add(str(data["email"]).lower())
        if "address" in data:
            addr = data["address"]
            if isinstance(addr, dict):
                parts = [
                    addr.get("streetAddress", ""),
                    addr.get("addressLocality", ""),
                    addr.get("addressRegion", ""),
                    addr.get("postalCode", ""),
                ]
                full = " ".join(p for p in parts if p).strip()
                if full:
                    addresses.add(full)
            elif isinstance(addr, str):
                addresses.add(addr.strip())
        for v in data.values():
            if isinstance(v, (dict, list)):
                _extract_jsonld_facts(v, phones, emails, addresses)


def extract_dates_from_page(html: str, page_url: str) -> list[str]:
    """Extract all date signals from JSON-LD and meta tags."""
    soup = BeautifulSoup(html, "lxml")
    dates = []

    # JSON-LD dates
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        raw = script.string or ""
        try:
            data = json.loads(raw)
            _extract_jsonld_dates(data, dates)
        except json.JSONDecodeError:
            pass

    # Meta tags
    for name in DATE_META_NAMES:
        tag = soup.find("meta", {"name": name}) or soup.find("meta", {"property": name})
        if tag and tag.get("content"):
            dates.append(tag["content"])

    return dates


def _extract_jsonld_dates(data, dates: list):
    if isinstance(data, list):
        for item in data:
            _extract_jsonld_dates(item, dates)
    elif isinstance(data, dict):
        for key in ["dateModified", "datePublished", "dateCreated"]:
            if key in data and data[key]:
                dates.append(str(data[key]))
        for v in data.values():
            if isinstance(v, (dict, list)):
                _extract_jsonld_dates(v, dates)


def parse_date(date_str: str) -> Optional[datetime]:
    """Try parsing various ISO date formats."""
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]:
        try:
            dt = datetime.strptime(date_str[:19], fmt[:len(fmt)])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def discover_pages(start_url: str, base_url: str) -> list[str]:
    """BFS crawl prioritizing contact/about/pricing pages."""
    queue = deque([start_url])
    visited = {start_url}
    pages = [start_url]

    # Add priority paths directly
    for path in PRIORITY_PATHS:
        candidate = base_url + path
        if candidate not in visited:
            visited.add(candidate)
            resp = safe_get(candidate)
            time.sleep(CRAWL_DELAY)
            if resp and resp.status_code == 200:
                pages.append(candidate)

    # BFS for remaining pages
    while queue and len(pages) < MAX_PAGES:
        url = queue.popleft()
        time.sleep(CRAWL_DELAY)
        resp = safe_get(url)
        if resp and resp.status_code == 200:
            links = extract_internal_links(resp.text, base_url, url)
            for link in links:
                if link not in visited:
                    visited.add(link)
                    queue.append(link)
                    if len(pages) < MAX_PAGES:
                        pages.append(link)

    return list(dict.fromkeys(pages))  # deduplicate preserving order

# ── Making findings ───────────────────────────────────────────────────────────

def make_finding(title, severity, evidence, action):
    return {
        "title": title,
        "severity": severity,
        "category": "discoverability",
        "skill_source": "freshness-corroboration-audit",
        "evidence": evidence,
        "suggested_action": {
            "summary": action,
            "priority": severity,
        },
    }

# ── Main audit logic ───────────────────────────────────────────────────────────

def run(url: str) -> list[dict]:
    """Run freshness-corroboration-audit and return list of findings."""
    url = normalize_url(url)
    base_url = get_base_url(url)
    findings = []

    try:
        pages = discover_pages(url, base_url)
    except Exception as exc:
        return [make_finding(
            "freshness-corroboration-audit page discovery failed",
            "low",
            f"Could not crawl pages: {exc}",
            "Check network connectivity.",
        )]

    # Collect facts and dates per page
    all_facts = []
    all_dates = []

    for page_url in pages:
        time.sleep(CRAWL_DELAY)
        resp = safe_get(page_url)
        if not resp or resp.status_code != 200:
            continue

        facts = extract_facts_from_page(resp.text, page_url)
        all_facts.append(facts)

        dates = extract_dates_from_page(resp.text, page_url)
        all_dates.extend(dates)

    # ── Fact consistency analysis ──────────────────────────────────────────────

    # Aggregate facts by type across all pages
    all_phones: dict[str, list[str]] = defaultdict(list)   # normalized → [url...]
    all_emails: dict[str, list[str]] = defaultdict(list)
    all_addresses: dict[str, list[str]] = defaultdict(list)

    for facts in all_facts:
        pu = facts["url"]
        for phone in facts["phones"]:
            all_phones[phone].append(pu)
        for email in facts["emails"]:
            all_emails[email].append(pu)
        for addr in facts["addresses"]:
            all_addresses[addr].append(pu)

    # Phone inconsistency
    if len(all_phones) > 1:
        # Only flag if multiple distinct values appear on *different* pages
        phone_summary = "; ".join(
            f"'{p}' on {len(urls)} page(s): {', '.join(urls[:3])}"
            for p, urls in sorted(all_phones.items())
        )
        findings.append(make_finding(
            title=f"Phone number inconsistency — {len(all_phones)} distinct values across pages",
            severity="high",
            evidence=(
                f"Found {len(all_phones)} different phone numbers across {len(pages)} pages. "
                f"Details: {phone_summary}. "
                "Inconsistent contact info causes AI models to distrust the site's data."
            ),
            action=(
                "Standardize the phone number in a single CMS variable or component. "
                "Use E.164 format (e.g., +1-800-555-0100) in JSON-LD 'telephone' field. "
                "Ensure all page templates reference the same source of truth."
            ),
        ))

    # Email inconsistency
    if len(all_emails) > 2:  # Allow a couple (info@ and support@, etc.)
        email_summary = ", ".join(f"'{e}'" for e in list(all_emails.keys())[:6])
        findings.append(make_finding(
            title=f"Multiple distinct email addresses ({len(all_emails)}) found across site",
            severity="medium",
            evidence=(
                f"Found {len(all_emails)} distinct email addresses: {email_summary}. "
                "While multiple emails may be intentional, excessive variety can confuse AI knowledge graphs."
            ),
            action=(
                "Confirm these email addresses are all intentional. "
                "For primary contact, use a single canonical email in Organization JSON-LD 'email' field."
            ),
        ))

    # Address inconsistency (strict — any difference is a problem)
    if len(all_addresses) > 1:
        # Group very similar addresses (handle minor variations)
        addr_list = sorted(all_addresses.keys())
        addr_summary = "; ".join(
            f"'{a}' on: {', '.join(all_addresses[a][:2])}"
            for a in addr_list[:4]
        )
        findings.append(make_finding(
            title=f"Physical address inconsistency — {len(all_addresses)} variants found",
            severity="high",
            evidence=(
                f"Found {len(all_addresses)} distinct address strings across pages. "
                f"Details: {addr_summary}. "
                "Address inconsistency is a strong negative signal for AI confidence in local business data."
            ),
            action=(
                "Standardize your address in a single CMS variable. "
                "Use a structured address in Organization/LocalBusiness JSON-LD with: "
                "streetAddress, addressLocality, addressRegion, postalCode, addressCountry."
            ),
        ))

    # ── Freshness analysis ─────────────────────────────────────────────────────

    pages_checked = len(all_facts)
    if pages_checked == 0:
        return findings

    if not all_dates:
        findings.append(make_finding(
            title="No content freshness signals found on any page",
            severity="high",
            evidence=(
                f"Checked {pages_checked} pages. "
                "0 pages contain dateModified, datePublished (JSON-LD), "
                "article:modified_time, or og:updated_time (meta tags). "
                "AI crawlers cannot determine whether this site's content is current."
            ),
            action=(
                "Add datePublished and dateModified to all Article/BlogPosting JSON-LD. "
                "Add <meta property='article:modified_time' content='...ISO date...'> to all content pages. "
                "Include <lastmod> dates in your sitemap.xml."
            ),
        ))
    else:
        # Check for stale dates
        now = datetime.now(timezone.utc)
        parsed_dates = [(d, parse_date(d)) for d in all_dates]
        valid_dates = [(raw, dt) for raw, dt in parsed_dates if dt is not None]

        if valid_dates:
            latest = max(dt for _, dt in valid_dates)
            days_since = (now - latest).days

            if days_since > STALE_THRESHOLD_DAYS:
                findings.append(make_finding(
                    title=f"Most recent freshness date is {days_since} days old",
                    severity="medium",
                    evidence=(
                        f"Most recent dateModified/datePublished found: {latest.date().isoformat()} "
                        f"({days_since} days ago). "
                        f"Found {len(valid_dates)} date signals total across {pages_checked} pages. "
                        "AI assistants may prefer fresher sources when multiple are available."
                    ),
                    action=(
                        "Update dateModified in JSON-LD whenever page content changes. "
                        "Consider a content refresh strategy to keep key pages updated at least annually."
                    ),
                ))

        pages_with_dates = len(set(d for d in all_dates if d))
        if pages_with_dates < pages_checked // 2:
            findings.append(make_finding(
                title=f"Freshness signals missing on {pages_checked - pages_with_dates}/{pages_checked} pages",
                severity="medium",
                evidence=(
                    f"Only {pages_with_dates}/{pages_checked} crawled pages have any date metadata. "
                    "Pages without freshness signals are harder for AI models to date-rank."
                ),
                action=(
                    "Systematically add dateModified to all page types, not just blog posts. "
                    "Even static pages (About, Pricing) should declare a dateModified when updated."
                ),
            ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_freshness.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
