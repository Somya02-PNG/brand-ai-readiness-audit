---
name: render-readability-audit
description: >
  Detects content that is only visible after JavaScript execution by diffing
  raw HTTP response text against the fully-rendered DOM captured by a headless
  Playwright browser. Reports the percentage of visible text absent from the
  raw HTML that AI crawlers would see, and flags pages where key brand facts
  (name, price, address) are inaccessible without JS.
license: MIT
entrypoint: false
---

## When to use

Use this skill when you suspect a site uses heavy client-side rendering
(React, Vue, Angular, SPAs) that may hide its content from raw HTTP crawlers
and AI assistants that do not execute JavaScript.

Trigger phrases:
- "Does [domain] require JavaScript for its content?"
- "Check if [URL] is readable by AI crawlers"
- "Why is [brand] not being cited even though it has a website?"

## Inputs

| Name       | Type   | Required | Description                                              |
|------------|--------|----------|----------------------------------------------------------|
| `url`      | string | Yes      | The public URL or domain to audit.                       |

## Procedure

1. Normalize URL. Crawl up to 8 representative pages (homepage + top internal
   links by link frequency). For each page:
   a. **Raw fetch**: `requests.get(url)` → extract visible text with
      BeautifulSoup (`get_text(separator=" ", strip=True)`).
   b. **Rendered fetch** (if Playwright available): launch headless Chromium,
      navigate to URL, wait for `networkidle`, extract
      `document.body.innerText`.
   c. Compute overlap ratio:
      `overlap = len(raw_words ∩ rendered_words) / max(len(rendered_words), 1)`.
   d. `render_gap_pct = (1 - overlap) * 100`.
2. Identify key-fact patterns (address, phone, email, price tokens) in rendered
   text that are absent from raw text.
3. Emit a finding per page where `render_gap_pct > 30%` (high severity) or
   `render_gap_pct > 15%` (medium severity).
4. Emit a summary finding if the average render gap across all pages exceeds
   30%.
5. If Playwright is not installed, emit a single `low`-severity finding noting
   the limitation and continue with raw-only analysis.

**Cap**: Max 8 Playwright renders to stay within the 5-minute runtime budget.

## Output

A list of finding objects. Example:

```json
[
  {
    "title": "63% of homepage content absent from raw HTML",
    "severity": "high",
    "category": "discoverability",
    "skill_source": "render-readability-audit",
    "evidence": "Raw HTML word count: 142. Playwright-rendered word count: 387. Render gap: 63.3% (245 words invisible to raw crawlers). Affected URL: https://example.com/",
    "suggested_action": {
      "summary": "Implement server-side rendering (SSR) or static site generation (SSG) so critical content is present in the raw HTML response. Frameworks: Next.js, Nuxt, Astro.",
      "priority": "high"
    }
  }
]
```

## Running the script

```bash
python skills/render-readability-audit/scripts/check_render_gap.py https://example.com
```

Requires `playwright` and Chromium:

```bash
pip install playwright && playwright install chromium
```
