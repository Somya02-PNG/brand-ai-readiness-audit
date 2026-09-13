#!/usr/bin/env python3
"""
audit-orchestrator/scripts/merge_report.py

Entrypoint for the brand-ai-readiness-audit marketplace.
Invokes all six worker audit skills, merges their findings into a single
schema-compliant JSON report with sequential IDs and severity counts.

Usage:
    python merge_report.py <url>
    python merge_report.py https://example.com
    python merge_report.py https://example.com --output report.json

Returns schema-compliant JSON to stdout (or file if --output specified).
"""

import sys
import json
import argparse
import ipaddress
import socket
import threading
import traceback
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Callable, Optional

# ── Worker skill imports (relative paths resolved via sys.path) ───────────────

import os

_SKILLS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

def _import_worker(skill_folder: str, script_name: str):
    """Dynamically import a worker script module."""
    import importlib.util
    script_path = os.path.join(
        _SKILLS_ROOT, "skills", skill_folder, "scripts", script_name
    )
    spec = importlib.util.spec_from_file_location(script_name.replace(".py", ""), script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Constants ──────────────────────────────────────────────────────────────────

SEVERITY_ORDER = ["critical", "high", "medium", "low"]

# Worker skill registry: (module_folder, script_filename, display_name)
WORKER_SKILLS = [
    ("crawl-access-audit",           "check_access.py",    "crawl-access-audit"),
    ("render-readability-audit",     "check_render_gap.py","render-readability-audit"),
    ("structured-data-audit",        "check_schema.py",    "structured-data-audit"),
    ("freshness-corroboration-audit","check_freshness.py", "freshness-corroboration-audit"),
    ("entity-clarity-audit",         "check_entity.py",    "entity-clarity-audit"),
    ("engagement-audit",             "check_engagement.py","engagement-audit"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


# Private / loopback / link-local networks that must never be audited
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),    # loopback
    ipaddress.ip_network("10.0.0.0/8"),     # private class A
    ipaddress.ip_network("172.16.0.0/12"),  # private class B
    ipaddress.ip_network("192.168.0.0/16"), # private class C
    ipaddress.ip_network("169.254.0.0/16"), # link-local (APIPA)
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique-local (ULA)
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
]


def assert_public_url(url: str) -> None:
    """
    Gate function: resolve the URL's hostname and raise ValueError if any
    returned IP address falls within a private, loopback, or link-local range.

    Must be called once before dispatching any worker skill.
    Raises ValueError with a descriptive message on rejection.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Cannot determine hostname from URL: {url!r}")

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(
            f"Hostname resolution failed for {hostname!r}: {exc}. "
            "Provide a publicly reachable domain."
        ) from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        raw_ip = sockaddr[0]  # first element is always the IP string
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue  # unparseable address — skip silently

        for network in _PRIVATE_NETWORKS:
            if ip in network:
                raise ValueError(
                    f"Audit target '{hostname}' resolves to a private/loopback/link-local "
                    f"address ({ip}), which is not permitted. "
                    "Only publicly routable internet addresses may be audited."
                )


def get_site(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or url


def severity_rank(sev: str) -> int:
    s = str(sev).lower().strip()
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return order.get(s, 3)


def severity_key(finding: dict) -> int:
    return severity_rank(finding.get("severity", "low"))


def derive_mechanism(finding: dict) -> str:
    """Generate a one-sentence mechanism explaining why this hurts AI discoverability or engagement."""
    if finding.get("mechanism"):
        return str(finding["mechanism"]).strip()

    text = (
        str(finding.get("title", "")) + " " +
        str(finding.get("evidence", "")) + " " +
        str(finding.get("category", "")) + " " +
        str(finding.get("skill_source", ""))
    ).lower()

    if any(k in text for k in ["robot", "disallow", "status", "redirect", "4xx", "5xx", "blocked", "http"]):
        return "Search and AI crawlers cannot index, parse, or cite content that is blocked by HTTP errors or robots.txt directives."
    if any(k in text for k in ["render", "javascript", "playwright", "raw html", "client-rendered", "gap"]):
        return "AI retrieval systems and web scrapers lacking headless browser execution miss key information that only appears after client-side rendering."
    if any(k in text for k in ["schema", "json-ld", "structured data", "property", "org", "product", "article"]):
        return "Missing or invalid structured data deprives AI answer engines of explicit semantic entities and relationships needed for authoritative citation."
    if any(k in text for k in ["freshness", "stale", "inconsistent", "phone", "email", "address", "conflict"]):
        return "Conflicting or stale brand facts across pages lower retrieval model confidence and increase hallucination risks in AI responses."
    if any(k in text for k in ["entity", "sameas", "wikidata", "wikipedia", "crunchbase", "legalname", "about"]):
        return "Lack of authoritative external identity anchors hinders knowledge graph disambiguation, causing AI assistants to confuse or overlook the brand."
    if any(k in text for k in ["engagement", "nav", "cta", "call-to-action", "link", "search", "breadcrumb"]):
        return "On-page friction, broken pathways, or absent calls-to-action cause visitors arriving from AI assistant links to bounce before converting."

    return "This issue impedes AI search systems and assistants from accurately discovering, parsing, and attributing brand content."


def derive_fix_effort(finding: dict, severity: str) -> str:
    """Derive fix effort level: low, medium, or high."""
    if finding.get("fix_effort"):
        val = str(finding["fix_effort"]).lower().strip()
        if val in ("low", "medium", "high"):
            return val

    text = (str(finding.get("title", "")) + " " + str(finding.get("skill_source", ""))).lower()

    if any(k in text for k in ["robots.txt", "cta", "h1", "sameas", "sitemap", "meta"]):
        return "low"
    if any(k in text for k in ["render gap", "architecture", "ssr", "database"]):
        return "high"
    if severity in ("critical", "high"):
        return "medium"
    return "low"


def derive_verification(finding: dict) -> str:
    """Derive concrete command or check to verify the fix."""
    if finding.get("verification"):
        return str(finding["verification"]).strip()

    text = (str(finding.get("title", "")) + " " + str(finding.get("skill_source", ""))).lower()

    if "robot" in text:
        return "curl -sI <site_url>/robots.txt && python -c 'import urllib.robotparser; rp=urllib.robotparser.RobotFileParser(); rp.set_url(\"<site_url>/robots.txt\"); rp.read(); print(rp.can_fetch(\"GPTBot\", \"<site_url>/\"))'"
    if "sitemap" in text:
        return "curl -sI <site_url>/sitemap.xml | grep -i 'HTTP/'"
    if any(k in text for k in ["schema", "json-ld", "structured"]):
        return "curl -s <page_url> | grep -A 20 'application/ld+json' or validate using validator.schema.org"
    if any(k in text for k in ["render", "javascript"]):
        return "curl -s <page_url> | wc -w | diff against Playwright rendered DOM text word count"
    if any(k in text for k in ["freshness", "inconsistency"]):
        return "Audit contact details across footer, /contact, and /about to confirm exact string match"
    if any(k in text for k in ["entity", "sameas", "about"]):
        return "Verify Organization JSON-LD contains non-empty sameAs array with valid profile URLs"
    if any(k in text for k in ["cta", "nav", "broken", "engagement"]):
        return "Inspect page source for visible hero CTA button and test all internal links return HTTP 200"

    return "Re-run the audit worker script standalone to verify 0 findings emitted"


def normalize_finding(raw: dict) -> dict:
    """Normalize a finding to strictly conform to the required JSON schema with safe defaults."""
    title = str(raw.get("title") or "Observation detected").strip()

    # severity: critical|high|medium|low
    sev = str(raw.get("severity", "low")).lower().strip()
    if sev not in ("critical", "high", "medium", "low"):
        sev = "low"

    evidence = str(raw.get("evidence") or "No detailed evidence string provided.").strip()

    # suggested_action MUST be an object: {"summary": "<str>", "priority": "critical|high|medium|low"}
    raw_action = raw.get("suggested_action")
    if isinstance(raw_action, dict):
        action_summary = str(raw_action.get("summary") or "Review and remediate this finding.").strip()
        action_priority = str(raw_action.get("priority") or sev).lower().strip()
        if action_priority not in ("critical", "high", "medium", "low"):
            action_priority = sev
    elif isinstance(raw_action, str) and raw_action.strip():
        action_summary = raw_action.strip()
        action_priority = sev
    else:
        action_summary = "Review and remediate this finding."
        action_priority = sev

    suggested_action = {
        "summary": action_summary,
        "priority": action_priority,
    }

    mechanism = derive_mechanism(raw) or "unknown"
    fix_effort = derive_fix_effort(raw, sev) or "low"
    if fix_effort not in ("low", "medium", "high"):
        fix_effort = "low"
    verification = derive_verification(raw) or "unknown"

    finding = {
        "id": str(raw.get("id") or ""),
        "title": title,
        "severity": sev,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "mechanism": mechanism,
        "fix_effort": fix_effort,
        "verification": verification,
    }

    # Preserve coverage_gap flag if set by a worker-failure path
    if raw.get("coverage_gap"):
        finding["coverage_gap"] = True

    return finding


def assign_ids(findings: list[dict]) -> list[dict]:
    """Sort findings by severity (critical > high > medium > low), then by id, and assign sequential F-XXX IDs."""
    normalized = [normalize_finding(f) for f in findings if not f.get("proactive")]

    def sort_key(f: dict):
        return (severity_rank(f["severity"]), str(f.get("id", "")), str(f.get("title", "")))

    sorted_findings = sorted(normalized, key=sort_key)
    for i, finding in enumerate(sorted_findings, start=1):
        finding["id"] = f"F-{i:03d}"
    return sorted_findings


def compute_summary(findings: list[dict]) -> dict:
    counts = {
        "total_findings": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "coverage_gaps": 0,
    }
    for f in findings:
        if f.get("coverage_gap") is True:
            counts["coverage_gaps"] += 1
            continue
        counts["total_findings"] += 1
        sev = f.get("severity", "low").lower()
        if sev in ("critical", "high", "medium", "low"):
            counts[sev] += 1
        else:
            counts["low"] += 1
    return counts


def generate_proactive_findings(url: str, existing_findings: list[dict]) -> list[dict]:
    """
    Generate 2-3 proactive findings (severity info, proactive=True)
    not tied to detected defects, tailored to what the crawl revealed about the site.
    """
    text_corpus = " ".join(
        f.get("title", "") + " " + f.get("evidence", "") for f in existing_findings
    ).lower()
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()

    is_content_or_media = (
        any(k in text_corpus for k in ["article", "news", "blog", "author", "editorial", "headline"])
        or any(k in domain for k in ["news", "verge", "times", "post", "blog", "press", "media"])
    )
    is_ecommerce = any(k in text_corpus for k in ["product", "offers", "cart", "checkout", "sku", "store", "shop"])
    has_faq = (
        ("faqpage" in text_corpus or "frequently asked questions" in text_corpus)
        and "missing" not in text_corpus
        and "no faqpage" not in text_corpus
    )
    has_llms = (
        "llms.txt" in text_corpus
        and "missing" not in text_corpus
        and "no /llms.txt" not in text_corpus
        and "no llms.txt" not in text_corpus
        and "not found" not in text_corpus
    )
    has_author_links = (
        ("author bio" in text_corpus or "author sameas" in text_corpus)
        and "missing" not in text_corpus
        and "no author" not in text_corpus
    )
    has_speakable = (
        "speakable" in text_corpus
        and "missing" not in text_corpus
        and "no speakable" not in text_corpus
    )
    has_breadcrumbs = (
        ("breadcrumblist" in text_corpus or "breadcrumb" in text_corpus)
        and "missing" not in text_corpus
        and "no breadcrumb" not in text_corpus
        and "no breadcrumbs" not in text_corpus
    )
    has_wikidata = (
        "wikidata" in text_corpus
        and "missing" not in text_corpus
        and "no wikidata" not in text_corpus
    )

    candidates = []

    # 1. Content/Editorial specific: Author bio pages with sameAs
    if is_content_or_media and not has_author_links:
        candidates.append({
            "title": "Consider adding author bio pages with sameAs links for content credibility",
            "severity": "info",
            "category": "credibility",
            "skill_source": "audit-orchestrator",
            "proactive": True,
            "evidence": (
                "Authoritative AI answer engines evaluate author expertise and identity when scoring source credibility. "
                "Linking editorial bylines to dedicated author bio pages with Person JSON-LD and sameAs links "
                "(Wikidata, LinkedIn, Twitter/X) boosts model confidence in attribution and E-E-A-T."
            ),
            "suggested_action": {
                "summary": (
                    "Create dedicated author profile pages linked from article bylines, "
                    "populated from editorial staff directory and verified LinkedIn or Wikidata profiles, "
                    "because AI answer engines evaluate author E-E-A-T credentials when scoring content trustworthiness. "
                    "Verify: curl -s <url>/authors | grep -i 'Person'."
                ),
                "priority": "low",
            },
            "mechanism": "AI answer engines evaluate author E-E-A-T credentials when scoring content trustworthiness.",
            "fix_effort": "low",
            "verification": "curl -s <url>/authors | grep -i 'Person'",
        })

    # 2. Content/Editorial specific: Speakable schema for voice/audio AI
    if is_content_or_media and not has_speakable:
        candidates.append({
            "title": "Consider adding Speakable specification for voice and audio AI assistants",
            "severity": "info",
            "category": "discoverability",
            "skill_source": "audit-orchestrator",
            "proactive": True,
            "evidence": (
                "The Speakable schema.org specification marks key content sections (such as article ledes, "
                "key takeaways, or executive summaries) as optimal for text-to-speech reading by voice assistants "
                "and conversational AI summary features."
            ),
            "suggested_action": {
                "summary": (
                    "Add Speakable schema.org markup to Article JSON-LD, "
                    "populated from introductory summaries and key takeaway elements in page templates, "
                    "because voice assistants and conversational AI summarizers require explicit speakable selectors to generate audio snippets. "
                    "Verify: curl -s <url> | grep -i '\"speakable\"'."
                ),
                "priority": "low",
            },
            "mechanism": "Voice assistants and conversational AI summarizers require explicit speakable selectors to generate audio snippets.",
            "fix_effort": "low",
            "verification": "curl -s <url> | grep -i '\"speakable\"'",
        })

    # 3. FAQPage schema (if site does not already have FAQPage)
    if not has_faq:
        candidates.append({
            "title": "Consider adding FAQPage JSON-LD to answer common questions directly in AI results",
            "severity": "info",
            "category": "discoverability",
            "skill_source": "audit-orchestrator",
            "proactive": True,
            "evidence": (
                "No FAQPage structured data was detected across the crawled pages. Publishing FAQPage JSON-LD "
                "enables AI search engines and assistants to quote structured question-and-answer pairs directly in conversational answers."
            ),
            "suggested_action": {
                "summary": (
                    "Add FAQPage JSON-LD to high-intent informational pages, "
                    "populated from server-rendered Q&A content in help and pricing templates, "
                    "because AI answer engines directly extract question-answer pairs for conversational grounding. "
                    "Verify: curl -s <url> | grep -i 'FAQPage'."
                ),
                "priority": "low",
            },
            "mechanism": "AI answer engines directly extract question-answer pairs for conversational grounding.",
            "fix_effort": "low",
            "verification": "curl -s <url> | grep -i 'FAQPage'",
        })

    # 4. /llms.txt summary file (if not already reported or existing)
    if not has_llms:
        candidates.append({
            "title": "Consider publishing an /llms.txt summary file to guide AI assistants",
            "severity": "info",
            "category": "discoverability",
            "skill_source": "audit-orchestrator",
            "proactive": True,
            "evidence": (
                "No /llms.txt file was found at the site root. The emerging /llms.txt convention (llmstxt.org) "
                "provides LLMs and AI search engines with a clean, curated Markdown summary of site architecture, "
                "core capabilities, and key documentation."
            ),
            "suggested_action": {
                "summary": (
                    "Publish an /llms.txt file at domain root, "
                    "populated from high-level site architecture and markdown documentation, "
                    "because AI crawlers can ingest concise markdown indexes directly without HTML parsing overhead. "
                    "Verify: curl -ILs <url>/llms.txt returns HTTP 200."
                ),
                "priority": "low",
            },
            "mechanism": "AI crawlers can ingest concise markdown indexes directly without HTML parsing overhead.",
            "fix_effort": "low",
            "verification": "curl -ILs <url>/llms.txt",
        })

    # 5. BreadcrumbList schema
    if not has_breadcrumbs and (is_ecommerce or len(existing_findings) > 3):
        candidates.append({
            "title": "Consider adding BreadcrumbList JSON-LD to convey hierarchical site architecture",
            "severity": "info",
            "category": "discoverability",
            "skill_source": "audit-orchestrator",
            "proactive": True,
            "evidence": (
                "BreadcrumbList structured data explicitly maps category and subpage relationships. "
                "AI search indexers use breadcrumb hierarchies to contextualize deep links in cited references."
            ),
            "suggested_action": {
                "summary": (
                    "Implement BreadcrumbList JSON-LD on content and category pages, "
                    "populated from site navigation hierarchy and parent category paths, "
                    "because AI search indexers rely on breadcrumb schema to contextualize deep links in cited references. "
                    "Verify: curl -s <url> | grep -i 'BreadcrumbList'."
                ),
                "priority": "low",
            },
            "mechanism": "AI search indexers rely on breadcrumb schema to contextualize deep links in cited references.",
            "fix_effort": "low",
            "verification": "curl -s <url> | grep -i 'BreadcrumbList'",
        })

    # 6. Wikidata grounding
    if not has_wikidata:
        candidates.append({
            "title": "Consider establishing a Wikidata entity for canonical knowledge graph grounding",
            "severity": "info",
            "category": "discoverability",
            "skill_source": "audit-orchestrator",
            "proactive": True,
            "evidence": (
                "Wikidata is a core training and entity-resolution reference for major LLMs (including GPT-4, Claude, "
                "and Gemini). Establishing an official Wikidata item and linking it in your Organization sameAs array "
                "provides durable grounding in the global knowledge graph."
            ),
            "suggested_action": {
                "summary": (
                    "Create a Wikidata item for your organization and link it in sameAs, "
                    "populated from official corporate registration records, "
                    "because major LLM knowledge graphs use Wikidata as a canonical entity-resolution reference. "
                    "Verify: curl -s <url> | grep -i 'wikidata.org'."
                ),
                "priority": "low",
            },
            "mechanism": "Major LLM knowledge graphs use Wikidata as a canonical entity-resolution reference.",
            "fix_effort": "low",
            "verification": "curl -s <url> | grep -i 'wikidata.org'",
        })

    # Return 2 or 3 proactive findings (at least 2, at most 3)
    return candidates[:3] if len(candidates) >= 3 else candidates[:2]


def run_worker(
    folder: str,
    script: str,
    display_name: str,
    url: str,
    results_container: list,
    index: int,
):
    """Run a single worker skill and store its findings in results_container[index]."""
    try:
        mod = _import_worker(folder, script)
        findings = mod.run(url)
        if not isinstance(findings, list):
            findings = []
        # Ensure skill_source is set
        for f in findings:
            f.setdefault("skill_source", display_name)
            f.setdefault("category", "discoverability")
        results_container[index] = findings
    except Exception as exc:
        tb = traceback.format_exc()
        results_container[index] = [{
            "title": f"{display_name} encountered an error",
            "severity": "low",
            "category": "discoverability",
            "skill_source": display_name,
            "coverage_gap": True,  # worker failure — not a website defect
            "evidence": (
                f"Worker skill '{display_name}' raised an exception and could not complete. "
                f"Error: {type(exc).__name__}: {exc}. "
                f"Traceback (last line): {tb.strip().splitlines()[-1]}"
            ),
            "suggested_action": {
                "summary": (
                    f"Debug worker execution for '{display_name}', "
                    f"populated from CLI command 'python skills/{folder}/scripts/{script} {url}', "
                    f"because internal worker runtime failures prevent generating actionable AI audit findings. "
                    f"Verify: python skills/{folder}/scripts/{script} {url}."
                ),
                "priority": "low",
            },
            "mechanism": "Internal worker runtime failures prevent auditing and reporting AI readiness signals.",
            "fix_effort": "low",
            "verification": f"python skills/{folder}/scripts/{script} {url}",
        }]


def make_fallback_finding(display_name: str = "worker-skill") -> dict:
    """Generate a fallback finding when a worker returns nothing or times out.

    Tagged with coverage_gap=True to distinguish it from genuine website defects.
    """
    return {
        "title": f"{display_name} timed out or returned no findings",
        "severity": "low",
        "category": "discoverability",
        "skill_source": display_name,
        "coverage_gap": True,  # worker failure — not a website defect
        "evidence": (
            f"Worker skill '{display_name}' did not complete within the time budget or returned no findings. "
            "Partial results excluded."
        ),
        "suggested_action": {
            "summary": (
                f"Verify standalone execution of '{display_name}', "
                f"populated from local CLI worker runner, "
                f"because audit worker timeouts prevent collecting complete AI readiness signals for this domain. "
                f"Verify: python -m pytest tests/test_merge_report.py."
            ),
            "priority": "low",
        },
        "mechanism": "Worker execution timeouts prevent evaluating domain AI readiness criteria.",
        "fix_effort": "low",
        "verification": "python -m pytest tests/test_merge_report.py",
    }


def handle_worker_result(findings: Optional[list], display_name: str) -> list[dict]:
    """Ensure that if a worker returns nothing (None), a fallback low-severity finding is emitted."""
    if findings is None:
        return [make_fallback_finding(display_name)]
    return findings


def collect_findings(results: list) -> list[dict]:
    """Collect findings from worker results, adding a fallback low-severity finding if a worker returns None."""
    all_findings = []
    for i, worker_findings in enumerate(results):
        display_name = WORKER_SKILLS[i][2] if i < len(WORKER_SKILLS) else f"worker-{i}"
        all_findings.extend(handle_worker_result(worker_findings, display_name))
    return all_findings


def normalize_beyond_problem_suggestion(raw: dict) -> dict:
    """Ensure each suggestion strictly matches: {title, rationale, mechanism, priority}."""
    title = str(raw.get("title") or "Proactive recommendation").strip()
    rationale = str(raw.get("rationale") or raw.get("evidence") or "Recommended proactive optimization for AI discoverability.").strip()
    mechanism = str(raw.get("mechanism") or "Enhances search intelligence and knowledge graph representation for AI assistants.").strip()

    raw_priority = str(
        raw.get("priority")
        or (raw.get("suggested_action", {}).get("priority") if isinstance(raw.get("suggested_action"), dict) else "low")
    ).lower().strip()
    priority = raw_priority if raw_priority in ("low", "medium", "high") else "low"

    return {
        "title": title,
        "rationale": rationale,
        "mechanism": mechanism,
        "priority": priority,
    }


def generate_beyond_problem_suggestions(url: str, existing_findings: Optional[list[dict]] = None) -> list[dict]:
    """Generate proactive beyond-problem suggestions relying on generate_proactive_findings."""
    raw_candidates = generate_proactive_findings(url, existing_findings or [])
    return [normalize_beyond_problem_suggestion(c) for c in raw_candidates]


def build_report(url: str, findings: list[dict], beyond_problem_suggestions: Optional[list] = None) -> dict:
    # Filter defects from any proactive items
    defect_findings = [f for f in findings if not f.get("proactive")]
    findings_with_ids = assign_ids(defect_findings)

    if beyond_problem_suggestions is None:
        proactive_in_findings = [f for f in findings if f.get("proactive")]
        if proactive_in_findings:
            raw_suggestions = proactive_in_findings
        else:
            raw_suggestions = generate_beyond_problem_suggestions(url, defect_findings)
    else:
        raw_suggestions = beyond_problem_suggestions

    normalized_suggestions = [
        normalize_beyond_problem_suggestion(s) for s in (raw_suggestions or [])
    ]

    # Ensure beyond_problem_suggestions is always populated if not provided or empty
    if not normalized_suggestions and (beyond_problem_suggestions is None or len(beyond_problem_suggestions) == 0):
        normalized_suggestions = generate_beyond_problem_suggestions(url, defect_findings)

    return {
        "site": get_site(url),
        "audited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": compute_summary(findings_with_ids),
        "findings": findings_with_ids,
        "beyond_problem_suggestions": normalized_suggestions,
    }

# ── Main ───────────────────────────────────────────────────────────────────────

def run(url: str) -> dict:
    """
    Orchestrate all worker skills, merge findings, return the full report dict.
    Workers run in parallel threads for speed.
    """
    url = normalize_url(url)

    # ── SSRF / private-network gate ───────────────────────────────────────────
    # Resolves the hostname and rejects any private, loopback, or link-local IP
    # before a single worker fetch is dispatched.
    assert_public_url(url)
    # ─────────────────────────────────────────────────────────────────────────

    # Pre-allocate results slots
    results = [None] * len(WORKER_SKILLS)

    # Launch workers in parallel threads
    threads = []
    for i, (folder, script, display_name) in enumerate(WORKER_SKILLS):
        t = threading.Thread(
            target=run_worker,
            args=(folder, script, display_name, url, results, i),
            daemon=True,
        )
        threads.append(t)
        t.start()

    # Wait for all workers to complete
    for t in threads:
        t.join(timeout=480)  # 8 min per worker; render worker needs ~405s worst-case (3 pages × 135s at 40s timeouts)

    # Collect all findings (using collect_findings helper)
    all_findings = collect_findings(results)

    # Generate beyond-problem suggestions tailored to the site
    suggestions = generate_beyond_problem_suggestions(url, all_findings)

    return build_report(url, all_findings, beyond_problem_suggestions=suggestions)


def main():
    parser = argparse.ArgumentParser(
        description="Brand AI-Readiness Audit — Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python merge_report.py https://example.com
  python merge_report.py example.com --output report.json
  python merge_report.py https://shop.example.com --pretty
        """,
    )
    parser.add_argument("url", help="The URL or domain to audit (e.g. https://example.com)")
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Write JSON report to FILE instead of stdout",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print the JSON output (default: True)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        default=False,
        help="Output compact JSON (overrides --pretty)",
    )

    args = parser.parse_args()
    indent = None if args.compact else 2

    print(f"[audit-orchestrator] Starting audit of: {args.url}", file=sys.stderr)
    print(f"[audit-orchestrator] Running {len(WORKER_SKILLS)} worker skills in parallel...", file=sys.stderr)

    report = run(args.url)

    total = report["summary"]["total_findings"]
    critical = report["summary"]["critical"]
    high = report["summary"]["high"]
    medium = report["summary"]["medium"]
    low = report["summary"]["low"]
    info = report["summary"].get("info", 0)
    info_str = f", {info} info" if info else ""
    print(
        f"[audit-orchestrator] Done. {total} findings: "
        f"{critical} critical, {high} high, "
        f"{medium} medium, {low} low{info_str}.",
        file=sys.stderr,
    )

    output_json = json.dumps(report, indent=indent, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"[audit-orchestrator] Report written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
