# Skills Specification Validation Report

This document records the automated validation of all 7 skills in the **Brand AI-Readiness Audit Marketplace** against the official [Agent Skills specification](https://agentskills.io) using the reference validation tool `skills-ref` (v0.1.1).

---

## Validation Overview

Each skill directory was validated using `skills-ref validate <skill-path>`.

The validator verifies:
1. **Valid YAML Frontmatter**: Delimited by `---`, compliant with strict YAML parsing (`strictyaml`).
2. **Required Core Metadata**:
   - `name`: Must match the directory name, adhere to lowercase kebab-case, and contain no disallowed punctuation.
   - `description`: Non-empty description explaining when and how an agent invokes the skill.
   - `license`: Declared license (MIT).
3. **Execution Metadata**:
   - `metadata.entrypoint`: Correctly flags `"true"` for the orchestrator and `"false"` for workers.
4. **Deterministic Procedures**: Ordered, step-by-step procedures with input declarations, tool usage requirements, and structured JSON output definitions.
5. **Read-Only Safety**: Strictly non-destructive HTTP GET audits; no state-modifying requests, auth bypass, or site-altering actions.

---

## Validation Commands & Full Execution Output

```bash
$ pip install skills-ref
Requirement already satisfied: skills-ref in ... (0.1.1)

$ skills-ref validate ./skills/audit-orchestrator
Valid skill: skills\audit-orchestrator

$ skills-ref validate ./skills/crawl-access-audit
Valid skill: skills\crawl-access-audit

$ skills-ref validate ./skills/render-readability-audit
Valid skill: skills\render-readability-audit

$ skills-ref validate ./skills/structured-data-audit
Valid skill: skills\structured-data-audit

$ skills-ref validate ./skills/freshness-corroboration-audit
Valid skill: skills\freshness-corroboration-audit

$ skills-ref validate ./skills/entity-clarity-audit
Valid skill: skills\entity-clarity-audit

$ skills-ref validate ./skills/engagement-audit
Valid skill: skills\engagement-audit
```

### Result Summary

| Skill Directory | Entrypoint | `skills-ref` Status | Exit Code |
|---|---|---|---|
| [`skills/audit-orchestrator`](skills/audit-orchestrator/SKILL.md) | **True** (Primary) | **Valid skill** | `0` |
| [`skills/crawl-access-audit`](skills/crawl-access-audit/SKILL.md) | False (Worker) | **Valid skill** | `0` |
| [`skills/render-readability-audit`](skills/render-readability-audit/SKILL.md) | False (Worker) | **Valid skill** | `0` |
| [`skills/structured-data-audit`](skills/structured-data-audit/SKILL.md) | False (Worker) | **Valid skill** | `0` |
| [`skills/freshness-corroboration-audit`](skills/freshness-corroboration-audit/SKILL.md) | False (Worker) | **Valid skill** | `0` |
| [`skills/entity-clarity-audit`](skills/entity-clarity-audit/SKILL.md) | False (Worker) | **Valid skill** | `0` |
| [`skills/engagement-audit`](skills/engagement-audit/SKILL.md) | False (Worker) | **Valid skill** | `0` |

---

## Detailed Skill Verification Checklist

### 1. `audit-orchestrator`
- [x] **Valid YAML Frontmatter**: Clean block at top of `SKILL.md`.
- [x] **Name + Description + License**: `name: audit-orchestrator`, complete description, `license: MIT`.
- [x] **Entrypoint Declaration**: `metadata.entrypoint: "true"`.
- [x] **Deterministic Procedure**: Documents input normalization, parallel thread invocation of 6 workers, finding deduplication, severity sorting, and sequential `F-XXX` ID assignment.
- [x] **Declared Tools**: Python 3.11+, standard library `subprocess`/`threading`/`json`.
- [x] **Read-Only / No Site Altering**: Aggregates output from local child audit processes; executes no network mutation.

### 2. `crawl-access-audit`
- [x] **Valid YAML Frontmatter**: Clean block at top of `SKILL.md`.
- [x] **Name + Description + License**: `name: crawl-access-audit`, complete description, `license: MIT`.
- [x] **Entrypoint Declaration**: `metadata.entrypoint: "false"`.
- [x] **Deterministic Procedure**: Evaluates robots.txt rules against 14 AI crawlers, probes HTTP status, tests redirect chains, checks sitemap.xml reachability.
- [x] **Declared Tools**: `requests`, `urllib.robotparser`, `bs4`, `lxml`.
- [x] **Read-Only / No Site Altering**: Non-destructive HTTP GET queries with polite throttling (≥0.5s delay) and max page caps.

### 3. `render-readability-audit`
- [x] **Valid YAML Frontmatter**: Clean block at top of `SKILL.md`.
- [x] **Name + Description + License**: `name: render-readability-audit`, complete description, `license: MIT`.
- [x] **Entrypoint Declaration**: `metadata.entrypoint: "false"`.
- [x] **Deterministic Procedure**: Compares raw HTML word count vs. Playwright rendered DOM text to compute percentage render gap.
- [x] **Declared Tools**: `requests`, `playwright` (headless Chromium).
- [x] **Read-Only / No Site Altering**: Read-only browser navigation; does not click destructive controls or submit forms.

### 4. `structured-data-audit`
- [x] **Valid YAML Frontmatter**: Clean block at top of `SKILL.md`.
- [x] **Name + Description + License**: `name: structured-data-audit`, complete description, `license: MIT`.
- [x] **Entrypoint Declaration**: `metadata.entrypoint: "false"`.
- [x] **Deterministic Procedure**: Extracts `<script type="application/ld+json">`, validates JSON syntax, verifies required schema.org entity types.
- [x] **Declared Tools**: `requests`, `bs4`, `json`.
- [x] **Read-Only / No Site Altering**: Passive HTML inspection; no write operations.

### 5. `freshness-corroboration-audit`
- [x] **Valid YAML Frontmatter**: Clean block at top of `SKILL.md`.
- [x] **Name + Description + License**: `name: freshness-corroboration-audit`, complete description, `license: MIT`.
- [x] **Entrypoint Declaration**: `metadata.entrypoint: "false"`.
- [x] **Deterministic Procedure**: Scans crawled pages for conflicting telephone numbers, email addresses, postal addresses, and copyright year staleness.
- [x] **Declared Tools**: `requests`, `bs4`, `re`.
- [x] **Read-Only / No Site Altering**: Passive regex and DOM extraction.

### 6. `entity-clarity-audit`
- [x] **Valid YAML Frontmatter**: Clean block at top of `SKILL.md`.
- [x] **Name + Description + License**: `name: entity-clarity-audit`, complete description, `license: MIT`.
- [x] **Entrypoint Declaration**: `metadata.entrypoint: "false"`.
- [x] **Deterministic Procedure**: Checks for disambiguating brand identity: dedicated About page, Organization schema `legalName`, and authoritative `sameAs` links (Wikidata, Wikipedia, Crunchbase, LinkedIn).
- [x] **Declared Tools**: `requests`, `bs4`, `re`.
- [x] **Read-Only / No Site Altering**: Inspects publicly published link targets and metadata.

### 7. `engagement-audit`
- [x] **Valid YAML Frontmatter**: Clean block at top of `SKILL.md`.
- [x] **Name + Description + License**: `name: engagement-audit`, complete description, `license: MIT`.
- [x] **Entrypoint Declaration**: `metadata.entrypoint: "false"`.
- [x] **Deterministic Procedure**: Assesses navigation structure, above-the-fold heading hierarchy, call-to-action prominence, broken internal link percentage, and breadcrumbs.
- [x] **Declared Tools**: `requests`, `bs4`, `re`.
- [x] **Read-Only / No Site Altering**: Performs safe HEAD/GET status verification on internal hyperlinks.
