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
import threading
import traceback
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Callable

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

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

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


def get_site(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or url


def severity_key(finding: dict) -> int:
    sev = finding.get("severity", "low").lower()
    try:
        return SEVERITY_ORDER.index(sev)
    except ValueError:
        return len(SEVERITY_ORDER)


def assign_ids(findings: list[dict]) -> list[dict]:
    """Sort defects by severity (critical first) and keep proactive findings at the end, then assign sequential F-XXX IDs."""
    def sort_key(f: dict):
        is_proactive = 1 if f.get("proactive") else 0
        return (is_proactive, severity_key(f))

    sorted_findings = sorted(findings, key=sort_key)
    for i, finding in enumerate(sorted_findings, start=1):
        finding["id"] = f"F-{i:03d}"
    return sorted_findings


def compute_summary(findings: list[dict]) -> dict:
    counts = {
        "total_findings": len(findings),
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }
    for f in findings:
        sev = f.get("severity", "low").lower()
        if sev in counts:
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
    has_faq = "faqpage" in text_corpus or " faq" in text_corpus or "frequently asked questions" in text_corpus
    has_llms = "llms.txt" in text_corpus
    has_author_links = "author bio" in text_corpus or "author sameas" in text_corpus
    has_speakable = "speakable" in text_corpus
    has_breadcrumbs = "breadcrumblist" in text_corpus
    has_wikidata = "wikidata" in text_corpus and "missing" not in text_corpus

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
                    "Create dedicated author profile pages with Person schema, brief bios, and sameAs links "
                    "to authoritative external profiles to strengthen E-E-A-T credibility for AI engines."
                ),
                "priority": "low",
            },
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
                    "Add 'speakable' properties to Article or WebPage JSON-LD using CSS selectors targeting "
                    "introductory summaries and key takeaways."
                ),
                "priority": "low",
            },
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
                    "Add FAQPage structured data to high-intent informational pages (such as pricing, product FAQs, "
                    "or support pages) with clear, concise question-and-answer pairs."
                ),
                "priority": "low",
            },
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
                    "Publish an /llms.txt file at the domain root with concise Markdown summaries of your brand, "
                    "products, and primary links to streamline AI ingestion."
                ),
                "priority": "low",
            },
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
                    "Implement BreadcrumbList JSON-LD on content and category pages to signal clear navigational hierarchy."
                ),
                "priority": "low",
            },
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
                    "Create or update a Wikidata item representing your organization and reference it in your "
                    "homepage Organization JSON-LD sameAs array."
                ),
                "priority": "low",
            },
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
            "evidence": (
                f"Worker skill '{display_name}' raised an exception and could not complete. "
                f"Error: {type(exc).__name__}: {exc}. "
                f"Traceback (last line): {tb.strip().splitlines()[-1]}"
            ),
            "suggested_action": {
                "summary": (
                    f"Re-run the audit. If the error persists, run '{script}' standalone "
                    f"to debug: python skills/{folder}/scripts/{script} {url}"
                ),
                "priority": "low",
            },
        }]


def build_report(url: str, findings: list[dict]) -> dict:
    findings_with_ids = assign_ids(findings)
    return {
        "site": get_site(url),
        "audited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": compute_summary(findings_with_ids),
        "findings": findings_with_ids,
    }

# ── Main ───────────────────────────────────────────────────────────────────────

def run(url: str) -> dict:
    """
    Orchestrate all worker skills, merge findings, return the full report dict.
    Workers run in parallel threads for speed.
    """
    url = normalize_url(url)

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

    # Collect all findings
    all_findings = []
    for i, worker_findings in enumerate(results):
        if worker_findings is None:
            folder, script, display_name = WORKER_SKILLS[i]
            all_findings.append({
                "title": f"{display_name} timed out",
                "severity": "low",
                "category": "discoverability",
                "skill_source": display_name,
                "evidence": (
                    f"Worker skill '{display_name}' did not complete within the time budget. "
                    "Partial results excluded."
                ),
                "suggested_action": {
                    "summary": f"Run '{display_name}' standalone to debug the timeout.",
                    "priority": "low",
                },
            })
        else:
            all_findings.extend(worker_findings)

    # Append 2-3 proactive findings tailored to what the crawl revealed
    proactive_findings = generate_proactive_findings(url, all_findings)
    all_findings.extend(proactive_findings)

    return build_report(url, all_findings)


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
