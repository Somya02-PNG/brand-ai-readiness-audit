#!/usr/bin/env python3
"""
entity-clarity-audit/scripts/check_entity.py

Checks whether a brand has sufficient disambiguating identity signals:
sameAs links, legalName, About page quality, and external identifiers.

Usage:
    python check_entity.py <url>
    python check_entity.py https://example.com

Returns JSON list of findings to stdout.
"""

import sys
import json
import re
import time
from urllib.parse import urlparse, urljoin
from collections import deque
from typing import Optional, Any

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(json.dumps([{
        "title": "Missing dependency for entity-clarity-audit",
        "severity": "low",
        "category": "discoverability",
        "skill_source": "entity-clarity-audit",
        "evidence": f"Required package not installed: {e}",
        "suggested_action": {
            "summary": "Install required packages: pip install requests beautifulsoup4 lxml",
            "priority": "low"
        }
    }]))
    sys.exit(0)

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_PAGES = 12
REQUEST_TIMEOUT = 12
CRAWL_DELAY = 0.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BrandAuditBot/1.0; "
        "+https://github.com/brand-ai-readiness-audit)"
    )
}

# Known identity/authority platform domains
HIGH_TRUST_DOMAINS = {
    "wikidata.org": "Wikidata",
    "wikipedia.org": "Wikipedia",
    "crunchbase.com": "Crunchbase",
}

SOCIAL_PLATFORM_DOMAINS = {
    "linkedin.com": "LinkedIn",
    "twitter.com": "Twitter/X",
    "x.com": "Twitter/X",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "youtube.com": "YouTube",
    "github.com": "GitHub",
    "glassdoor.com": "Glassdoor",
    "g2.com": "G2",
    "trustpilot.com": "Trustpilot",
    "yelp.com": "Yelp",
    "producthunt.com": "Product Hunt",
    "angellist.com": "AngelList",
    "pitchbook.com": "PitchBook",
}

ALL_AUTHORITY_DOMAINS = {**HIGH_TRUST_DOMAINS, **SOCIAL_PLATFORM_DOMAINS}

# About page path candidates
ABOUT_PATHS = ["/about", "/about-us", "/company", "/who-we-are",
               "/our-story", "/team", "/mission"]

# Disambiguating fact patterns for About page scoring
DISAMBIGUATING_PATTERNS = {
    "founding_year": re.compile(r"\b(?:founded|established|incorporated|since|est\.?)\s+(?:in\s+)?\d{4}\b", re.I),
    "location_hq": re.compile(r"\b(?:headquartered|based|located)\s+in\s+[A-Z][a-zA-Z\s,]+", re.I),
    "industry_vertical": re.compile(r"\b(?:software|saas|e-commerce|healthcare|fintech|edtech|b2b|b2c|marketplace|platform|agency|consulting|manufacturing|retail)\b", re.I),
    "team_size": re.compile(r"\b\d+[,\d]*\s+(?:employees|team members|people|professionals)\b", re.I),
    "customer_count": re.compile(r"\b\d+[,\d]*\+?\s+(?:customers|clients|users|brands|businesses)\b", re.I),
    "geographic_reach": re.compile(r"\b\d+\s+(?:countries|regions|cities|markets)\b", re.I),
}

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


def extract_all_links(html: str, current_url: str) -> list[str]:
    """Extract all hrefs including external."""
    soup = BeautifulSoup(html, "lxml")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        abs_url = urljoin(current_url, href).split("#")[0]
        if abs_url.startswith("http"):
            links.append(abs_url)
    return list(set(links))


def extract_jsonld_blocks(html: str) -> list[Any]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        raw = script.string or ""
        try:
            results.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return results


def flatten_jsonld(data: Any) -> list[dict]:
    """Flatten @graph and arrays into individual entities."""
    entities = []
    if isinstance(data, list):
        for item in data:
            entities.extend(flatten_jsonld(item))
    elif isinstance(data, dict):
        if "@graph" in data:
            for item in data["@graph"]:
                if isinstance(item, dict):
                    entities.append(item)
        else:
            entities.append(data)
    return entities


def get_same_as(entity: dict) -> list[str]:
    same_as = entity.get("sameAs", [])
    if isinstance(same_as, str):
        return [same_as]
    elif isinstance(same_as, list):
        return [s for s in same_as if isinstance(s, str)]
    return []


