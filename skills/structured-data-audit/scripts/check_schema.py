#!/usr/bin/env python3
"""
structured-data-audit/scripts/check_schema.py

Checks for presence, validity, and completeness of schema.org JSON-LD
markup on a representative sample of pages.

Usage:
    python check_schema.py <url>
    python check_schema.py https://example.com

Returns JSON list of findings to stdout.
"""

import sys
import json
import time
import re
from urllib.parse import urlparse, urljoin
from collections import deque
from typing import Optional, Any

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(json.dumps([{
        "title": "Missing dependency for structured-data-audit",
        "severity": "low",
        "category": "discoverability",
        "skill_source": "structured-data-audit",
        "evidence": f"Required package not installed: {e}",
        "suggested_action": {
            "summary": "Install required packages: pip install requests beautifulsoup4 lxml extruct",
            "priority": "low"
        }
    }]))
    sys.exit(0)

# extruct is the preferred extractor; fall back to bs4-only if not installed
EXTRUCT_AVAILABLE = False
try:
    import extruct
    EXTRUCT_AVAILABLE = True
except ImportError:
    pass

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

# Priority URL path patterns for crawl
PRIORITY_PATTERNS = [
    r"/product", r"/shop", r"/item", r"/buy",  # e-commerce
    r"/blog", r"/article", r"/post", r"/news",  # content
    r"/about", r"/company", r"/team",           # identity
    r"/faq", r"/help", r"/support",             # FAQ
    r"/pricing", r"/plans",                     # pricing
    r"/contact",                                # contact
]

# Required properties per schema type
REQUIRED_PROPS: dict[str, list[str]] = {
    "Organization": ["name", "url"],
    "LocalBusiness": ["name", "address", "telephone"],
    "Product": ["name", "description", "offers"],
    "Article": ["headline", "datePublished", "author"],
    "BlogPosting": ["headline", "datePublished", "author"],
    "NewsArticle": ["headline", "datePublished", "author"],
    "FAQPage": ["mainEntity"],
    "BreadcrumbList": ["itemListElement"],
    "WebSite": ["name", "url"],
    "Person": ["name"],
    "Event": ["name", "startDate"],
    "Recipe": ["name", "recipeIngredient"],
    "HowTo": ["name", "step"],
    "Review": ["itemReviewed", "reviewRating"],
    "Course": ["name", "description", "provider"],
    "JobPosting": ["title", "hiringOrganization", "jobLocation"],
    "SoftwareApplication": ["name", "applicationCategory"],
}

