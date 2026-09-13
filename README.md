# Brand AI-Readiness Audit Marketplace

[![CI](https://img.shields.io/github/actions/workflow/status/Somya02-PNG/brand-ai-readiness-audit/ci.yml?branch=main&label=CI)](https://github.com/Somya02-PNG/brand-ai-readiness-audit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## What this marketplace does

The Brand AI-Readiness Audit Marketplace audits any public website to identify technical, semantic, and crawlability barriers that prevent AI assistants and answer engines from discovering, reading, and accurately citing brand information. It simultaneously analyzes on-site navigation, structural orientation, and conversion wayfinding to diagnose why visitors referred by generative AI queries bounce instead of engaging with the brand.

---

## Skills

### 1. `audit-orchestrator`
- **Concern**: Entrypoint coordination, spawning all worker audit skills concurrently, aggregating and deduplicating observations, sorting findings strictly by severity, injecting beyond-problem strategic recommendations, and emitting a consolidated schema-compliant JSON report.
- **Inputs**: Target domain or URL string (`sys.argv[1]`) and optional `--output <path>` destination.
- **Outputs**: Consolidated JSON report object containing site metadata, UTC audit timestamp, summary counts by severity, ordered findings, and proactive beyond-problem suggestions.
- **Files**: `skills/audit-orchestrator/SKILL.md`, `skills/audit-orchestrator/scripts/merge_report.py`, `skills/audit-orchestrator/scripts/beyond_problem.py`

### 2. `crawl-access-audit`
- **Concern**: AI bot crawl accessibility via root server responses, `robots.txt` disallow/allow rules evaluated against 16 recognized AI and search crawlers, HTTP redirect hop depths, sitemap reachability, and root `/llms.txt` discovery.
- **Inputs**: Target base URL.
- **Outputs**: Audit findings reporting blocked AI crawlers, excessive redirect hops (>2), bot-wall 403/503 challenges, and missing or unparseable sitemap manifests.
- **Files**: `skills/crawl-access-audit/SKILL.md`, `skills/crawl-access-audit/scripts/check_access.py`, `skills/crawl-access-audit/references/crawler-registry.md`, `skills/crawl-access-audit/references/checks.md`

### 3. `render-readability-audit`
- **Concern**: Measuring the JavaScript "render gap" by computing word-count and textual differences between raw server-delivered HTML and headless browser-rendered DOM, identifying brand facts hidden from non-JS AI crawlers.
- **Inputs**: Target URL and representative page sample URLs.
- **Outputs**: Render gap percentage calculations per page and findings flagging critical brand data (pricing, contact, descriptions) that require client-side JavaScript execution to be visible.
- **Files**: `skills/render-readability-audit/SKILL.md`, `skills/render-readability-audit/scripts/check_render_gap.py`

### 4. `structured-data-audit`
- **Concern**: Presence, syntax validity, completeness, and nesting of schema.org JSON-LD structured data (`Organization`, `Product`, `Article`, `FAQPage`, `LocalBusiness`), evaluating mandatory properties and citation-critical corroboration fields.
- **Inputs**: Target URL and HTML content across sampled page templates.
- **Outputs**: Findings identifying pages lacking structured data, schema syntax errors, missing required properties (e.g., `author`, `offers.price`), and omitted recommended entity fields (`sameAs`, `legalName`).
- **Files**: `skills/structured-data-audit/SKILL.md`, `skills/structured-data-audit/scripts/check_schema.py`

### 5. `freshness-corroboration-audit`
- **Concern**: Cross-page factual corroboration (checking consistency of phone numbers, physical addresses, and email contacts across the domain) and temporal freshness signals (`dateModified`, `datePublished`, `<lastmod>`).
- **Inputs**: Target URL and sampled page contents.
- **Outputs**: Findings highlighting conflicting business contact details across pages, absent publication timestamps, and stale content exceeding 365 days without updates.
- **Files**: `skills/freshness-corroboration-audit/SKILL.md`, `skills/freshness-corroboration-audit/scripts/check_freshness.py`

### 6. `entity-clarity-audit`
- **Concern**: Unambiguous entity identity resolution signals necessary for LLM knowledge graph mapping, including dedicated About page depth, explicit legal entity naming, and authoritative outbound `sameAs` links.
- **Inputs**: Target URL, homepage, and About page.
- **Outputs**: Findings assessing About page entity disambiguation criteria (headquarters, founding year, leadership, scope), missing `legalName` in Organization schema, and absent links to canonical knowledge registries (Wikidata, Wikipedia, Crunchbase, LinkedIn).
- **Files**: `skills/entity-clarity-audit/SKILL.md`, `skills/entity-clarity-audit/scripts/check_entity.py`

### 7. `engagement-audit`
- **Concern**: Structural visitor engagement and conversion architecture, inspecting broken internal links (4xx/5xx), navigation hierarchy depth, visible above-the-fold `<h1>` topic orientation, and primary call-to-action (CTA) prominence.
- **Inputs**: Target URL and sampled internal page links.
- **Outputs**: Findings identifying high percentages of broken internal links, deep navigation trees (>3 levels), orphan pages, missing homepage H1 headings, and absent wayfinding elements (breadcrumbs, search inputs).
- **Files**: `skills/engagement-audit/SKILL.md`, `skills/engagement-audit/scripts/check_engagement.py`, `skills/engagement-audit/references/checks.md`

---

## How the entrypoint composes them

The entrypoint skill `audit-orchestrator` composes all six worker skills into a unified, parallelized audit pipeline:

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
                    │   - Inject proactive strategic  │
                    │     recommendations (≥5 items)  │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │    Final Report Emission        │
                    │   - Strict JSON Schema Floor    │
                    │   - Summary counts calculation  │
                    │   - stdout or --output file     │
                    └─────────────────────────────────┘
```

### Numbered Composition Walkthrough

1. **Input Normalization**: The orchestrator receives the target domain or URL from CLI arguments (`sys.argv[1]`), prepends `https://` if a protocol scheme is omitted, extracts the base hostname, and resolves the canonical origin.
2. **Parallel Worker Dispatch**: Six worker threads are spawned concurrently using Python's `threading.Thread`. Each thread invokes a specialized audit worker script (`check_access.py`, `check_render_gap.py`, `check_schema.py`, `check_freshness.py`, `check_entity.py`, `check_engagement.py`) with identical URL parameters.
3. **Fault-Tolerant Collection**: Worker threads are joined with execution timeouts. If an individual worker script encounters a timeout, connection failure, or unexpected exception, the orchestrator intercepts the failure and synthesizes a `low`-severity diagnostic finding so partial failures never halt the overall audit.
4. **Action & Schema Normalization**: Every finding is validated to ensure its `suggested_action` is a structured dictionary containing `summary` (formatted as `"<What to change>, populated from <where>, because <mechanism>. Verify: <check>."`), `priority`, `mechanism`, `fix_effort`, and `verification`.
5. **Severity Sorting & ID Assignment**: All aggregated findings are sorted deterministically: `critical` first, followed by `high`, `medium`, and `low`. Sequential zero-padded identifiers (`F-001`, `F-002`, `F-003`, ...) are assigned based on this sorted order.
6. **Beyond-Problem Suggestions Generation**: The orchestrator invokes `skills/audit-orchestrator/scripts/beyond_problem.py` to append proactive strategic recommendations (such as establishing a plain-text canonical brand facts page, conversational FAQ markup, cross-entity corroboration, and sitemap freshness signals).
7. **Summary Calculation & Output**: Total finding counts and per-tier breakdowns (`critical`, `high`, `medium`, `low`) are calculated, the audit timestamp is formatted in ISO 8601 UTC with trailing `Z`, and the validated JSON document is emitted to stdout or saved to `--output <path>`.

---

## Report schema

Every audit produces a consolidated JSON report conforming to the required schema floor. See concrete example reports:
- [example-audit-saas.json](example-audit-saas.json) (SaaS Domain Audit)
- [example-audit-ecommerce.json](example-audit-ecommerce.json) (E-Commerce Domain Audit)
- [example-audit-blog.json](example-audit-blog.json) (Editorial/Blog Domain Audit)

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

The marketplace enforces strict operational safety guardrails:
- **Read-Only GET-Only Operations**: All network traffic is strictly confined to read-only HTTP `GET` and `HEAD` requests. No state-mutating requests (`POST`, `PUT`, `DELETE`, `PATCH`) are ever sent.
- **Respects `robots.txt`**: All crawling components strictly adhere to `robots.txt` disallow rules and rate limits per RFC 9309.
- **No Authenticated Areas**: Audits inspect purely public, unauthenticated web content. The system never accepts, stores, or transmits credentials, cookies, API tokens, or session keys, and never attempts to bypass access controls.
- **No Site-Altering Actions**: The marketplace never submits forms, initiates checkout transactions, modifies server configurations, or alters remote state.
- **Per-Worker Fetch Cap of 20**: Each worker enforces a strict ceiling of ≤20 page fetches per audit. Pages containing over 100 internal links are capped at 20 fetches to prevent load spikes on target servers.
- **< 5 Minute Runtime**: Optimized parallel execution and per-worker page limits ensure complete multi-worker audits conclude in under 5 minutes.

For detailed security policies and vulnerability reporting procedures, see [SECURITY.md](SECURITY.md).

---

## Validation

All 7 skills in this repository have been validated against the official Agent Skills specification using the reference tool `skills-ref`.

Full validation commands, terminal execution logs, and detailed checklists confirming frontmatter, deterministic procedures, and read-only behavior for every skill are documented in [VALIDATION.md](VALIDATION.md).

See [TESTING.md](TESTING.md) for real-world validation evidence across 8 unseen websites, including bugs discovered and fixed during testing.

---

## Testing

The automated test suite runs via `pytest` without requiring live internet access, utilizing local static HTML fixtures and mock HTTP transports:

```bash
# Run the full test suite quietly
pytest -q
```

### Test Suite Highlights
- **Import Verification** (`test_imports.py`): Ensures all skill scripts import cleanly without missing dependencies or syntax errors.
- **Crawler Registry Verification** (`test_crawler_registry.py`): Validates all 16 recognized AI and search crawlers and their respective user-agent tokens.
- **Robots Parser & Edge Cases** (`test_robots_parser.py`, `test_crawl_access.py`): Verifies RFC 9309 compliance, 404 all-allowed handling, bot-wall 403 challenge detection, and the 20-fetch cap on dense link pages.
- **Schema & Action Compliance** (`test_schema_compliance.py`): Enforces the required JSON schema floor, ID sorting, and the action string pattern across findings.
- **Orchestration & Merging** (`test_merge_report.py`): Tests worker aggregation, fault tolerance, and summary metric calculations.

---

## Repo layout

```
brand-ai-readiness-audit/
├── .editorconfig                          ← Code formatting rules (UTF-8, LF, 4-space py, 2-space json/md)
├── .gitignore                             ← Git exclusion rules
├── .github/
│   └── workflows/
│       └── ci.yml                         ← GitHub Actions CI workflow running pytest
├── CHANGELOG.md                           ← Version history & release notes
├── LICENSE                                ← MIT License
├── README.md                              ← Marketplace documentation
├── SECURITY.md                            ← Safety guardrails & read-only policy
├── TESTING.md                             ← Real-world testing evidence & bugs found
├── VALIDATION.md                          ← Agent Skills specification validation logs
├── marketplace.json                       ← agentskills.io marketplace entrypoint definition
├── requirements.txt                       ← Pinned dependencies
├── example-audit-blog.json                ← Reference audit report (Editorial/Blog)
├── example-audit-ecommerce.json           ← Reference audit report (E-commerce)
├── example-audit-saas.json                ← Reference audit report (SaaS)
├── skills/
│   ├── audit-orchestrator/                ← ENTRYPOINT SKILL
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── merge_report.py            ← Parallel worker orchestration & report merging
│   │       └── beyond_problem.py          ← Proactive strategic recommendations generator
│   ├── crawl-access-audit/                ← WORKER SKILL 1
│   │   ├── SKILL.md
│   │   ├── references/
│   │   │   ├── checks.md                  ← Crawl access criteria & pass conditions
│   │   │   └── crawler-registry.md        ← Registry of 16 AI and search crawlers
│   │   └── scripts/
│   │       └── check_access.py            ← robots.txt, status codes & sitemap audit
│   ├── render-readability-audit/          ← WORKER SKILL 2
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_render_gap.py        ← Raw HTML vs. Playwright render gap analysis
│   ├── structured-data-audit/             ← WORKER SKILL 3
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_schema.py            ← schema.org JSON-LD extraction & audit
│   ├── freshness-corroboration-audit/     ← WORKER SKILL 4
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_freshness.py         ← Fact consistency & freshness audit
│   ├── entity-clarity-audit/              ← WORKER SKILL 5
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       └── check_entity.py            ← About page, sameAs, & legalName audit
│   └── engagement-audit/                  ← WORKER SKILL 6
│       ├── SKILL.md
│       ├── references/
│       │   └── checks.md                  ← Visitor engagement criteria
│       └── scripts/
│           └── check_engagement.py        ← Navigation, broken links, & CTA audit
└── tests/                                 ← Automated pytest test suite
    ├── __init__.py
    ├── conftest.py                        ← Test fixtures & path setup
    ├── fixtures/                          ← Static HTML & robots.txt fixtures
    │   ├── cloudflare_403.html
    │   ├── page_js_only.html
    │   ├── page_many_links.html
    │   ├── page_non_english.html
    │   ├── page_ssr.html
    │   ├── robots_block_gptbot.txt
    │   └── robots_partial_block.txt
    ├── test_beyond_problem.py             ← Strategic beyond-problem suggestions tests
    ├── test_crawl_access.py               ← Crawl access, bot-walls & fetch cap tests
    ├── test_crawler_registry.py           ← 16 AI & search bot registry validation tests
    ├── test_imports.py                    ← Clean import verification for all skill scripts
    ├── test_merge_report.py               ← Aggregation, sorting & worker fallback tests
    ├── test_render_gap.py                 ← Playwright headless SSR vs. JS render gap tests
    ├── test_robots_parser.py              ← robots.txt parser & edge cases tests
    └── test_schema_compliance.py          ← JSON schema floor & action pattern tests
```