def classify_link(url: str) -> Optional[str]:
    """Return the platform name if the URL belongs to a known authority domain."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")
    for known_domain, name in ALL_AUTHORITY_DOMAINS.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            return name
    return None


def discover_pages(start_url: str, base_url: str) -> list[str]:
    pages = [start_url]
    visited = {start_url}

    # Priority: About pages
    for path in ABOUT_PATHS:
        candidate = base_url + path
        if candidate not in visited:
            visited.add(candidate)
            time.sleep(CRAWL_DELAY)
            resp = safe_get(candidate)
            if resp and resp.status_code == 200:
                pages.append(candidate)

    # BFS for remaining
    queue = deque([start_url])
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

    return list(dict.fromkeys(pages))


def score_about_page(text: str) -> tuple[int, list[str]]:
    """
    Score an About page for disambiguating identity facts.
    Returns (score 0-6, list of facts found).
    """
    found = []
    for fact_type, pattern in DISAMBIGUATING_PATTERNS.items():
        if pattern.search(text):
            found.append(fact_type.replace("_", " "))
    return len(found), found

# ── Making findings ───────────────────────────────────────────────────────────

def make_finding(title, severity, evidence, action):
    return {
        "title": title,
        "severity": severity,
        "category": "discoverability",
        "skill_source": "entity-clarity-audit",
        "evidence": evidence,
        "suggested_action": {
            "summary": action,
            "priority": severity,
        },
    }

# ── Main audit logic ───────────────────────────────────────────────────────────

def run(url: str) -> list[dict]:
    """Run entity-clarity-audit and return list of findings."""
    url = normalize_url(url)
    base_url = get_base_url(url)
    findings = []

    try:
        pages = discover_pages(url, base_url)
    except Exception as exc:
        return [make_finding(
            "entity-clarity-audit page discovery failed",
            "low",
            f"Could not crawl pages: {exc}",
            "Check network connectivity.",
        )]

    # Aggregate data across all pages
    all_same_as_links: list[str] = []
    all_external_links: list[str] = []
    org_entities: list[tuple[str, dict]] = []  # (page_url, entity)
    about_page_content: Optional[tuple[str, str]] = None  # (url, text)
    brand_name: Optional[str] = None

    for page_url in pages:
        time.sleep(CRAWL_DELAY)
        resp = safe_get(page_url)
        if not resp or resp.status_code != 200:
            continue

        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        visible_text = soup.get_text(separator=" ", strip=True)

        # Collect external links
        all_external_links.extend(extract_all_links(html, page_url))

        # Process JSON-LD
        for block in extract_jsonld_blocks(html):
            for entity in flatten_jsonld(block):
                t = entity.get("@type", "")
                types = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
                is_org = any(t in ("Organization", "LocalBusiness", "Corporation",
                                   "NGO", "GovernmentOrganization", "EducationalOrganization",
                                   "Brand") for t in types)
                if is_org:
                    org_entities.append((page_url, entity))
                    same_as = get_same_as(entity)
                    all_same_as_links.extend(same_as)
                    if not brand_name and entity.get("name"):
                        brand_name = entity["name"]

                # Also get sameAs from any entity type
                all_same_as_links.extend(get_same_as(entity))

        # About page check
        path = urlparse(page_url).path.lower()
        if any(ap in path for ap in ["/about", "/company", "/who-we", "/our-story"]):
            if not about_page_content:
                about_page_content = (page_url, visible_text)

    # Deduplicate
    all_same_as_links = list(set(all_same_as_links))
    all_external_links = list(set(all_external_links))

    # Classify sameAs and external links
    same_as_platforms = {classify_link(link): link
                         for link in all_same_as_links if classify_link(link)}
    external_authority_links = {classify_link(link): link
                                 for link in all_external_links if classify_link(link)}
    all_known_platforms = {**external_authority_links, **same_as_platforms}

    # ── Finding 1: No sameAs at all ───────────────────────────────────────────
    if not all_same_as_links:
        findings.append(make_finding(
            title="No sameAs links in any JSON-LD block",
            severity="high",
            evidence=(
                f"Crawled {len(pages)} pages including homepage "
                f"{'and /about' if about_page_content else ''}. "
                "0 pages contain a 'sameAs' property in any JSON-LD entity. "
                "Without sameAs, AI knowledge graphs cannot confidently link this site to its "
                "verified external identity on Wikidata, LinkedIn, or Crunchbase."
            ),
            action=(
                "Add a 'sameAs' array to your Organization JSON-LD on the homepage. "
                "Minimum recommended links: LinkedIn company page, Crunchbase profile. "
                "For highest-trust disambiguation: create a Wikidata entry and link to it. "
                "Example: \"sameAs\": [\"https://www.linkedin.com/company/...\", "
                "\"https://www.wikidata.org/wiki/Q...\"]"
            ),
        ))
    else:
        # Check for high-trust disambiguators
        missing_high_trust = [name for domain, name in HIGH_TRUST_DOMAINS.items()
                               if name not in same_as_platforms]
        if missing_high_trust:
            findings.append(make_finding(
                title=f"sameAs present but missing high-trust disambiguators: {', '.join(missing_high_trust)}",
                severity="medium",
                evidence=(
                    f"Found sameAs links to: {', '.join(same_as_platforms.keys()) or 'none classified'}. "
                    f"Missing high-trust identity anchors: {', '.join(missing_high_trust)}. "
                    "Wikidata/Wikipedia/Crunchbase entries are the strongest signals for AI entity resolution."
                ),
                action=(
                    f"Add the following to your sameAs array: {', '.join(missing_high_trust)}. "
                    "If no Wikidata entry exists for your brand, create one at https://www.wikidata.org/wiki/Special:NewItem"
                ),
            ))

    # ── Finding 2: No legalName in Organization JSON-LD ─────────────────────
    if org_entities:
        has_legal_name = any(e.get("legalName") for _, e in org_entities)
        if not has_legal_name:
            brand_note = f"Brand name in JSON-LD: '{brand_name}'." if brand_name else "No brand name found in JSON-LD."
            findings.append(make_finding(
                title="Organization JSON-LD missing 'legalName'",
                severity="medium",
                evidence=(
                    f"Found Organization JSON-LD on {len(org_entities)} page(s) but none declare 'legalName'. "
                    f"{brand_note} "
                    "Without legalName, AI models cannot distinguish between organizations "
                    "sharing a similar short brand name."
                ),
                action=(
                    "Add 'legalName' to your Organization JSON-LD with your full registered company name "
                    "(e.g., 'Acme Corporation Inc.' rather than just 'Acme'). "
                    "This is especially important if your brand name is generic or widely shared."
                ),
            ))
    else:
        findings.append(make_finding(
            title="No Organization JSON-LD found on any crawled page",
            severity="high",
            evidence=(
                f"Crawled {len(pages)} pages. "
                "No JSON-LD with @type Organization, LocalBusiness, or equivalent was found. "
                "AI assistants use Organization markup as the primary entity anchor for a brand."
            ),
            action=(
                "Add Organization JSON-LD to your homepage with: "
                "name, legalName, url, description, logo, sameAs, contactPoint. "
                "Reference: https://schema.org/Organization"
            ),
        ))

    # ── Finding 3: No About page ───────────────────────────────────────────────
    about_checked = any(
        safe_get(base_url + path) and
        (safe_get(base_url + path)).status_code == 200
        for path in ABOUT_PATHS[:3]
    )
    if not about_page_content:
        findings.append(make_finding(
            title="No About/Company page found",
            severity="medium",
            evidence=(
                f"Checked paths: {', '.join(ABOUT_PATHS[:5])}. "
                "None returned HTTP 200. An About page is a key identity signal "
                "that AI models use to understand a brand's purpose and distinguish it from peers."
            ),
            action=(
                "Create an /about page with: company name (full legal name), founding year, "
                "headquarters location, industry/vertical, mission statement, and key differentiators. "
                "Include at least 3 specific disambiguating facts."
            ),
        ))
    else:
        about_url, about_text = about_page_content
        score, facts_found = score_about_page(about_text)
        if score < 3:
            findings.append(make_finding(
                title=f"About page lacks sufficient disambiguating identity facts (score: {score}/6)",
                severity="low",
                evidence=(
                    f"About page: {about_url}. "
                    f"Detected disambiguating facts: {', '.join(facts_found) if facts_found else 'none'}. "
                    f"Missing categories: {', '.join(k.replace('_', ' ') for k in DISAMBIGUATING_PATTERNS if k.replace('_', ' ') not in facts_found)}. "
                    "Generic About pages increase the risk of AI entity confusion."
                ),
                action=(
                    "Improve the About page to include specific facts: founding year, HQ city/country, "
                    "industry vertical, team size, customer count, and geographic reach. "
                    "These specifics help AI models build an accurate entity profile."
                ),
            ))

    # ── Finding 4: No external identity links at all ───────────────────────────
    if not all_known_platforms:
        findings.append(make_finding(
            title="No links to external authority or social platforms found",
            severity="medium",
            evidence=(
                f"Scanned all external links across {len(pages)} pages. "
                "No links to LinkedIn, Twitter/X, Wikidata, Crunchbase, GitHub, "
                "or other authority platforms were found. "
                "External identity links help AI models verify and locate the brand."
            ),
            action=(
                "Add links to your verified social/authority profiles in the site footer or About page. "
                "Minimum: LinkedIn and one high-trust platform (Wikidata, Crunchbase, or GitHub). "
                "Also add these as sameAs values in your Organization JSON-LD."
            ),
        ))

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_entity.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
