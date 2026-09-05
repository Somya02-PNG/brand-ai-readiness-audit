# Render Readability Audit — Check Reference

This checklist is executed by `check_render_gap.py`. Compares raw HTTP response
against Playwright-rendered DOM to detect JS-dependent content.

## Render gap thresholds

| Condition | Threshold | Severity |
|---|---|---|
| Site-wide average render gap | > 30% of rendered words absent from raw HTML | critical |
| Per-page render gap | > 30% | high |
| Per-page render gap | > 15% | medium |
| Low raw word count (no Playwright) | < 100 words in raw HTML | high |

## Per-page procedure

1. Raw fetch: `requests.get(url)` → BeautifulSoup `get_text(strip=True)`
2. Rendered fetch: Playwright `page.goto(url, wait_until="networkidle")` → `document.body.innerText`
3. Tokenize both to lowercase word sets (≥ 3 chars)
4. `render_gap_pct = |rendered_words - raw_words| / max(|rendered_words|, 1) * 100`
5. Detect key-fact patterns in rendered text absent from raw text

## Key-fact patterns to check for in render gap

```
Phone:   \b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b
Email:   [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}
Price:   \$[\d,]+(?:\.\d{2})?  |  €[\d,]+
ZIP:     \b\d{5}(?:-\d{4})?\b
```

If any of these patterns appear in rendered text but NOT in raw HTML → emit high-severity finding.

## Page selection for Playwright rendering

- Max 8 pages rendered (time budget)
- Priority order: homepage → pages with path segments matching `/product`, `/pricing`, `/about`, `/faq`
- All other pages: first-come from BFS queue

## Playwright settings

```python
browser = pw.chromium.launch(headless=True)
context = browser.new_context(ignore_https_errors=True)
page.goto(url, wait_until="networkidle", timeout=20_000)
text = page.evaluate("document.body.innerText")
```

## Fallback (no Playwright)

- Emit `low` severity: "Playwright not available; raw-HTML-only analysis performed."
- Still check raw word count. If < 100 words → emit `high` severity suggesting CSR.

## Evidence format

```
"Raw HTML: 142 words. Playwright-rendered: 387 words. 
 Render gap: 63.3% (245 words invisible to raw crawlers). 
 Affected URL: https://example.com/"
```

```
"Phone number '+1-800-555-0100' found in JS-rendered DOM but absent from raw HTML 
 on https://example.com/contact."
```