# Recommended (not required) but high-value for AI
RECOMMENDED_PROPS: dict[str, list[str]] = {
    "Organization": ["description", "sameAs", "legalName", "logo"],
    "Product": ["image", "brand", "sku"],
    "Article": ["image", "description"],
    "FAQPage": [],
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


def score_url_priority(url: str) -> int:
    """Higher score = higher crawl priority for structured data auditing."""
    path = urlparse(url).path.lower()
    for i, pat in enumerate(PRIORITY_PATTERNS):
        if re.search(pat, path):
            return len(PRIORITY_PATTERNS) - i
    return 0


def discover_pages(start_url: str, base_url: str) -> list[str]:
    """BFS crawl with priority scoring for schema-relevant pages."""
    visited = {start_url}
    pages = [start_url]
    queue = deque([start_url])
    candidates = []

    while queue:
        url = queue.popleft()
        time.sleep(CRAWL_DELAY)
        resp = safe_get(url)
        if resp and resp.status_code == 200:
            links = extract_internal_links(resp.text, base_url, url)
            for link in links:
                if link not in visited:
                    visited.add(link)
                    candidates.append((link, score_url_priority(link)))

    # Sort by priority and take up to MAX_PAGES-1 additional pages
    candidates.sort(key=lambda x: x[1], reverse=True)
    for link, _ in candidates[: MAX_PAGES - 1]:
        pages.append(link)

    return pages[:MAX_PAGES]


def extract_jsonld(html: str, base_url: str = "") -> list[dict[str, Any]]:
    """
    Extract and parse all JSON-LD blocks from a page.
    Uses extruct (primary) for robust extraction; falls back to BeautifulSoup.
    extruct also catches malformed JSON and normalizes @graph blocks.
    """
    results = []

    if EXTRUCT_AVAILABLE:
        try:
            # extruct.extract returns normalized dicts per syntax
            html_bytes = html.encode("utf-8", errors="replace")
            data = extruct.extract(
                html_bytes,
                base_url=base_url or "",
                syntaxes=["json-ld"],
                uniform=True,
                errors="log",
            )
            for item in data.get("json-ld", []):
                results.append({"data": item, "raw": "", "error": None})
            # If extruct returned nothing but html has ld+json tags,
            # fall through to BS4 to catch malformed-JSON findings
            if results:
                return results
        except Exception:
            pass  # fall through to BS4

    # BS4 fallback (also catches malformed JSON as an explicit finding)
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        raw = script.string or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            results.append({"data": parsed, "raw": raw, "error": None})
        except json.JSONDecodeError as e:
            results.append({"data": None, "raw": raw[:200], "error": str(e)})
    return results



def get_types(data: Any) -> list[str]:
    """Recursively extract all @type values from a JSON-LD object."""
    types = []
    if isinstance(data, dict):
        t = data.get("@type")
        if isinstance(t, str):
            types.append(t)
        elif isinstance(t, list):
            types.extend(t)
        # Handle @graph
        if "@graph" in data:
            for item in data["@graph"]:
                types.extend(get_types(item))
    elif isinstance(data, list):
        for item in data:
            types.extend(get_types(item))
    return types


def flatten_graph(data: Any) -> list[dict]:
    """Flatten @graph arrays so each entity is individually inspectable."""
    entities = []
    if isinstance(data, list):
        for item in data:
            entities.extend(flatten_graph(item))
    elif isinstance(data, dict):
        if "@graph" in data:
            for item in data["@graph"]:
                if isinstance(item, dict):
                    entities.append(item)
        else:
            entities.append(data)
    return entities


def get_entity_declared_types(entity: dict) -> list[str]:
    """Get the immediate @type values declared directly on this entity."""
    t = entity.get("@type")
    if isinstance(t, str):
        return [t]
    elif isinstance(t, list):
        return [str(x) for x in t if isinstance(x, str)]
    return []


def check_entity_props(entity: dict, schema_type: str, page_url: str) -> list[dict]:
    """Check a single JSON-LD entity for missing required/recommended props."""
    findings = []
    required = REQUIRED_PROPS.get(schema_type, [])
    recommended = RECOMMENDED_PROPS.get(schema_type, [])

    missing_required = [p for p in required if not entity.get(p)]
    missing_recommended = [p for p in recommended if not entity.get(p)]

    path = urlparse(page_url).path or "/"

    if missing_required:
        findings.append({
            "title": f"{schema_type} JSON-LD missing required properties on {path}",
            "severity": "high",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": (
                f"Page: {page_url}. "
                f"Found {schema_type} JSON-LD block but missing required fields: "
                f"{', '.join(missing_required)}. "
                f"Present fields: {', '.join(k for k in entity.keys() if not k.startswith('@'))}."
            ),
            "suggested_action": {
                "summary": (
                    f"Add the following required properties to your {schema_type} JSON-LD: "
                    f"{', '.join(missing_required)}. "
                    "See schema.org/{schema_type} for full spec."
                ).replace("{schema_type}", schema_type),
                "priority": "high",
            },
        })

    if missing_recommended and not missing_required:
        findings.append({
            "title": f"{schema_type} JSON-LD missing high-value recommended properties on {path}",
            "severity": "medium",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": (
                f"Page: {page_url}. "
                f"{schema_type} JSON-LD present and required fields satisfied, but missing "
                f"recommended fields: {', '.join(missing_recommended)}. "
                "These fields significantly improve AI citation quality."
            ),
            "suggested_action": {
                "summary": (
                    f"Add recommended properties to {schema_type} JSON-LD: "
                    f"{', '.join(missing_recommended)}."
                ),
                "priority": "medium",
            },
        })

    # Product-specific: validate offers object
    if schema_type == "Product" and entity.get("offers"):
        offers = entity["offers"]
        if isinstance(offers, dict):
            offer_missing = [p for p in ["price", "priceCurrency", "availability"] if not offers.get(p)]
            if offer_missing:
                findings.append({
                    "title": f"Product Offer object missing properties on {path}",
                    "severity": "high",
                    "category": "discoverability",
                    "skill_source": "structured-data-audit",
                    "evidence": (
                        f"Page: {page_url}. "
                        f"Product JSON-LD has 'offers' object but missing: {', '.join(offer_missing)}."
                    ),
                    "suggested_action": {
                        "summary": (
                            f"Add to the offers object: {', '.join(offer_missing)}. "
                            "Use priceCurrency: 'USD' (ISO 4217) and availability: 'https://schema.org/InStock'."
                        ),
                        "priority": "high",
                    },
                })

    # FAQPage: validate mainEntity
    if schema_type == "FAQPage":
        main_entity = entity.get("mainEntity", [])
        if not isinstance(main_entity, list) or len(main_entity) == 0:
            findings.append({
                "title": f"FAQPage mainEntity is empty or invalid on {path}",
                "severity": "high",
                "category": "discoverability",
                "skill_source": "structured-data-audit",
                "evidence": f"Page: {page_url}. FAQPage JSON-LD has no items in mainEntity.",
                "suggested_action": {
                    "summary": "Populate mainEntity with Question objects each having name and acceptedAnswer.",
                    "priority": "high",
                },
            })

    return findings


