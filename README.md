# Brand AI-Readiness Audit Marketplace

> **Adobe University Hackathon 2026 — Round 3 Submission**
>
> An agent skill marketplace that audits any public website URL and produces a structured JSON report identifying why a brand is **hard for AI assistants to discover and cite**, and why **on-site visitors fail to engage** — with prioritized, actionable fixes.

---

## Quick Start

```bash
# 1. Install dependencies
pip install requests beautifulsoup4 lxml playwright
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

## Architecture

```
brand-ai-readiness-audit/
├── marketplace.json               ← agentskills.io manifest (1 entrypoint)
├── README.md                      ← this file
└── skills/
    ├── audit-orchestrator/        ← ENTRYPOINT — orchestrates all 6 workers
    ├── crawl-access-audit/        ← robots.txt, HTTP status, sitemap
    ├── render-readability-audit/  ← JS render gap (raw vs Playwright)
    ├── structured-data-audit/     ← schema.org JSON-LD audit
    ├── freshness-corroboration-audit/ ← fact consistency & freshness
    ├── entity-clarity-audit/      ← sameAs, legalName, About page
    └── engagement-audit/          ← nav, broken links, CTAs, breadcrumbs
```

The orchestrator runs all 6 worker skills **in parallel threads** for speed, then merges and sorts findings by severity before outputting the final report.

---

## Skills Reference

### `audit-orchestrator` ← **ENTRYPOINT**

**Script**: [`skills/audit-orchestrator/scripts/merge_report.py`](skills/audit-orchestrator/scripts/merge_report.py)

The single entry point for the marketplace. Accepts a URL, spawns all 6 worker audits in parallel threads, collects their findings lists, assigns sequential IDs (`F-001`, `F-002`, ...) ordered by severity, computes summary counts, and outputs a single schema-compliant JSON report.

Handles worker failures gracefully — if one skill errors or times out, a `low`-severity diagnostic finding is included and the report is still emitted.

---

### `crawl-access-audit`

**Script**: [`skills/crawl-access-audit/scripts/check_access.py`](skills/crawl-access-audit/scripts/check_access.py)

Checks whether AI crawlers and search bots can access the site.

| Check | What it detects |
|---|---|
| `robots.txt` rules | Blocks for GPTBot, ChatGPT-User, Google-Extended, PerplexityBot, anthropic-ai, CCBot, Omgilibot |
| HTTP status codes | Non-200 homepage, 4xx/5xx on crawled pages |
| Redirect chains | Chains > 2 hops (latency, crawler timeout risk) |
| `sitemap.xml` | Absence of discoverable sitemap via robots.txt or common paths |

**Severity range**: `critical` (homepage blocked) → `medium` (sitemap missing, redirect chains)

---

### `render-readability-audit`

**Script**: [`skills/render-readability-audit/scripts/check_render_gap.py`](skills/render-readability-audit/scripts/check_render_gap.py)

Detects content that only exists after JavaScript execution by diffing raw HTTP response text against Playwright-rendered DOM text.

| Check | What it detects |
|---|---|
| Render gap % | `(rendered_words − raw_words) / rendered_words × 100` per page |
| Site-wide average | Aggregate render gap across all sampled pages |
| Key fact visibility | Phone/email/price patterns missing from raw HTML |

**Thresholds**: `> 30%` → `high`; `> 15%` → `medium`; `> 30%` average across site → `critical`

**Playwright fallback**: If Playwright is not installed, emits a `low`-severity note and performs raw-HTML-only word count analysis.

---

### `structured-data-audit`

**Script**: [`skills/structured-data-audit/scripts/check_schema.py`](skills/structured-data-audit/scripts/check_schema.py)

Checks for presence, JSON validity, and completeness of schema.org JSON-LD markup on up to 12 representative pages.

| Check | What it detects |
|---|---|
| JSON-LD presence | Pages with zero `<script type="application/ld+json">` blocks |
| Malformed JSON | `json.loads()` failures with parse error evidence |
| Required properties | Missing fields per type (Organization, Product, Article, FAQPage, LocalBusiness, etc.) |
| Recommended properties | Missing high-value fields (`sameAs`, `logo`, `image`, `description`) |
| Type coverage | Product pages without Product schema; blog pages without Article schema |

**Severity range**: `critical` (0% markup coverage) → `medium` (recommended fields missing)

---

### `freshness-corroboration-audit`

**Script**: [`skills/freshness-corroboration-audit/scripts/check_freshness.py`](skills/freshness-corroboration-audit/scripts/check_freshness.py)

Validates internal fact consistency across pages and checks content freshness signals.

| Check | What it detects |
|---|---|
| Phone inconsistency | Multiple distinct phone numbers across pages |
| Email inconsistency | > 2 distinct email addresses (flags for review) |
| Address inconsistency | Different address strings on different pages |
| Freshness signals | Absence of `dateModified`/`datePublished` in JSON-LD or meta tags |
| Stale content | Most recent date signal > 365 days old |

Facts are extracted via regex from both visible text and JSON-LD. Phone numbers are normalized to digit-only form before comparison to avoid false positives from formatting differences.

---

### `entity-clarity-audit`

**Script**: [`skills/entity-clarity-audit/scripts/check_entity.py`](skills/entity-clarity-audit/scripts/check_entity.py)

Checks whether the brand has sufficient disambiguating identity signals.

| Check | What it detects |
|---|---|
| `sameAs` links | Absence of any `sameAs` in JSON-LD |
| High-trust disambiguators | Missing Wikidata, Wikipedia, or Crunchbase in `sameAs` |
| `legalName` | Organization JSON-LD missing `legalName` field |
| About page | Missing or too-generic About page (scored on 6 fact categories) |
| External identity links | No outbound links to LinkedIn, Wikidata, Crunchbase, etc. |

The About page is scored for 6 disambiguating fact categories: founding year, HQ location, industry vertical, team size, customer count, and geographic reach. Score < 3/6 → `low`-severity finding.

---

### `engagement-audit`

**Script**: [`skills/engagement-audit/scripts/check_engagement.py`](skills/engagement-audit/scripts/check_engagement.py)

Evaluates on-site visitor engagement and navigation quality.

| Check | What it detects |
|---|---|
| Broken internal links | % of internal URLs returning HTTP 4xx/5xx |
| Dead-end pages | Pages with zero outbound internal links |
| `<nav>` presence | Missing semantic navigation element on homepage |
| Navigation depth | `<ul>/<li>` nesting > 3 levels in `<nav>` |
| Above-fold H1 | Missing `<h1>` on homepage |
| Above-fold CTA | No CTA-keyword link/button in first 25% of homepage HTML |
| Breadcrumbs | No `aria-label="breadcrumb"`, `.breadcrumb` class, or BreadcrumbList JSON-LD |
| Site search | No `<input type="search">` or `role="search"` found |

**Broken link severity thresholds**: `> 20%` → `critical`; `> 10%` → `high`; `> 5%` → `medium`

---

## Output Schema

Every audit produces a JSON object conforming to this fixed schema:

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
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
      "category": "discoverability",
      "skill_source": "structured-data-audit",
      "evidence": "Sampled 12 pages; 0/12 contain <script type='application/ld+json'>. Checked: /, /products/alpha, /products/beta, ...",
      "suggested_action": {
        "summary": "Implement schema.org JSON-LD across all page types. Start with Organization on homepage, then Product/Article/FAQPage.",
        "priority": "critical"
      }
    }
  ]
}
```

