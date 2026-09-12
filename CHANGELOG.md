# Changelog

All notable changes to the **Brand AI-Readiness Audit Marketplace** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-12

### Initial Release
- **Multi-skill marketplace**: Modular agent skills architecture adhering to the Agent Skills specification, orchestrated through a single marketplace entrypoint (`marketplace.json`).
- **7 audit workers**: Implemented 1 entrypoint orchestrator and 6 specialized audit workers:
  - `audit-orchestrator`: Concurrent orchestration, fault tolerance, deduplication, and report assembly.
  - `crawl-access-audit`: Evaluates robots.txt rules against 16 AI and search crawlers, HTTP status codes, redirect chains, and sitemap/llms.txt presence.
  - `render-readability-audit`: Quantifies JavaScript render gap between raw HTML and Playwright rendered DOM.
  - `structured-data-audit`: Audits schema.org JSON-LD presence, JSON syntax, required properties, and high-value corroboration markup.
  - `freshness-corroboration-audit`: Cross-checks contact info consistency (phone/address/email) and content freshness timestamps.
  - `entity-clarity-audit`: Evaluates About page disambiguation, legal entity naming, and canonical `sameAs` authorities.
  - `engagement-audit`: Measures broken internal links, navigation hierarchy depth, visible H1 headers, and call-to-action prominence.
- **Schema-compliant report**: Unified JSON report structure enforcing a strict schema floor (`site`, `audited_at` in ISO 8601 UTC with trailing `Z`, integer `summary` severities, ordered `findings` with concrete verification checks, and `beyond_problem_suggestions`).
- **Beyond-problem suggestions**: Generates proactive strategic recommendations (canonical facts page, conversational FAQs, locale variants, email resilience, sitemap freshness) extending beyond problem detection.
- **Test suite**: Comprehensive test suite utilizing `pytest` with 35 tests covering import cleanliness, crawler registry verification, robots parsing, bot-wall challenges, worker fallback tolerance, and strict schema compliance.
- **CI**: Continuous Integration pipeline configured with GitHub Actions (`.github/workflows/ci.yml`) automating dependency installation, Playwright browser setup, and test suite execution on push and pull requests.