def check_context(entity: dict, page_url: str) -> Optional[dict]:
    context = entity.get("@context", "")
    if isinstance(context, str):
        if "schema.org" not in context:
            return {"url": page_url, "context": context}
    elif isinstance(context, list):
        if not any("schema.org" in str(c) for c in context):
            return {"url": page_url, "context": str(context)}
    return None

# ── Main audit logic ───────────────────────────────────────────────────────────

def run(url: str) -> list[dict]:
    """Run structured-data-audit and return list of findings."""
    url = normalize_url(url)
    base_url = get_base_url(url)
    findings = []

    try:
        pages = discover_pages(url, base_url)
    except Exception as exc:
        return [{
            "title": "structured-data-audit page discovery failed",
            "severity": "low",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": f"Could not crawl pages: {exc}",
            "suggested_action": {
                "summary": "Check network connectivity.",
                "priority": "low",
            },
        }]

    pages_with_jsonld = 0
    pages_without_jsonld = []
    page_type_coverage: dict[str, int] = {}
    context_issues = []
    seen_context_urls = set()

    missing_required_issues: dict[tuple, list[dict]] = {}
    page_seen_req_issues: dict[tuple, set] = {}

    missing_rec_issues: dict[tuple, list[dict]] = {}
    page_seen_rec_issues: dict[tuple, set] = {}

    offer_issues: dict[tuple, list[dict]] = {}
    page_seen_offer_issues: dict[tuple, set] = {}

    faq_issues: list[dict] = []
    page_seen_faq: set = set()

    for page_url in pages:
        time.sleep(CRAWL_DELAY)
        resp = safe_get(page_url)
        if not resp or resp.status_code != 200:
            continue

        blocks = extract_jsonld(resp.text, base_url=page_url)

        # Check for malformed JSON
        for block in blocks:
            if block["error"]:
                findings.append({
                    "title": f"Malformed JSON-LD on {urlparse(page_url).path or '/'}",
                    "severity": "high",
                    "category": "discoverability",
                    "skill_source": "structured-data-audit",
                    "evidence": (
                        f"Page: {page_url}. "
                        f"JSON-LD block failed to parse: {block['error']}. "
                        f"Snippet: {block['raw'][:150]}..."
                    ),
                    "suggested_action": {
                        "summary": (
                            "Fix the JSON syntax error in the JSON-LD block. "
                            "Validate with Google's Rich Results Test: "
                            "https://search.google.com/test/rich-results"
                        ),
                        "priority": "high",
                    },
                })

        valid_blocks = [b for b in blocks if b["data"] is not None]
        if valid_blocks:
            pages_with_jsonld += 1
            for block in valid_blocks:
                # Context check (top-level only)
                ctx_issue = check_context(block["data"], page_url)
                if ctx_issue and page_url not in seen_context_urls:
                    seen_context_urls.add(page_url)
                    context_issues.append(ctx_issue)

                entities = flatten_graph(block["data"])
                for entity in entities:
                    types = get_types(entity)
                    for t in types:
                        page_type_coverage[t] = page_type_coverage.get(t, 0) + 1

                    declared_types = get_entity_declared_types(entity)
                    if not declared_types:
                        declared_types = [t for t in types if t in REQUIRED_PROPS or t in RECOMMENDED_PROPS]

                    path = urlparse(page_url).path or "/"

                    # Check required properties across declared types
                    req_types = [t for t in declared_types if t in REQUIRED_PROPS]
                    types_with_missing_req = [t for t in req_types if any(not entity.get(p) for p in REQUIRED_PROPS[t])]
                    if types_with_missing_req:
                        missing_props = sorted(list({p for t in types_with_missing_req for p in REQUIRED_PROPS[t] if not entity.get(p)}))
                        type_label = "/".join(types_with_missing_req)
                        issue_key = (type_label, tuple(missing_props))
                        if page_url not in page_seen_req_issues.get(issue_key, set()):
                            page_seen_req_issues.setdefault(issue_key, set()).add(page_url)
                            missing_required_issues.setdefault(issue_key, []).append({
                                "page_url": page_url,
                                "path": path,
                                "present_fields": [k for k in entity.keys() if not k.startswith('@')],
                            })
                    elif declared_types:
                        # Only check recommended properties if all required properties are satisfied
                        rec_types = [t for t in declared_types if t in RECOMMENDED_PROPS]
                        types_with_missing_rec = [t for t in rec_types if any(not entity.get(p) for p in RECOMMENDED_PROPS[t])]
                        if types_with_missing_rec:
                            missing_rec = sorted(list({p for t in types_with_missing_rec for p in RECOMMENDED_PROPS[t] if not entity.get(p)}))
                            type_label = "/".join(types_with_missing_rec)
                            issue_key = (type_label, tuple(missing_rec))
                            if page_url not in page_seen_rec_issues.get(issue_key, set()):
                                page_seen_rec_issues.setdefault(issue_key, set()).add(page_url)
                                missing_rec_issues.setdefault(issue_key, []).append({
                                    "page_url": page_url,
                                    "path": path,
                                })

                    # Product-specific: validate offers object
                    if "Product" in declared_types and entity.get("offers"):
                        offers = entity["offers"]
                        if isinstance(offers, dict):
                            offer_missing = sorted([p for p in ["price", "priceCurrency", "availability"] if not offers.get(p)])
                            if offer_missing:
                                off_key = tuple(offer_missing)
                                if page_url not in page_seen_offer_issues.get(off_key, set()):
                                    page_seen_offer_issues.setdefault(off_key, set()).add(page_url)
                                    offer_issues.setdefault(off_key, []).append({
                                        "page_url": page_url,
                                        "path": path,
                                    })

                    # FAQPage: validate mainEntity
                    if "FAQPage" in declared_types:
                        main_entity = entity.get("mainEntity", [])
                        if not isinstance(main_entity, list) or len(main_entity) == 0:
                            if page_url not in page_seen_faq:
                                page_seen_faq.add(page_url)
                                faq_issues.append({
                                    "page_url": page_url,
                                    "path": path,
                                })
        else:
            pages_without_jsonld.append(urlparse(page_url).path or "/")

    # Consolidate context findings if repeated across multiple pages
    if len(context_issues) > 1:
        evidence_lines = [
            f"Found JSON-LD blocks where @context is not 'https://schema.org' across {len(context_issues)} pages:"
        ]
        for item in context_issues:
            ctx_val = item["context"] or "(empty string)"
            evidence_lines.append(f"- {item['url']} (context: '{ctx_val}')")
        evidence_lines.append("Expected '@context': 'https://schema.org'.")

        findings.append({
            "title": f"JSON-LD @context is not schema.org across {len(context_issues)} pages",
            "severity": "medium",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": "\n".join(evidence_lines),
            "suggested_action": {
                "summary": "Set @context to 'https://schema.org' in all JSON-LD blocks across all pages.",
                "priority": "medium",
            },
        })
    elif len(context_issues) == 1:
        item = context_issues[0]
        ctx_val = item["context"] or "(empty string)"
        findings.append({
            "title": f"JSON-LD @context is not schema.org on {urlparse(item['url']).path or '/'}",
            "severity": "medium",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": f"Page: {item['url']}. @context value: '{ctx_val}'. Expected 'https://schema.org'.",
            "suggested_action": {
                "summary": "Set @context to 'https://schema.org' in all JSON-LD blocks.",
                "priority": "medium",
            },
        })

    # Consolidate missing required property findings across pages
    for (type_label, missing_props), items in missing_required_issues.items():
        primary_type = type_label.split("/")[0]
        if len(items) > 2:
            page_urls = [it["page_url"] for it in items]
            findings.append({
                "title": f"{type_label} JSON-LD missing required properties across {len(items)} pages",
                "severity": "high",
                "category": "discoverability",
                "skill_source": "structured-data-audit",
                "evidence": (
                    f"Found {type_label} JSON-LD blocks missing required fields: "
                    f"{', '.join(missing_props)} across {len(items)} pages: "
                    f"{', '.join(page_urls)}."
                ),
                "suggested_action": {
                    "summary": (
                        f"Add the following required properties to your {type_label} JSON-LD across affected pages: "
                        f"{', '.join(missing_props)}. "
                        f"See schema.org/{primary_type} for full spec."
                    ),
                    "priority": "high",
                },
            })
        else:
            for it in items:
                findings.append({
                    "title": f"{type_label} JSON-LD missing required properties on {it['path']}",
                    "severity": "high",
                    "category": "discoverability",
                    "skill_source": "structured-data-audit",
                    "evidence": (
                        f"Page: {it['page_url']}. "
                        f"Found {type_label} JSON-LD block but missing required fields: "
                        f"{', '.join(missing_props)}. "
                        f"Present fields: {', '.join(it['present_fields'])}."
                    ),
                    "suggested_action": {
                        "summary": (
                            f"Add the following required properties to your {type_label} JSON-LD: "
                            f"{', '.join(missing_props)}. "
                            f"See schema.org/{primary_type} for full spec."
                        ),
                        "priority": "high",
                    },
                })

    # Consolidate missing recommended property findings across pages
    for (type_label, missing_props), items in missing_rec_issues.items():
        if len(items) > 2:
            page_urls = [it["page_url"] for it in items]
            findings.append({
                "title": f"{type_label} JSON-LD missing high-value recommended properties across {len(items)} pages",
                "severity": "medium",
                "category": "discoverability",
                "skill_source": "structured-data-audit",
                "evidence": (
                    f"{type_label} JSON-LD present across {len(items)} pages but missing recommended fields: "
                    f"{', '.join(missing_props)}: {', '.join(page_urls)}. "
                    "These fields significantly improve AI citation quality."
                ),
                "suggested_action": {
                    "summary": (
                        f"Add recommended properties to {type_label} JSON-LD across affected pages: "
                        f"{', '.join(missing_props)}."
                    ),
                    "priority": "medium",
                },
            })
        else:
            for it in items:
                findings.append({
                    "title": f"{type_label} JSON-LD missing high-value recommended properties on {it['path']}",
                    "severity": "medium",
                    "category": "discoverability",
                    "skill_source": "structured-data-audit",
                    "evidence": (
                        f"Page: {it['page_url']}. "
                        f"{type_label} JSON-LD present and required fields satisfied, but missing "
                        f"recommended fields: {', '.join(missing_props)}. "
                        "These fields significantly improve AI citation quality."
                    ),
                    "suggested_action": {
                        "summary": (
                            f"Add recommended properties to {type_label} JSON-LD: "
                            f"{', '.join(missing_props)}."
                        ),
                        "priority": "medium",
                    },
                })

    # Product offer issues
    for missing_props, items in offer_issues.items():
        if len(items) > 2:
            page_urls = [it["page_url"] for it in items]
            findings.append({
                "title": f"Product Offer object missing properties across {len(items)} pages",
                "severity": "high",
                "category": "discoverability",
                "skill_source": "structured-data-audit",
                "evidence": (
                    f"Product JSON-LD has 'offers' object but missing {', '.join(missing_props)} "
                    f"across {len(items)} pages: {', '.join(page_urls)}."
                ),
                "suggested_action": {
                    "summary": (
                        f"Add to the offers object: {', '.join(missing_props)}. "
                        "Use priceCurrency: 'USD' (ISO 4217) and availability: 'https://schema.org/InStock'."
                    ),
                    "priority": "high",
                },
            })
        else:
            for it in items:
                findings.append({
                    "title": f"Product Offer object missing properties on {it['path']}",
                    "severity": "high",
                    "category": "discoverability",
                    "skill_source": "structured-data-audit",
                    "evidence": (
                        f"Page: {it['page_url']}. "
                        f"Product JSON-LD has 'offers' object but missing: {', '.join(missing_props)}."
                    ),
                    "suggested_action": {
                        "summary": (
                            f"Add to the offers object: {', '.join(missing_props)}. "
                            "Use priceCurrency: 'USD' (ISO 4217) and availability: 'https://schema.org/InStock'."
                        ),
                        "priority": "high",
                    },
                })

    # FAQPage mainEntity issues
    if len(faq_issues) > 2:
        page_urls = [it["page_url"] for it in faq_issues]
        findings.append({
            "title": f"FAQPage mainEntity is empty or invalid across {len(faq_issues)} pages",
            "severity": "high",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": f"FAQPage JSON-LD has no items in mainEntity across {len(faq_issues)} pages: {', '.join(page_urls)}.",
            "suggested_action": {
                "summary": "Populate mainEntity with Question objects each having name and acceptedAnswer.",
                "priority": "high",
            },
        })
    else:
        for it in faq_issues:
            findings.append({
                "title": f"FAQPage mainEntity is empty or invalid on {it['path']}",
                "severity": "high",
                "category": "discoverability",
                "skill_source": "structured-data-audit",
                "evidence": f"Page: {it['page_url']}. FAQPage JSON-LD has no items in mainEntity.",
                "suggested_action": {
                    "summary": "Populate mainEntity with Question objects each having name and acceptedAnswer.",
                    "priority": "high",
                },
            })

    total_pages = len(pages)
    no_markup_pct = len(pages_without_jsonld) / total_pages * 100 if total_pages else 0

    # Summary: no markup
    if no_markup_pct >= 80:
        findings.insert(0, {
            "title": f"0 of {total_pages} pages contain any schema.org JSON-LD",
            "severity": "critical",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": (
                f"Sampled {total_pages} pages; {len(pages_without_jsonld)}/{total_pages} "
                f"({no_markup_pct:.0f}%) have no <script type='application/ld+json'> block. "
                f"Checked pages include: {', '.join(pages_without_jsonld[:8])}."
            ),
            "suggested_action": {
                "summary": (
                    "Implement schema.org JSON-LD markup across all page types. "
                    "Start with Organization on the homepage, then Product/Article/FAQPage "
                    "on relevant pages. Use Google's Structured Data Markup Helper."
                ),
                "priority": "critical",
            },
        })
    elif no_markup_pct >= 50:
        findings.insert(0, {
            "title": f"{len(pages_without_jsonld)}/{total_pages} pages lack schema.org JSON-LD",
            "severity": "high",
            "category": "discoverability",
            "skill_source": "structured-data-audit",
            "evidence": (
                f"Only {pages_with_jsonld}/{total_pages} sampled pages have JSON-LD markup. "
                f"Pages without markup: {', '.join(pages_without_jsonld[:6])}."
            ),
            "suggested_action": {
                "summary": (
                    "Extend JSON-LD markup to all page types. "
                    "Prioritize product, article, and FAQ pages for maximum AI citation impact."
                ),
                "priority": "high",
            },
        })

    # Suggest missing high-value schema types
    # Path pattern matching test cases:
    #   Should NOT match: "/news/tv-production-industry", "/workshops/design", "/composting-guide"
    #   SHOULD still match: "/product/123", "/shop/shoes", "/blog/post-1", "/products"
    if total_pages > 3:
        has_product_pages = any(
            re.search(r"(^|/)(product|products|shop|item|items|store)(/|$|-|_)", urlparse(p).path, re.I)
            for p in pages
        )
        has_blog_pages = any(
            re.search(r"(^|/)(blog|blogs|article|articles|news)(/|$|-|_)", urlparse(p).path, re.I)
            for p in pages
        )
        if has_product_pages and "Product" not in page_type_coverage:
            findings.append({
                "title": "Product pages detected but no Product JSON-LD found",
                "severity": "high",
                "category": "discoverability",
                "skill_source": "structured-data-audit",
                "evidence": (
                    "URL patterns suggest this site has product pages "
                    "(paths matching /product/, /shop/, /item/), "
                    "but no Product schema.org JSON-LD was found on any of them."
                ),
                "suggested_action": {
                    "summary": (
                        "Add Product JSON-LD to all product pages with at minimum: "
                        "name, description, offers (price, priceCurrency, availability), image, brand."
                    ),
                    "priority": "high",
                },
            })
        if has_blog_pages and "Article" not in page_type_coverage and "BlogPosting" not in page_type_coverage:
            findings.append({
                "title": "Blog/article pages detected but no Article JSON-LD found",
                "severity": "medium",
                "category": "discoverability",
                "skill_source": "structured-data-audit",
                "evidence": (
                    "URL patterns suggest this site has blog or article pages, "
                    "but no Article or BlogPosting JSON-LD was found. "
                    "AI assistants rely on Article markup to properly attribute authored content."
                ),
                "suggested_action": {
                    "summary": (
                        "Add Article or BlogPosting JSON-LD to all blog posts with: "
                        "headline, datePublished, dateModified, author (Person with name), image."
                    ),
                    "priority": "medium",
                },
            })

    return findings


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_schema.py <url>", file=sys.stderr)
        sys.exit(1)
    results = run(sys.argv[1])
    print(json.dumps(results, indent=2))
