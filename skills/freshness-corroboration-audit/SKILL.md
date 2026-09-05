---
name: freshness-corroboration-audit
description: >
  Validates internal fact consistency across a site's pages — checking that
  contact details (address, phone, email), pricing signals, and business hours
  agree with each other. Also checks for content freshness signals
  (dateModified, datePublished in JSON-LD and meta tags) that AI assistants
  use to judge whether information is current and trustworthy.
license: MIT
entrypoint: false
---

## When to use

Use this skill to detect factual contradictions within a site that may cause
AI assistants to distrust or refuse to cite its content, and to assess whether
the site signals content freshness to crawlers.

Trigger phrases:
- "Are facts consistent across [domain]?"
- "Check if [brand] has outdated or contradictory information"
- "Why does [brand] give AI conflicting information?"

## Inputs

| Name  | Type   | Required | Description                        |
|-------|--------|----------|------------------------------------|
| `url` | string | Yes      | The public URL or domain to audit. |

## Procedure

1. Crawl homepage + up to 14 pages (BFS, same-origin), prioritizing:
   `/contact`, `/about`, `/pricing`, `/faq`, footer links.
2. **Fact extraction** — per page, extract using regex patterns:
   - **Phone numbers**: E.164 and common formatted variants
     (`+1-XXX-XXX-XXXX`, `(XXX) XXX-XXXX`, etc.)
   - **Email addresses**: standard RFC-5321 pattern
   - **Physical addresses**: street-number + street-name patterns,
     ZIP/postal code patterns
   - **Prices**: currency symbols + numeric patterns (`$X`, `€X`, `from $X/mo`)
3. Canonicalize extracted facts by stripping whitespace and normalizing
   formats. Group by fact type across all pages.
4. If multiple distinct canonical values exist for the same fact type across
   different pages → emit a finding naming the conflicting values and the
   specific page URLs where each appears.
5. **Freshness signals** — for each page:
   - Check `<meta name="article:modified_time">` / `<meta property="og:updated_time">`.
   - Check `dateModified` and `datePublished` in any JSON-LD block.
   - Parse found dates; flag pages where `dateModified` is absent or
     more than 365 days in the past (medium severity).
6. If no pages across the sample have any freshness date signal → emit a
   `high`-severity finding.

## Output

Example findings:

```json
[
  {
    "title": "Phone number inconsistency across pages",
    "severity": "high",
    "category": "discoverability",
    "skill_source": "freshness-corroboration-audit",
    "evidence": "Found 2 distinct phone numbers: '+1-800-555-0100' on /contact and /footer; '+1-800-555-0199' on /about. Inconsistency may cause AI models to flag content as unreliable.",
    "suggested_action": {
      "summary": "Standardize the phone number in a single source of truth (e.g., a CMS global variable) and ensure all page templates reference it. Use E.164 format in JSON-LD.",
      "priority": "high"
    }
  },
  {
    "title": "No content freshness signals on any page",
    "severity": "high",
    "category": "discoverability",
    "skill_source": "freshness-corroboration-audit",
    "evidence": "Checked 15 pages; 0/15 contain dateModified, datePublished (JSON-LD), or article:modified_time (meta). AI crawlers cannot determine content currency.",
    "suggested_action": {
      "summary": "Add datePublished and dateModified to all Article/BlogPosting JSON-LD. Set the og:updated_time meta tag on every page. Regenerate sitemaps with <lastmod> dates.",
      "priority": "high"
    }
  }
]
```

## Running the script

```bash
python skills/freshness-corroboration-audit/scripts/check_freshness.py https://example.com
```
