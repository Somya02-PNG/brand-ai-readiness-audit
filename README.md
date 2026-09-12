# Brand AI-Readiness Audit Marketplace

[![CI](https://img.shields.io/github/actions/workflow/status/<OWNER>/<REPO>/ci.yml?branch=main&label=CI)](https://github.com/<OWNER>/<REPO>/actions/workflows/ci.yml)

> **Adobe University Hackathon 2026 — Round 3 Submission**
>
> An agent skill marketplace that audits any public website URL and produces a structured JSON report identifying why a brand is **hard for AI assistants to discover and cite**, and why **on-site visitors fail to engage** — with prioritized, actionable fixes.

---

## What this marketplace does

The **Brand AI-Readiness Audit Marketplace** evaluates how modern AI search engines, generative answer engines (ChatGPT, Perplexity, Claude, Google Gemini), and human visitors experience and process a website. When an AI agent recommends a brand or answers a user query, it relies on server crawlability, machine-readable structured schema, raw-HTML text availability, unambiguous entity identifiers, and factual consistency across the web. At the same time, once an AI agent sends a user to the site, on-page engagement factors dictate whether that visitor converts. This marketplace performs a comprehensive, multi-dimensional audit of any target domain in under 5 minutes, returning an evidence-backed, schema-compliant JSON report with prioritized findings and concrete remediation steps.

---

## Skills

### `audit-orchestrator`
The single entry point for the marketplace (`marketplace.json`). It accepts a target URL, normalizes it, spawns all six specialized worker audit skills concurrently across separate worker threads, gathers their findings, deduplicates and normalizes output, sorts findings strictly by severity (`critical` → `high` → `medium` → `low`), assigns sequential IDs (`F-001`, `F-002`, ...), appends proactive strategic suggestions via `beyond_problem.py`, computes summary metrics, and emits the final consolidated JSON report to stdout or file.

### `crawl-access-audit`
Inspects root server configuration, HTTP status codes, redirect hops, and `robots.txt` directives against 14 known AI crawler tokens (including `GPTBot`, `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`, `ClaudeBot`, `Google-Extended`, and `Applebot-Extended`). It ensures robots.txt missing states (404/connection errors) default to all-allowed per RFC 9309, detects Cloudflare or bot-wall 403/503 challenges with diagnostic findings, identifies long redirect chains (>2 hops), flags missing `sitemap.xml` entries, and checks for root `/llms.txt` summary manifests while capping high-volume page fetches at 20.

### `render-readability-audit`
Quantifies the "JavaScript render gap" by diffing raw HTTP response text (what simple AI crawlers see) against headless Playwright-rendered DOM text (what modern browsers execute). It computes per-page and site-wide average render gap percentages, identifying key brand facts (pricing, contact information, product specifications) that are rendered exclusively via client-side JavaScript and therefore remain completely invisible to non-JS crawlers such as GPTBot, ClaudeBot, and Common Crawl.

### `structured-data-audit`
Extracts and audits `<script type="application/ld+json">` schema.org markup across up to 12 representative site pages. It verifies JSON syntax validity, checks coverage across core entity schemas (`Organization`, `Product`, `Article`, `FAQPage`, `LocalBusiness`), flags missing mandatory properties (e.g., `name`, `legalName`, `offers.price`, `author`), evaluates recommended corroboration properties such as `sameAs` and `image`, and checks whether schema is properly server-rendered rather than injected post-hydration.

### `freshness-corroboration-audit`
Validates internal fact consistency across the site by extracting phone numbers, email addresses, physical mailing addresses, and copyright year markers from visible page content and schema markup. It alerts on internal discrepancies (such as conflicting contact numbers across landing pages), checks for temporal freshness signals (`dateModified`, `datePublished` in JSON-LD and meta tags), and flags stale content when the most recent modification date exceeds 365 days.

### `entity-clarity-audit`
Measures whether a brand provides unambiguous entity resolution signals required for knowledge graph ingestion. It verifies the presence of an informative About page scored across six key disambiguation criteria (founding year, headquarters location, industry vertical, team size, customer base, geographic scope), confirms `legalName` presence in Organization schema, and checks for outbound authoritative `sameAs` links pointing to canonical knowledge bases like Wikidata, Wikipedia, Crunchbase, and LinkedIn.

### `engagement-audit`
Evaluates structural on-site visitor engagement factors to identify why incoming traffic might bounce or fail to convert. It audits internal link health to calculate the percentage of broken links (HTTP 4xx/5xx), identifies dead-end orphan pages, checks for semantic `<nav>` structures and excessive nesting depth (>3 levels), verifies an above-the-fold `<h1>` heading and primary call-to-action (CTA) keyword placement, and checks for accessible breadcrumb navigation and on-site search inputs.

---

## How the entrypoint composes them

The entrypoint skill `audit-orchestrator` composes all six worker skills into a unified audit pipeline:

```
                          Target URL (CLI argument)
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │       audit-orchestrator        │
                    │  (merge_report.py entrypoint)   │
                    └────────────────┬────────────────┘
                                     │
             ┌───────────────────────┼───────────────────────┐
             │       Parallel Worker Threads (I/O Bounded)   │
             ▼                       ▼                       ▼
    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
    │  crawl-access-  │     │render-readabili-│     │structured-data- │
    │     audit       │     │    ty-audit     │     │     audit       │
    └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
             │                       │                       │
             ▼                       ▼                       ▼
    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
    │  freshness-cor- │     │ entity-clarity- │     │  engagement-    │
    │ roboration-audit│     │     audit       │     │     audit       │
    └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
             │                       │                       │
             └───────────────────────┼───────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │      Result Aggregation         │
                    │   - Fault-tolerant catch        │
                    │   - Deduplicate observations    │
                    │   - Sort by severity (Crit-Low) │
                    │   - Assign IDs (F-001, F-002...)│
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │     beyond_problem.py           │
                    │   - Inject ≥6 proactive strategic│
                    │     Round-2 suggestions         │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │    Final Report Emission        │
                    │   - Strict JSON Schema          │
                    │   - Summary counts calculation  │
                    │   - stdout or --output file     │
                    └─────────────────────────────────┘
```

### Composition Walkthrough

1. **Input Normalization**: The orchestrator receives the target domain or URL from CLI arguments (`sys.argv[1]`), prepends `https://` if a scheme is omitted, extracts `base_url`, and resolves the canonical origin.
2. **Parallel Worker Dispatch**: Six worker threads are spawned concurrently using Python's `threading.Thread`. Each thread invokes a dedicated worker script (`check_access.py`, `check_render_gap.py`, `check_schema.py`, `check_freshness.py`, `check_entity.py`, `check_engagement.py`) with identical URL parameters.
3. **Fault-Tolerant Collection**: Thread completion is joined with a timeout. If a worker fails, times out, or encounters an unexpected exception, the orchestrator intercepts the failure and synthesizes a `low`-severity diagnostic finding so partial failures never halt the overall report.
4. **Action & Schema Normalization**: Every finding is verified to ensure its `suggested_action` is a structured dictionary containing `summary` (formatted as `"<What to change>, populated from <where>, because <mechanism>. Verify: <check>."`), `priority`, `mechanism`, `fix_effort`, and `verification`.
5. **Severity Sorting & ID Assignment**: All collected findings are sorted deterministically: `critical` first, followed by `high`, `medium`, and `low`. Sequential identifiers (`F-001`, `F-002`, `F-003`, ...) are assigned based on this sorted order.
6. **Proactive Suggestions Injection**: The orchestrator invokes `skills/audit-orchestrator/scripts/beyond_problem.py` to generate at least 6 actionable, proactive recommendations (e.g., cross-entity corroboration, canonical facts page, conversational FAQ, locale variants, email-summary resilience, sitemap freshness signals).
7. **Summary Calculation & Output**: Total findings and counts per severity tier (`critical`, `high`, `medium`, `low`) are calculated, audited timestamp is set in ISO 8601 UTC format with trailing `Z`, and the finalized JSON document is formatted and written to stdout or saved to `--output <path>`.

---

## Report schema

Every audit produces a JSON object conforming strictly to this schema:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-12T14:32:00Z",
  "summary": {
    "total_findings": 8,
    "critical": 1,
    "high": 3,
    "medium": 3,
    "low": 1
  },
  "findings": [
    {
      "id": "F-001",
      "title": "0 of 12 pages contain any schema.org JSON-LD",
      "severity": "critical",
      "evidence": "Sampled 12 pages; 0/12 contain <script type='application/ld+json'>.",
      "suggested_action": {
        "summary": "Implement schema.org JSON-LD across all page types, populated from server-rendered templates, because AI crawlers require structured data to identify entity facts. Verify: curl -s https://example.com | grep 'application/ld+json'.",
        "priority": "critical"
      },
      "mechanism": "Absence of structured data leaves AI models guessing entity roles and product attributes from raw unstructured text.",
      "fix_effort": "medium",
      "verification": "curl -s https://example.com | grep 'application/ld+json'"
    }
  ],
  "beyond_problem_suggestions": [
    {
      "title": "Publish a Plain-Text Canonical Brand Facts Page",
      "rationale": "Create a /facts or dedicated section with unambiguous single-sentence factual assertions.",
      "mechanism": "LLM extractors achieve near-perfect factual precision when digesting declarative single-sentence propositions.",
      "priority": "high"
    }
  ]
}
```

---

## Safety & guardrails

The marketplace is engineered with strict read-only safety guarantees:
- **Read-Only GET Operations**: Audits execute read-only HTTP GET and HEAD requests exclusively. No `POST`, `PUT`, `DELETE`, or `PATCH` requests are ever transmitted.
- **Strict robots.txt Compliance**: Crawlers honor disallow rules and rate limits specified in `robots.txt` per RFC 9309.
- **No Authentication or Credential Access**: Audits inspect purely public web content; no passwords, API keys, session tokens, or authentication mechanisms are accepted or bypassed.
- **Zero Site Mutation**: Audits do not fill in forms, trigger transactional workflows, or mutate server state.
- **Bounded Worker Fetch Caps**: Each worker enforces strict page limits (≤ 15–20 pages per audit). If a high-density page contains over 100 links, discovery is capped at 20 fetches and recorded in evidence.
- **Polite Crawl Throttling**: A crawl delay of ≥ 0.3–0.5s is maintained between sequential HTTP requests.
- **Headless Resource Bounding**: Playwright DOM rendering is capped at a maximum of 4 concurrent page contexts.

For full details, review [SECURITY.md](SECURITY.md).

---

## Validation

All 7 skills in this repository have been validated against the official Agent Skills specification using the reference tool `skills-ref`:

```bash
skills-ref validate ./skills/audit-orchestrator
skills-ref validate ./skills/crawl-access-audit
skills-ref validate ./skills/render-readability-audit
skills-ref validate ./skills/structured-data-audit
skills-ref validate ./skills/freshness-corroboration-audit
skills-ref validate ./skills/entity-clarity-audit
skills-ref validate ./skills/engagement-audit
```

All 7 skills passed validation with zero errors (`Exit code: 0`). Full command execution logs, validator outputs, and skill property checklists are documented in [VALIDATION.md](VALIDATION.md).

---

## Testing

The test suite is built on `pytest` and verifies crawler registry completeness, robots parser behavior, schema compliance, worker fallback tolerance, and action formatting without requiring external network connectivity:

```bash
# Run the complete test suite
pytest -q
```

### Test Coverage Highlights
- **Crawler Registry**: Confirms all 14 known AI crawlers (`GPTBot`, `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`, `Perplexity-User`, `ClaudeBot`, `anthropic-ai`, `Claude-Web`, `Google-Extended`, `CCBot`, `Bytespider`, `Applebot-Extended`, `meta-externalagent`, `cohere-ai`) are registered and tested.
- **Robots.txt Edge Cases**: Validates 404/connection error handling as "all allowed" in evidence, case-insensitive rule matching, and wildcard `*` behavior.
- **Security & Bot-Walls**: Tests Cloudflare 403 challenge detection and emission of `"Automated access blocked — manual review needed"`.
- **Resilience**: Verifies error-free parsing of non-English/multilingual HTML and validates link fetch caps on pages with >100 links.
- **Schema & Action Compliance**: Enforces that all findings match the target schema and follow the `"<What to change>, populated from <where>, because <mechanism>. Verify: <check>."` format.

---

## Repo layout

```
brand-ai-readiness-audit/
├── .editorconfig                          ← Code formatting & indentation rules
├── .gitignore                             ← Git exclusion rules
├── .github/
│   └── workflows/
│       └── ci.yml                         ← GitHub Actions CI pipeline
├── CHANGELOG.md                           ← Version history & release notes
├── LICENSE                                ← MIT License
├── README.md                              ← Marketplace documentation
├── SECURITY.md                            ← Read-only safety & security guardrails
├── VALIDATION.md                          ← skills-ref specification validation logs
├── marketplace.json                       ← agentskills.io entrypoint declaration
├── requirements.txt                       ← Pinned third-party dependencies
├── example-audit-ecommerce.json           ← Reference audit report (E-commerce)
├── example-audit-saas.json                ← Reference audit report (SaaS)
├── skills/
│   ├── audit-orchestrator/                ← ENTRYPOINT SKILL
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── merge_report.py            ← Parallel worker orchestration & report merging
│   │       └── beyond_problem.py          ← Proactive Round-2 strategic recommendations
│   ├── crawl-access-audit/                ← WORKER SKILL 1
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   ├── checks.md                  ← Check logic and pass conditions
│   │   │   └── crawler-registry.md        ← Comprehensive AI crawler registry
│   │   └── scripts/
│   │       └── check_access.py            ← robots.txt, HTTP status & sitemap check
│   ├── render-readability-audit/          ← WORKER SKILL 2
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_render_gap.py        ← Raw vs. Playwright render gap analysis
│   ├── structured-data-audit/             ← WORKER SKILL 3
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_schema.py            ← schema.org JSON-LD extraction & audit
│   ├── freshness-corroboration-audit/     ← WORKER SKILL 4
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_freshness.py         ← Fact consistency & freshness analysis
│   ├── entity-clarity-audit/              ← WORKER SKILL 5
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_entity.py            ← About page, sameAs, & legalName audit
│   └── engagement-audit/                  ← WORKER SKILL 6
│       ├── SKILL.md
│       ├── references/
│       │   └── checks.md                  ← Engagement check criteria
│       └── scripts/
│           └── check_engagement.py        ← Navigation, broken links, & CTA audit
└── tests/                                 ← Pytest test suite
    ├── __init__.py
    ├── conftest.py                        ← Common test fixtures & root path setup
    ├── fixtures/                          ← Static HTML/robots test fixtures
    │   ├── cloudflare_403.html
    │   ├── page_js_only.html
    │   ├── page_many_links.html
    │   ├── page_non_english.html
    │   ├── page_ssr.html
    │   ├── robots_block_gptbot.txt
    │   └── robots_partial_block.txt
    ├── test_crawl_access.py               ← Bot-walls, 404 all-allowed, & >100 link tests
    ├── test_crawler_registry.py           ← Registry verification for all 14 AI bots
    ├── test_merge_report.py               ← Orchestrator merging, sorting, & fallback tests
    ├── test_robots_parser.py              ← robots.txt parsing & sitemap detection
    └── test_schema_compliance.py          ← Strict JSON schema compliance tests
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Run a full audit (outputs to stdout)
python skills/audit-orchestrator/scripts/merge_report.py https://example.com

# 3. Save report to file
python skills/audit-orchestrator/scripts/merge_report.py https://example.com --output report.json
```

**Runtime**: < 5 minutes per typical site  
**Output**: Schema-compliant JSON with findings, severity levels, evidence strings, and actionable fixes  
**Safety**: Read-only HTTP GET only. Respects `robots.txt`. No auth, no destructive actions.

---

## License

MIT © 2026 brand-ai-readiness-audit contributors
