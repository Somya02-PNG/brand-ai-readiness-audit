---
name: audit-orchestrator
description: >
  Given any website URL, runs all six Brand AI-Readiness worker audits and
  merges their findings into a single, schema-compliant JSON report. Useful
  for diagnosing why a brand is missing or misrepresented in AI assistants,
  or why visitors who arrive don't engage.
license: MIT
entrypoint: true
---

## When to use

Invoke this skill when you need a complete, end-to-end AI-readiness and
engagement audit for any public website. It is the single entry point for the
`brand-ai-readiness-audit` marketplace.

Trigger phrases:
- "Audit [URL] for AI readiness"
- "Why is [brand/domain] not appearing in AI search results?"
- "Diagnose why visitors to [domain] don't engage"
- "Run a brand discoverability audit on [URL]"

## Inputs

| Name  | Type   | Required | Description                                    |
|-------|--------|----------|------------------------------------------------|
| `url` | string | Yes      | The full URL or domain to audit (e.g. `https://example.com` or `example.com`). Must be publicly accessible. |
| `output` | string | No | File path to write the JSON report. If omitted, report is printed to stdout. |

## Procedure

1. Normalize the input URL (add `https://` scheme if missing; strip trailing slash).
2. Invoke the six worker skills **in parallel where safe**, collecting their findings lists:
   - `crawl-access-audit` → access / crawlability findings
   - `render-readability-audit` → JS render gap findings
   - `structured-data-audit` → schema.org markup findings
   - `freshness-corroboration-audit` → fact consistency / freshness findings
   - `entity-clarity-audit` → entity disambiguation findings
   - `engagement-audit` → on-site engagement findings
3. Concatenate all findings lists. Each worker skill's findings arrive without IDs.
4. Assign sequential IDs (`F-001`, `F-002`, ...) ordered by severity (critical → high → medium → low → info).
5. Compute `summary` counts: `total_findings`, `critical`, `high`, `medium`, `low`.
6. Emit the merged JSON object matching the fixed output schema below.
7. If any worker skill fails (network error, timeout, dependency missing), include a
   `low`-severity finding documenting the failure rather than aborting the entire report.

**Runtime budget**: Target < 5 minutes per site. Crawl depth is capped at 15
representative pages; Playwright renders are capped at 8 pages.

**Safety**: Read-only HTTP GET only. No login flows. No destructive actions.
Respects `robots.txt`. Throttled to ≥ 0.5 s between requests.

## Output

A single JSON object conforming to this fixed schema:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 2,
    "low": 1
  },
  "findings": [
    {
      "id": "F-001",
      "title": "No JSON-LD structured data on product pages",
      "severity": "critical",
      "category": "discoverability",
      "skill_source": "structured-data-audit",
      "evidence": "Crawled 12 product pages; 0/12 contain schema.org markup.",
      "suggested_action": {
        "summary": "Add Product/Offer JSON-LD to every product page.",
        "priority": "critical"
      }
    }
  ]
}
```

**Required fields**: `site`, `audited_at`, `summary`, `findings[].id`,
`findings[].title`, `findings[].severity`, `findings[].evidence`,
`findings[].suggested_action.summary`, `findings[].suggested_action.priority`.

**Extension fields** (populated by worker skills): `category`
(`"discoverability"` | `"engagement"`), `skill_source`.

## Running the script

```bash
# Audit a domain and print report to stdout
python skills/audit-orchestrator/scripts/merge_report.py https://example.com

# Write report to a file
python skills/audit-orchestrator/scripts/merge_report.py https://example.com --output report.json
```

Dependencies: `requests`, `beautifulsoup4`, `lxml`, `playwright` (optional;
degrades gracefully if absent). Install with:

```bash
pip install requests beautifulsoup4 lxml playwright
playwright install chromium
```
