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
    """Sort by severity (critical first) then assign sequential F-XXX IDs."""
    sorted_findings = sorted(findings, key=severity_key)
    for i, finding in enumerate(sorted_findings, start=1):
        finding["id"] = f"F-{i:03d}"
    return sorted_findings


def compute_summary(findings: list[dict]) -> dict:
    counts = {"total_findings": len(findings), "critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low").lower()
        if sev in counts:
            counts[sev] += 1
    return counts


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
        t.join(timeout=270)  # 4.5 min per worker max; overall < 5 min target

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
    print(
        f"[audit-orchestrator] Done. {total} findings: "
        f"{critical} critical, {high} high, "
        f"{report['summary']['medium']} medium, {report['summary']['low']} low.",
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