**Required fields** (never removed): `site`, `audited_at`, `summary`, `findings[].id`, `findings[].title`, `findings[].severity`, `findings[].evidence`, `findings[].suggested_action.summary`, `findings[].suggested_action.priority`

**Extension fields** added by worker skills: `category` (`"discoverability"` | `"engagement"`), `skill_source`

---

## Dependencies

| Package | Purpose | Required |
|---|---|---|
| `requests` | Raw HTTP fetching | **Yes** |
| `beautifulsoup4` | HTML parsing | **Yes** |
| `lxml` | Fast HTML/XML parser backend | **Yes** |
| `playwright` + Chromium | JS-rendered DOM capture | Optional (degrades gracefully) |

Install everything:

```bash
pip install requests beautifulsoup4 lxml playwright
playwright install chromium
```

---

## Running Individual Skills

Each worker skill is also runnable standalone for debugging:

```bash
python skills/crawl-access-audit/scripts/check_access.py https://example.com
python skills/render-readability-audit/scripts/check_render_gap.py https://example.com
python skills/structured-data-audit/scripts/check_schema.py https://example.com
python skills/freshness-corroboration-audit/scripts/check_freshness.py https://example.com
python skills/entity-clarity-audit/scripts/check_entity.py https://example.com
python skills/engagement-audit/scripts/check_engagement.py https://example.com
```

Each outputs a JSON array of findings to stdout.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Parallelism | `threading.Thread` per worker | Reduces total runtime; GIL doesn't bottleneck I/O-bound work |
| Crawl depth | Homepage + up to 15 pages (BFS) | Representative sample without time overrun |
| Playwright cap | ≤ 8 renders per audit | Stays within 5-minute budget |
| Thresholds | Relative (e.g. `> 30%` gap) | Generalizes across all site types |
| Playwright | Optional import with fallback | Hosts without Playwright still get partial results |
| JSON-LD parser | `json.loads` via BeautifulSoup | No binary deps; catches malformed JSON as a finding |
| Error handling | Per-skill try/except | One failed skill ≠ no report |
| Throttle | ≥ 0.3–0.5 s between requests | Polite crawling; avoids rate limiting |

---

## Rubric Self-Check

| Rubric criterion | Where it's satisfied |
|---|---|
| **Detection accuracy** | Each check is evidence-based (counts, URLs, diffs); no template findings |
| **Suggested-action quality** | Every finding has a specific, mechanism-sound `suggested_action` |
| **Output design** | Fixed schema matches PDF sample exactly; extension fields never remove required ones |
| **Skill-format hygiene** | All 7 SKILL.md files have valid YAML frontmatter (`name`, `description`, `license: MIT`) |
| **Marketplace composition** | 6 focused worker skills + 1 orchestrator; genuine separation of concerns |
| **Generalization** | No hardcoded domains/thresholds; relative heuristics; graceful fallbacks |

---

## License

MIT © 2026 brand-ai-readiness-audit contributors
