# Changelog

All notable changes to the **Brand AI-Readiness Audit Marketplace** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-12

### Added
- **Entrypoint Skill (`audit-orchestrator`)**:
  - Implemented `merge_report.py` orchestrating 6 worker skills concurrently in parallel worker threads.
  - Fault-tolerant collection ensuring individual worker failures degrade to `low`-severity diagnostic findings without halting overall execution.
  - Deterministic severity-based sorting (`critical` → `high` → `medium` → `low`) and sequential finding ID assignment (`F-001`, `F-002`, ...).
  - Integrated `beyond_problem.py` generating at least 6 proactive strategic recommendations (cross-entity corroboration, canonical facts page, conversational FAQ, locale variants, email-summary resilience, sitemap freshness).
- **Crawl Access Audit (`crawl-access-audit`)**:
  - Validates `robots.txt` compliance against 14 AI crawlers (`GPTBot`, `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`, `Perplexity-User`, `ClaudeBot`, `anthropic-ai`, `Claude-Web`, `Google-Extended`, `CCBot`, `Bytespider`, `Applebot-Extended`, `meta-externalagent`, `cohere-ai`).
  - Added comprehensive crawler registry reference at `skills/crawl-access-audit/references/crawler-registry.md`.
  - RFC 9309 compliance: handles wildcard rules (`User-agent: *`), case-insensitive matching, and treats 404/connection errors as all-allowed in evidence.
  - Emits low-severity diagnostic finding on Cloudflare / bot-wall 403/503 responses: `"Automated access blocked — manual review needed"`.
  - Caps high-link pages (>100 links) at 20 fetches and records the cap in evidence.
  - Robust handling of non-English/multilingual character encodings.
- **Render Readability Audit (`render-readability-audit`)**:
  - Compares raw HTTP response text against Playwright headless DOM rendered text to measure JavaScript render gap percentages.
  - Graceful fallback when Playwright is unavailable.
- **Structured Data Audit (`structured-data-audit`)**:
  - Validates schema.org JSON-LD presence, JSON syntax, required properties, and high-value corroboration fields (`sameAs`, `legalName`).
- **Freshness & Corroboration Audit (`freshness-corroboration-audit`)**:
  - Detects internal fact discrepancies across phone numbers, emails, and addresses.
  - Flags content staleness (>365 days) and missing timestamp metadata (`dateModified`, `datePublished`).
- **Entity Clarity Audit (`entity-clarity-audit`)**:
  - Evaluates brand disambiguation signals: About page depth score (6 categories), Organization `legalName`, and authoritative outbound `sameAs` links.
- **Engagement Audit (`engagement-audit`)**:
  - Audits on-site conversion and navigation heuristics: broken internal links (4xx/5xx), semantic `<nav>`, above-the-fold `<h1>` and CTAs, and breadcrumbs.
- **Standards & Verification**:
  - Standardized all 82 findings across skills to follow: `"<What to change>, populated from <where>, because <mechanism>. Verify: <check>."` with explicit `mechanism`, `fix_effort`, and `verification` fields.
  - 100% Agent Skills specification compliance validated across all 7 skills via `skills-ref validate` (documented in `VALIDATION.md`).
  - Pytest test suite with 34 tests covering robots parsing, registry completeness, schema compliance, worker fallback, and bot-wall handling (`tests/`).
  - GitHub Actions CI workflow (`.github/workflows/ci.yml`) running pytest on push and pull requests.
