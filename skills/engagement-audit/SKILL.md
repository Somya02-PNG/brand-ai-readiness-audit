---
name: engagement-audit
description: >
  Evaluates on-site visitor engagement signals: navigation clarity, percentage
  of broken internal links, dead-end pages with no outbound links, above-fold
  orientation cues (visible H1, clear CTA), and presence of wayfinding
  elements such as breadcrumbs and site search. These issues cause visitors
  to bounce before converting, defeating the purpose of AI-driven traffic.
license: MIT
entrypoint: false
---

## When to use

Use this skill when a brand is discoverable by AI assistants but visitors who
arrive from AI-generated recommendations still fail to engage or convert.

Trigger phrases:
- "Why do visitors to [domain] leave without engaging?"
- "Check navigation and UX health for [URL]"
- "Are there broken links on [domain]?"
- "Does [site] have good above-fold CTAs?"

## Inputs

| Name  | Type   | Required | Description                        |
|-------|--------|----------|------------------------------------|
| `url` | string | Yes      | The public URL or domain to audit. |

## Procedure

1. Crawl homepage + up to 14 pages (BFS, same-origin, cap 15 total).
   Collect all unique internal `<a href>` URLs seen across all pages.

2. **Broken internal links**:
   - HTTP GET each unique internal URL discovered (with throttle).
   - Count URLs returning 4xx or 5xx status codes.
   - Compute `broken_pct = broken_count / total_internal_links * 100`.
   - Emit `critical` if `broken_pct > 20%`; `high` if `> 10%`; `medium` if
     `> 5%`. List up to 10 broken URLs as evidence.

3. **Dead-end pages** (no exit links):
   - For each crawled page, count internal links on that page.
   - If a page has 0 internal outbound links → it's a dead end.
   - Emit a `medium`-severity finding listing dead-end URLs.

4. **Navigation depth**:
   - Parse `<nav>` elements; measure nesting depth of `<ul>/<li>` trees.
   - If max depth > 3 → emit `medium` finding (too complex).
   - If `<nav>` is absent from homepage → emit `high` finding.

5. **Above-fold orientation** (homepage only):
   - Check that an `<h1>` is present in the raw HTML.
   - Check that at least one `<a>` or `<button>` with text containing CTA
     keywords (e.g. "get started", "sign up", "try", "buy", "learn more",
     "contact", "request", "demo", "free") appears within the first 20% of
     the raw HTML body content.
   - Emit a `high` finding if H1 is absent; `medium` if CTA is absent.

6. **Wayfinding elements**:
   - Breadcrumbs: check for `<nav aria-label="breadcrumb">`,
     `class` containing `breadcrumb`, or BreadcrumbList JSON-LD.
   - Site search: check for `<input type="search">` or `role="search"`.
   - Emit `low`-severity findings for absent wayfinding on sites with > 10
     pages crawled.

## Output

Example findings:

```json
[
  {
    "title": "34% of internal links return 404",
    "severity": "critical",
    "category": "engagement",
    "skill_source": "engagement-audit",
    "evidence": "Discovered 82 unique internal links; 28/82 (34.1%) returned HTTP 4xx. Sample broken URLs: /old-pricing, /team/john-doe, /blog/2022/post-title.",
    "suggested_action": {
      "summary": "Audit and fix or redirect all broken internal URLs. Set up 301 redirects from old paths to their current equivalents. Use a link-checking tool in CI.",
      "priority": "critical"
    }
  },
  {
    "title": "No H1 heading on homepage",
    "severity": "high",
    "category": "engagement",
    "skill_source": "engagement-audit",
    "evidence": "Homepage (https://example.com/) raw HTML contains 0 <h1> elements. Without an H1, visitors and AI parsers cannot determine the page's primary topic.",
    "suggested_action": {
      "summary": "Add a single descriptive <h1> to the homepage that clearly states what the brand does (e.g., 'AI-Powered Inventory Management for E-Commerce').",
      "priority": "high"
    }
  }
]
```

## Running the script

```bash
python skills/engagement-audit/scripts/check_engagement.py https://example.com
```
